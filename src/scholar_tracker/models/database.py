import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import settings
from ..utils.logger import logger


def init_db():
    Path(settings.db_path).parent.mkdir(exist_ok=True)
    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                current_citations INTEGER DEFAULT 0,
                last_checked DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS citation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id INTEGER,
                citation_count INTEGER,
                delta INTEGER,
                recorded_at DATETIME,
                FOREIGN KEY (paper_id) REFERENCES papers (id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                model TEXT DEFAULT '',
                intent TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id TEXT PRIMARY KEY,
                summary_text TEXT DEFAULT '',
                summary_up_to_id INTEGER DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id TEXT PRIMARY KEY,
                facts TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_logs_user "
            "ON chat_logs(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_logs_time "
            "ON chat_logs(created_at)"
        )
        conn.commit()
    logger.info("Database initialized.")


def get_paper_by_title(title: str) -> Optional[Dict]:
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE title = ?", (title,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_paper_citations(title: str, citations: int) -> Tuple[bool, int]:
    """
    Returns (has_changed: bool, delta: int)
    """
    now = datetime.now(timezone.utc).isoformat()
    paper = get_paper_by_title(title)

    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        if not paper:
            # New paper tracking
            cursor.execute(
                "INSERT INTO papers (title, current_citations, last_checked) VALUES (?, ?, ?)",
                (title, citations, now)
            )
            paper_id = cursor.lastrowid

            # Record base history point
            cursor.execute(
                "INSERT INTO citation_history "
                "(paper_id, citation_count, delta, recorded_at) "
                "VALUES (?, ?, ?, ?)",
                (paper_id, citations, 0, now)
            )
            return True, 0

        else:
            paper_id = paper['id']
            prev_citations = paper['current_citations']
            delta = citations - prev_citations

            if delta > 0:
                cursor.execute(
                    "UPDATE papers SET current_citations = ?, last_checked = ? WHERE id = ?",
                    (citations, now, paper_id)
                )
                cursor.execute(
                    "INSERT INTO citation_history "
                    "(paper_id, citation_count, delta, recorded_at) "
                    "VALUES (?, ?, ?, ?)",
                    (paper_id, citations, delta, now)
                )
                return True, delta

            else:
                cursor.execute("UPDATE papers SET last_checked = ? WHERE id = ?", (now, paper_id))
                return False, 0


def get_total_citations() -> int:
    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(current_citations) FROM papers")
        result = cursor.fetchone()[0]
        return result if result else 0


def get_tracked_papers() -> List[Dict]:
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM papers")
        return [dict(r) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Chat logs (every LLM message, source of truth)
# ---------------------------------------------------------------------------

def log_chat_message(
    user_id: str, role: str, content: str,
    tokens_used: int = 0, model: str = "", intent: str = "llm",
) -> int:
    """Store a chat message. Returns the new row ID."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_logs "
            "(user_id, role, content, tokens_used, model, intent, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, role, content, tokens_used, model, intent, now),
        )
        return cursor.lastrowid


def get_recent_messages(
    user_id: str, after_id: int = 0, limit: int = 20,
) -> List[Dict]:
    """Load recent messages for a user after a given ID."""
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, role, content, created_at FROM chat_logs "
            "WHERE user_id = ? AND id > ? AND intent = 'llm' "
            "ORDER BY id ASC LIMIT ?",
            (user_id, after_id, limit),
        )
        return [dict(r) for r in cursor.fetchall()]


def get_chat_logs(
    limit: int = 50, user_id: Optional[str] = None,
) -> List[Dict]:
    """Get recent chat logs for admin dashboard."""
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if user_id:
            cursor.execute(
                "SELECT * FROM chat_logs WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM chat_logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in cursor.fetchall()]


def get_token_usage_today() -> int:
    """Total tokens used today across all users."""
    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM chat_logs "
            "WHERE date(created_at) = date('now')"
        )
        return cursor.fetchone()[0]


# ---------------------------------------------------------------------------
# User sessions (sliding window pointer)
# ---------------------------------------------------------------------------

def get_user_session(user_id: str) -> Optional[Dict]:
    """Get the summarization pointer for a user."""
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM user_sessions WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_user_session(
    user_id: str, summary_text: str, summary_up_to_id: int,
) -> None:
    """Update or create the summarization pointer."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_sessions (user_id, summary_text, summary_up_to_id, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "summary_text = excluded.summary_text, "
            "summary_up_to_id = excluded.summary_up_to_id, "
            "updated_at = excluded.updated_at",
            (user_id, summary_text, summary_up_to_id, now),
        )


# ---------------------------------------------------------------------------
# User memory (long-term facts, persistent)
# ---------------------------------------------------------------------------

def get_user_memory(user_id: str) -> str:
    """Get LTM facts for a user. Returns empty string if none."""
    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT facts FROM user_memory WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else ""


def upsert_user_memory(user_id: str, facts: str) -> None:
    """Store or update LTM facts for a user."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(settings.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_memory (user_id, facts, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "facts = excluded.facts, updated_at = excluded.updated_at",
            (user_id, facts, now),
        )
