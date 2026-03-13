"""Tests for the UI API / bridge chat endpoint (used by WhatsApp Web bridge)."""
import pytest
from fastapi.testclient import TestClient

from scholar_tracker.models.database import update_paper_citations


@pytest.fixture
def client(fresh_db):
    """Create a test client with fresh DB."""
    from main import app
    return TestClient(app)


class TestChatEndpoint:
    """Tests for /ui-api/chat which the WhatsApp bridge calls."""

    def test_menu_returns_interactive(self, client):
        """'menu' should return an interactive button payload."""
        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "menu"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "interactive"
        buttons = data["interactive"]["action"]["buttons"]
        assert len(buttons) == 3
        ids = [b["reply"]["id"] for b in buttons]
        assert "get_stats" in ids
        assert "get_meme" in ids
        assert "help" in ids

    def test_stats_empty_db(self, client):
        """'stats' with no papers should say no papers tracked."""
        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "stats"}})
        data = resp.json()
        assert data["type"] == "text"
        assert "no papers" in data["text"]["body"].lower()

    def test_stats_with_papers(self, client, fresh_db):
        """'stats' should return citation counts for tracked papers."""
        update_paper_citations("My Great Paper", 42)
        update_paper_citations("Another Paper", 10)

        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "stats"}})
        data = resp.json()
        body = data["text"]["body"]
        assert "My Great Paper" in body
        assert "42" in body
        assert "Another Paper" in body
        assert "10" in body

    def test_get_stats_alias(self, client, fresh_db):
        """'get_stats' (button ID) should work same as 'stats'."""
        update_paper_citations("Test Paper", 5)

        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "get_stats"}})
        data = resp.json()
        assert "Test Paper" in data["text"]["body"]
        assert "5" in data["text"]["body"]

    def test_help_returns_commands(self, client):
        """'help' should list available commands."""
        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "help"}})
        data = resp.json()
        assert data["type"] == "text"
        body = data["text"]["body"].lower()
        assert "menu" in body
        assert "stats" in body

    def test_unknown_intent_fallback(self, client):
        """Unknown text should return a fallback message."""
        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "xyzzy123"}})
        data = resp.json()
        assert data["type"] == "text"
        assert "menu" in data["text"]["body"].lower()

    def test_interactive_button_reply(self, client, fresh_db):
        """Interactive button reply (from WhatsApp) should route correctly."""
        update_paper_citations("Button Paper", 99)

        resp = client.post("/ui-api/chat", json={
            "type": "interactive",
            "interactive": {"button_reply": {"id": "get_stats"}}
        })
        data = resp.json()
        assert "Button Paper" in data["text"]["body"]

    def test_case_insensitive(self, client):
        """Commands should be case-insensitive."""
        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "MENU"}})
        assert resp.json()["type"] == "interactive"

        resp = client.post("/ui-api/chat", json={"type": "text", "text": {"body": "Stats"}})
        assert resp.json()["type"] == "text"


class TestOrcidLookup:
    """Tests for /ui-api/lookup-orcid endpoint."""

    def test_invalid_orcid(self, client):
        """Invalid ORCID should return error."""
        resp = client.get("/ui-api/lookup-orcid?orcid_id=not-an-orcid")
        data = resp.json()
        assert "error" in data

    def test_empty_orcid(self, client):
        """Empty ORCID should return error."""
        resp = client.get("/ui-api/lookup-orcid?orcid_id=")
        data = resp.json()
        assert "error" in data
