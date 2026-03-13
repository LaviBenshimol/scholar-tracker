import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..models.database import get_total_citations
from ..services.notifier import notifier
from ..utils.logger import logger

router = APIRouter()


def verify_signature(payload: bytes, signature_header: str) -> bool:
    if not settings.whatsapp_app_secret or not signature_header:
        return True

    expected_hash = hmac.new(
        key=settings.whatsapp_app_secret.encode('utf-8'),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()

    expected_signature = f"sha256={expected_hash}"
    return hmac.compare_digest(expected_signature, signature_header)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Webhook Verification for Meta to prove we own the endpoint"""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(hub_challenge)

    logger.warning("WhatsApp webhook verification failure")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhook")
async def receive_message(request: Request, x_hub_signature_256: str = Header(None)):
    """Process incoming WhatsApp messages."""
    body = await request.body()

    if not verify_signature(body, x_hub_signature_256):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()

    try:
        if "messages" not in data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}):
            return {"status": "ok"}

        message_data = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender_phone = message_data["from"]

        if settings.whitelisted_numbers and sender_phone not in settings.whitelisted_numbers:
            logger.warning(f"Ignored message from unauthorized sender: {sender_phone}")
            return {"status": "ok"}

        message_type = message_data["type"]

        intent = ""
        if message_type == "text":
            intent = message_data["text"]["body"].strip().lower()
        elif message_type == "interactive":
            intent = message_data["interactive"]["button_reply"]["id"]

        await handle_intent(sender_phone, intent)
    except Exception as e:
        logger.error(f"Error parsing webhook payload: {e}")

    return {"status": "ok"}


async def handle_intent(sender: str, intent: str):
    logger.info(f"Handling intent from {sender}: {intent}")

    if intent in ["stats", "get_stats"]:
        total = get_total_citations()
        await notifier.send_text(sender, f"Current total citations: {total}")

    elif intent in ["menu"]:
        await notifier.send_interactive_menu(
            to=sender,
            title="Scholar Tracker",
            body="What would you like to do?",
            buttons=[
                ("get_stats", "Get Stats"),
                ("help", "Help")
            ]
        )

    elif intent == "help":
        await notifier.send_text(sender, "Available commands: stats, menu, meme")

    else:
        await notifier.send_text(sender, "I didn't understand that. Type 'menu' for options.")
