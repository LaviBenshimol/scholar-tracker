"""Shared test fixtures for scholar-tracker tests."""
import os

import pytest

# Override DB path for tests BEFORE importing any app modules
os.environ["DB_PATH"] = ":memory:"
os.environ["WHATSAPP_TOKEN"] = ""
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = ""
os.environ["WHATSAPP_APP_SECRET"] = ""
os.environ["WHATSAPP_VERIFY_TOKEN"] = "test_verify_token"
os.environ["ALLOWED_PHONE_NUMBERS"] = "972501234567"
os.environ["SCHOLAR_AUTHOR_ID"] = ""

from scholar_tracker.config import settings  # noqa: E402  # isort:skip
from scholar_tracker.models.database import init_db  # noqa: E402  # isort:skip


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Create a fresh SQLite database for each test."""
    db_file = str(tmp_path / "test.db")
    original_db = settings.db_path
    settings.db_path = db_file

    init_db()

    yield db_file

    settings.db_path = original_db


@pytest.fixture
def sample_paper():
    """A sample paper dict for testing."""
    return {
        "title": "Attention Is All You Need",
        "citations": 150000,
    }
