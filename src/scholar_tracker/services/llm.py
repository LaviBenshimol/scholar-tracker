"""LLM service — Groq + Kimi K2 with 3-tier DB-backed memory."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..config import settings
from ..models.database import (
    get_recent_messages,
    get_total_citations,
    get_tracked_papers,
    get_user_memory,
    get_user_session,
    log_chat_message,
    upsert_user_memory,
    upsert_user_session,
)
from ..utils.logger import logger

# ---------------------------------------------------------------------------
# Load system prompt from file
# ---------------------------------------------------------------------------
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "system.txt"
SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8").strip() if _PROMPT_PATH.exists() else (
    "You are ScholarBot, a helpful research assistant on WhatsApp. "
    "Keep responses short (1-3 sentences)."
)

# Max recent messages to load from DB (10 turns = 20 messages)
MAX_RECENT_MESSAGES = 20

# Token threshold to trigger LTM extraction
LTM_TOKEN_THRESHOLD = 10_000

# Summarization prompt
SUMMARIZE_PROMPT = (
    "Summarize the following conversation in 2-3 concise sentences. "
    "Focus on key topics discussed and any important information shared."
)

# LTM extraction prompt
LTM_EXTRACT_PROMPT = (
    "From the conversation below, extract key facts about the user. "
    "Include: name, language preference, research field, interests, "
    "preferences, and any important context. "
    "Output as a short bullet-point list. Max 200 words."
)


# ---------------------------------------------------------------------------
# In-memory session cache (rebuilt from DB on demand)
# ---------------------------------------------------------------------------
class SessionCache:
    """In-memory cache for a user's session. Rebuilt from DB if missing."""

    def __init__(self):
        self.messages: List[Dict] = []  # recent turns loaded from DB
        self.summary: str = ""
        self.summary_up_to_id: int = 0
        self.ltm_facts: str = ""
        self.session_tokens: int = 0
        self.last_active: Optional[datetime] = None


_cache: Dict[str, SessionCache] = {}


# ---------------------------------------------------------------------------
# ConversationManager
# ---------------------------------------------------------------------------

def _get_groq_client():
    """Lazy-init Groq client."""
    if not settings.groq_api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=settings.groq_api_key)
    except Exception as e:
        logger.error(f"Failed to init Groq client: {e}")
        return None


def _format_time_gap(seconds: float) -> str:
    """Human-readable time gap string."""
    if seconds < 3600:
        return f"{int(seconds / 60)} minute"
    elif seconds < 86400:
        return f"{int(seconds / 3600)} hour"
    else:
        return f"{int(seconds / 86400)} day"


def _inject_time_gaps(messages: List[Dict]) -> List[Dict]:
    """Insert time gap markers between messages with >2hr gaps."""
    if not messages:
        return messages

    result = []
    for i, msg in enumerate(messages):
        if i > 0 and "created_at" in msg and "created_at" in messages[i - 1]:
            try:
                t1 = datetime.fromisoformat(messages[i - 1]["created_at"])
                t2 = datetime.fromisoformat(msg["created_at"])
                gap = (t2 - t1).total_seconds()
                if gap > 7200:  # 2 hours
                    gap_str = _format_time_gap(gap)
                    result.append({
                        "role": "system",
                        "content": f"[{gap_str} gap in conversation]",
                    })
            except (ValueError, TypeError):
                pass
        result.append({"role": msg["role"], "content": msg["content"]})
    return result


def _build_context_messages(
    user_id: str, cache: SessionCache, new_message: str,
) -> List[Dict]:
    """Build the full messages array for the Groq API call."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Time awareness
    now = datetime.now(timezone.utc)
    time_ctx = f"Current time: {now.strftime('%Y-%m-%d %H:%M UTC')}."
    if cache.last_active:
        gap = (now - cache.last_active).total_seconds()
        if gap > 3600:
            time_ctx += f" User was last active {_format_time_gap(gap)}s ago."
    messages.append({"role": "system", "content": time_ctx})

    # App state
    try:
        papers = get_tracked_papers()
        total = get_total_citations()
        if papers:
            messages.append({
                "role": "system",
                "content": (
                    f"User tracks {len(papers)} papers with "
                    f"{total} total citations."
                ),
            })
    except Exception:
        pass

    # Long-term memory
    if cache.ltm_facts:
        messages.append({
            "role": "system",
            "content": f"Known facts about user: {cache.ltm_facts}",
        })

    # Session summary
    if cache.summary:
        messages.append({
            "role": "system",
            "content": f"Previous conversation summary: {cache.summary}",
        })

    # Recent messages (with time gaps)
    recent_with_gaps = _inject_time_gaps(cache.messages)
    messages.extend(recent_with_gaps)

    # New message
    messages.append({"role": "user", "content": new_message})

    return messages


def _load_cache_from_db(user_id: str) -> SessionCache:
    """Rebuild session cache from database."""
    cache = SessionCache()

    # Load LTM facts
    cache.ltm_facts = get_user_memory(user_id)

    # Load session pointer
    session = get_user_session(user_id)
    if session:
        cache.summary = session.get("summary_text", "")
        cache.summary_up_to_id = session.get("summary_up_to_id", 0)

    # Load recent messages after the summary pointer
    recent = get_recent_messages(
        user_id, after_id=cache.summary_up_to_id, limit=MAX_RECENT_MESSAGES,
    )
    cache.messages = recent

    # Set last_active from most recent message
    if recent:
        try:
            cache.last_active = datetime.fromisoformat(recent[-1]["created_at"])
        except (ValueError, TypeError):
            pass

    return cache


def _maybe_summarize(user_id: str, cache: SessionCache, client) -> None:
    """If working memory exceeds MAX, summarize old messages."""
    if len(cache.messages) <= MAX_RECENT_MESSAGES:
        return

    # Take the oldest half to summarize
    to_summarize = cache.messages[:len(cache.messages) - MAX_RECENT_MESSAGES]
    if not to_summarize:
        return

    # Build summarization request
    convo_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in to_summarize
    )
    old_summary = f"Previous summary: {cache.summary}\n\n" if cache.summary else ""
    prompt = f"{old_summary}New conversation to summarize:\n{convo_text}"

    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SUMMARIZE_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        new_summary = resp.choices[0].message.content.strip()
        last_id = to_summarize[-1].get("id", cache.summary_up_to_id)

        # Update DB
        upsert_user_session(user_id, new_summary, last_id)

        # Update cache
        cache.summary = new_summary
        cache.summary_up_to_id = last_id
        cache.messages = cache.messages[len(to_summarize):]

        logger.info(f"Summarized {len(to_summarize)} messages for {user_id}")
    except Exception as e:
        logger.error(f"Summarization error: {e}")


def _maybe_extract_ltm(user_id: str, cache: SessionCache, client) -> None:
    """If session tokens > threshold, extract LTM facts."""
    if cache.session_tokens < LTM_TOKEN_THRESHOLD:
        return

    convo_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in cache.messages
    )
    old_facts = f"Previously known facts: {cache.ltm_facts}\n\n" if cache.ltm_facts else ""
    prompt = f"{old_facts}Recent conversation:\n{convo_text}"

    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": LTM_EXTRACT_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        facts = resp.choices[0].message.content.strip()
        upsert_user_memory(user_id, facts)
        cache.ltm_facts = facts
        cache.session_tokens = 0  # reset counter

        logger.info(f"Extracted LTM for {user_id}: {facts[:100]}...")
    except Exception as e:
        logger.error(f"LTM extraction error: {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat(user_id: str, message: str) -> str:
    """Send a message as a user, get an LLM response. Full memory management."""
    client = _get_groq_client()
    if not client:
        return (
            "LLM is not configured. Set GROQ_API_KEY in .env. "
            "Type 'help' for available commands."
        )

    # Get or rebuild cache
    if user_id not in _cache:
        _cache[user_id] = _load_cache_from_db(user_id)
    cache = _cache[user_id]

    # Maybe summarize if history is too long
    _maybe_summarize(user_id, cache, client)

    # Build context and call Groq
    messages = _build_context_messages(user_id, cache, message)

    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        reply = resp.choices[0].message.content.strip()
        tokens = resp.usage.total_tokens if resp.usage else 0

        # Log both messages to DB
        user_log_id = log_chat_message(
            user_id, "user", message, model=settings.llm_model,
        )
        log_chat_message(
            user_id, "assistant", reply,
            tokens_used=tokens, model=settings.llm_model,
        )

        # Update cache
        cache.messages.append({
            "id": user_log_id,
            "role": "user",
            "content": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cache.messages.append({
            "id": user_log_id + 1,
            "role": "assistant",
            "content": reply,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        cache.session_tokens += tokens
        cache.last_active = datetime.now(timezone.utc)

        # Maybe extract LTM
        _maybe_extract_ltm(user_id, cache, client)

        return reply

    except Exception as e:
        logger.error(f"Groq API error for {user_id}: {e}")
        return "I'm having trouble thinking right now 🤔 Try again, or type 'help' for commands."


def clear_session(user_id: str) -> None:
    """Clear in-memory cache for a user (DB stays intact)."""
    _cache.pop(user_id, None)
