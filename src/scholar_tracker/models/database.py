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
