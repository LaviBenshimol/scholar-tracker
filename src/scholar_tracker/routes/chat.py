import re

import httpx
from fastapi import APIRouter

from ..models.database import get_total_citations, get_tracked_papers, update_paper_citations
from ..models.schemas import (
    ButtonDef,
    ButtonReply,
    ChatRequest,
    ChatResponse,
    ImageContent,
    ImageResponse,
    InteractiveAction,
    InteractiveBody,
    InteractiveContent,
    InteractiveHeader,
    InteractiveResponse,
    TextBody,
    TextResponse,
)
from ..services.fun_jokes import get_random_joke
from ..services.fun_quotes import get_random_quote
from ..utils.logger import logger

MAX_MESSAGE_LENGTH = 500

router = APIRouter(prefix="/ui-api")

# ---------------------------------------------------------------------------
# Meme categories (subreddits supported by meme-api.com)
# ---------------------------------------------------------------------------
MEME_CATEGORIES = {
    "1": ("memes", "General Memes"),
    "2": ("ProgrammerHumor", "Programmer Humor"),
    "3": ("wholesomememes", "Wholesome Memes"),
    "4": ("dankmemes", "Dank Memes"),
    "5": ("sciencememes", "Science Memes"),
}

# ---------------------------------------------------------------------------
# Chat endpoint  (used by WhatsApp bridge + UI simulator)
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
def handle_simulated_chat(payload: ChatRequest) -> ChatResponse:
    intent = ""
    if payload.type == "text" and payload.text:
        raw = payload.text.body.strip()
        if len(raw) > MAX_MESSAGE_LENGTH:
            raw = raw[:MAX_MESSAGE_LENGTH]
        intent = raw.lower()
    elif payload.type == "interactive" and payload.interactive:
        intent = payload.interactive.button_reply.id

    if not intent:
        intent = "help"

    logger.info(f"Chat received intent: {intent}")

    # -- Stats ---------------------------------------------------------
    if intent in ("stats", "get_stats"):
        papers = get_tracked_papers()
        if not papers:
            body = "No papers tracked yet.\nUse the ORCID panel to load your profile first."
        else:
            lines = ["*Citation Dashboard*", ""]
            grand = 0
            for p in papers:
                c = p["current_citations"]
                grand += c
                lines.append(f"  {p['title']}")
                lines.append(f"  Citations: {c}")
                lines.append("")
            lines.append(f"Total citations: {grand}")
            body = "\n".join(lines)
        return TextResponse(text=TextBody(body=body))

    # -- Meme (with optional category) ---------------------------------
    elif intent.startswith("meme"):
        parts = intent.split(None, 1)
        arg = parts[1] if len(parts) > 1 else ""

        # "meme help" -> show categories
        if arg == "help":
            lines = ["*Meme Categories*", ""]
            for num, (sub, label) in MEME_CATEGORIES.items():
                lines.append(f"  {num}. {label} (r/{sub})")
            lines.append("")
            lines.append("Usage: meme, meme 1, meme 3")
            return TextResponse(text=TextBody(body="\n".join(lines)))

        # "meme 2" -> specific category
        subreddit = "memes"
        if arg in MEME_CATEGORIES:
            subreddit = MEME_CATEGORIES[arg][0]

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(f"https://meme-api.com/gimme/{subreddit}")
                resp.raise_for_status()
                data = resp.json()
                title = data.get("title", "Random Meme")
                url = data.get("url", "")
                sub = data.get("subreddit", subreddit)
                if url:
                    return ImageResponse(
                        image=ImageContent(url=url, caption=f"{title}\nr/{sub}")
                    )
                return TextResponse(text=TextBody(body="Couldn't fetch a meme. Try again!"))
        except Exception as e:
            logger.error(f"Meme fetch error: {e}")
            return TextResponse(text=TextBody(body="Meme API is down. Try again later!"))

    elif intent == "get_meme":
        # Button reply from menu
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get("https://meme-api.com/gimme")
                resp.raise_for_status()
                data = resp.json()
                title = data.get("title", "Random Meme")
                url = data.get("url", "")
                sub = data.get("subreddit", "memes")
                if url:
                    return ImageResponse(
                        image=ImageContent(url=url, caption=f"{title}\nr/{sub}")
                    )
                return TextResponse(text=TextBody(body="Couldn't fetch a meme. Try again!"))
        except Exception as e:
            logger.error(f"Meme fetch error: {e}")
            return TextResponse(text=TextBody(body="Meme API is down. Try again later!"))

    # -- Quote ---------------------------------------------------------
    elif intent == "quote":
        return TextResponse(text=TextBody(body=get_random_quote()))

    # -- Joke ----------------------------------------------------------
    elif intent == "joke":
        return TextResponse(text=TextBody(body=get_random_joke()))

    # -- ORCID ---------------------------------------------------------
    elif intent.startswith("orcid"):
        parts = intent.split(None, 1)
        arg = parts[1] if len(parts) > 1 else ""
        orcid = _extract_orcid_id(arg)
        if not orcid:
            return TextResponse(
                text=TextBody(
                    body="Usage: orcid <id>\n"
                    "Example: orcid 0009-0003-8948-3386"
                )
            )
        try:
            data = _fetch_openalex(orcid)
            if "error" in data:
                return TextResponse(text=TextBody(body=data["error"]))
            for p in data["papers"]:
                update_paper_citations(p["title"], p["cited_by_count"])
            name = data["author"]["name"]
            count = len(data["papers"])
            total = data["author"]["total_citations"]
            body = (
                f"✅ *Loaded {count} papers for {name}*\n"
                f"Total citations: {total}\n"
                f"Type 'stats' to see details."
            )
            return TextResponse(text=TextBody(body=body))
        except Exception as e:
            logger.error(f"ORCID command error: {e}")
            return TextResponse(
                text=TextBody(body="Failed to load ORCID data. Try again later.")
            )

    # -- Menu ----------------------------------------------------------
    elif intent == "menu":
        return InteractiveResponse(
            interactive=InteractiveContent(
                header=InteractiveHeader(text="Scholar Tracker"),
                body=InteractiveBody(text="What would you like to do?"),
                action=InteractiveAction(buttons=[
                    ButtonDef(reply=ButtonReply(id="get_stats"), title="\U0001f4ca Stats"),
                    ButtonDef(reply=ButtonReply(id="get_meme"), title="\U0001f602 Meme"),
                    ButtonDef(reply=ButtonReply(id="quote"), title="\U0001f4ac Quote"),
                ]),
            ),
        )

    # -- Help ----------------------------------------------------------
    elif intent == "help":
        body = (
            "*Commands:*\n"
            "  menu      — show menu\n"
            "  stats     — citation counts\n"
            "  meme      — random meme\n"
            "  meme 1-5  — meme by category\n"
            "  joke      — random joke\n"
            "  quote     — motivational quote\n"
            "  orcid <id> — load papers by ORCID"
        )
        return TextResponse(text=TextBody(body=body))

    # -- Unknown -------------------------------------------------------
    else:
        return TextResponse(
            text=TextBody(body="I didn't understand that. Type 'menu' for options.")
        )


# ---------------------------------------------------------------------------
# ORCID  ->  OpenAlex  (gives us papers + citation counts)
# ---------------------------------------------------------------------------

def _extract_orcid_id(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r'(\d{4}-\d{4}-\d{4}-\d{3}[\dX])', raw)
    return m.group(1) if m else ""


def _fetch_openalex(orcid_id: str) -> dict:
    """
    Query OpenAlex by ORCID.  Returns { author: {...}, papers: [...] }.
    OpenAlex is free, fast, no auth required, and has citation counts.
    """
    with httpx.Client(timeout=20) as client:
        author_url = f"https://api.openalex.org/authors/https://orcid.org/{orcid_id}"
        author_resp = client.get(author_url)
        if author_resp.status_code == 404:
            return {"error": f"ORCID '{orcid_id}' not found in OpenAlex."}
        author_resp.raise_for_status()
        author_data = author_resp.json()

        display_name = author_data.get("display_name", "Unknown")
        works_count = author_data.get("works_count", 0)
        cited_by = author_data.get("cited_by_count", 0)

        works_url = (
            f"https://api.openalex.org/works"
            f"?filter=author.orcid:{orcid_id}"
            f"&sort=cited_by_count:desc"
            f"&per_page=50"
        )
        works_resp = client.get(works_url)
        works_resp.raise_for_status()
        works_data = works_resp.json()

        papers = []
        for w in works_data.get("results", []):
            title = w.get("title") or "Untitled"
            cite_count = w.get("cited_by_count", 0)
            doi = w.get("doi") or ""
            pub_year = w.get("publication_year")
            papers.append({
                "title": title,
                "cited_by_count": cite_count,
                "doi": doi,
                "year": pub_year,
            })

    return {
        "author": {
            "name": display_name,
            "orcid_id": orcid_id,
            "orcid_url": f"https://orcid.org/{orcid_id}",
            "total_works": works_count,
            "total_citations": cited_by,
        },
        "papers": papers,
    }


@router.get("/lookup-orcid")
def lookup_orcid(orcid_id: str = ""):
    """Look up an ORCID via OpenAlex, return profile + papers with cite counts,
    and seed them into the local DB so the chat tracker works immediately."""

    orcid_id = _extract_orcid_id(orcid_id)
    if not orcid_id:
        return {
            "error": "Please enter a valid ORCID ID "
            "(e.g. 0009-0003-8948-3386 or the full URL)."
        }

    try:
        data = _fetch_openalex(orcid_id)
        if "error" in data:
            return data

        for p in data["papers"]:
            update_paper_citations(p["title"], p["cited_by_count"])

        logger.info(
            f"ORCID lookup seeded {len(data['papers'])} papers into DB "
            f"for {data['author']['name']}"
        )
        return data

    except httpx.HTTPStatusError as e:
        logger.error(f"OpenAlex HTTP error: {e}")
        return {"error": f"OpenAlex returned status {e.response.status_code}."}
    except Exception as e:
        logger.error(f"ORCID/OpenAlex lookup error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Debug: trigger a mock background job
# ---------------------------------------------------------------------------

@router.post("/trigger-job")
def trigger_local_job():
    """Simulate the scheduled cron check -- fakes a +1 delta on each paper."""
    logger.info("UI triggered a background job execution.")
    papers = get_tracked_papers()

    if not papers:
        return {
            "status": "ok",
            "notification": (
                "No papers tracked yet!\n"
                "Use the ORCID panel to load your profile first."
            ),
        }

    new_citations = []
    for p in papers:
        update_paper_citations(p["title"], p["current_citations"] + 1)
        new_citations.append(
            f"{p['title']}: +1 (total: {p['current_citations'] + 1})"
        )

    total = get_total_citations()
    msg = "New Citations Detected!\n" + "-" * 30 + "\n"
    msg += "\n".join(new_citations)
    msg += "\n" + "-" * 30 + f"\nGrand total: {total}"
    return {"status": "ok", "notification": msg}
