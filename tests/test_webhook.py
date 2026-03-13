"""Unit tests for the webhook handler logic."""
from unittest.mock import AsyncMock, patch

import pytest

from scholar_tracker.models.database import update_paper_citations
from scholar_tracker.routes.webhook import handle_intent, verify_signature


class TestVerifySignature:
    """Tests for HMAC signature verification."""

    def test_empty_secret_passes(self):
        """When app secret is not configured, verification passes (dev mode)."""
        with patch("scholar_tracker.routes.webhook.settings") as mock_settings:
            mock_settings.whatsapp_app_secret = ""
            assert verify_signature(b"payload", "sha256=anything") is True

    def test_empty_signature_passes_when_no_secret(self):
        """When neither secret nor signature, verification passes."""
        with patch("scholar_tracker.routes.webhook.settings") as mock_settings:
            mock_settings.whatsapp_app_secret = ""
            assert verify_signature(b"payload", "") is True

    def test_valid_signature_passes(self):
        """Correct HMAC signature should pass."""
        import hashlib
        import hmac

        secret = "test_secret"
        payload = b"test_payload"
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        with patch("scholar_tracker.routes.webhook.settings") as mock_settings:
            mock_settings.whatsapp_app_secret = secret
            assert verify_signature(payload, f"sha256={expected}") is True

    def test_invalid_signature_fails(self):
        """Wrong HMAC signature should fail."""
        with patch("scholar_tracker.routes.webhook.settings") as mock_settings:
            mock_settings.whatsapp_app_secret = "real_secret"
            assert verify_signature(b"payload", "sha256=wrong_hash") is False


class TestHandleIntent:
    """Tests for intent routing logic."""

    @pytest.mark.asyncio
    async def test_stats_intent(self, fresh_db):
        """'stats' intent should send citation count."""
        update_paper_citations("Paper A", 42)

        with patch("scholar_tracker.routes.webhook.notifier") as mock_notifier:
            mock_notifier.send_text = AsyncMock()
            await handle_intent("972501234567", "stats")

            mock_notifier.send_text.assert_called_once()
            call_args = mock_notifier.send_text.call_args
            assert "42" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_menu_intent(self, fresh_db):
        """'menu' intent should send interactive buttons."""
        with patch("scholar_tracker.routes.webhook.notifier") as mock_notifier:
            mock_notifier.send_interactive_menu = AsyncMock()
            await handle_intent("972501234567", "menu")

            mock_notifier.send_interactive_menu.assert_called_once()

    @pytest.mark.asyncio
    async def test_help_intent(self, fresh_db):
        """'help' intent should send available commands."""
        with patch("scholar_tracker.routes.webhook.notifier") as mock_notifier:
            mock_notifier.send_text = AsyncMock()
            await handle_intent("972501234567", "help")

            call_args = mock_notifier.send_text.call_args
            assert "commands" in call_args[0][1].lower() or "available" in call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_unknown_intent(self, fresh_db):
        """Unknown intent should send fallback message."""
        with patch("scholar_tracker.routes.webhook.notifier") as mock_notifier:
            mock_notifier.send_text = AsyncMock()
            await handle_intent("972501234567", "gibberish_xyz")

            call_args = mock_notifier.send_text.call_args
            assert "menu" in call_args[0][1].lower()
