import json

import httpx

from ..config import settings
from ..utils.logger import logger


class WhatsAppNotifier:
    def __init__(self):
        phone_id = settings.whatsapp_phone_number_id
        self.api_url = (
            f"https://graph.facebook.com/v18.0/{phone_id}/messages"
        )
        self.headers = {
            "Authorization": f"Bearer {settings.whatsapp_token}",
            "Content-Type": "application/json",
        }

    async def send_text(self, to: str, message: str):
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message}
        }
        await self._send(payload)

    async def send_interactive_menu(self, to: str, title: str, body: str, buttons: list):
        """Sends an interactive message with quick reply buttons."""
        interactive_buttons = []
        for i, (btn_id, btn_title) in enumerate(buttons):
            interactive_buttons.append({
                "type": "reply",
                "reply": {"id": btn_id, "title": btn_title}
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {"type": "text", "text": title},
                "body": {"text": body},
                "action": {"buttons": interactive_buttons}
            }
        }
        await self._send(payload)

    async def send_template(self, to: str, component_params: list):
        """Sends pre-approved template message when outside of 24hr window."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": settings.template_name,
                "language": {"code": settings.template_language},
                "components": [
                    {"type": "body", "parameters": component_params}
                ]
            }
        }
        await self._send(payload)

    async def _send(self, payload: dict):
        if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
            logger.warning("WhatsApp credentials not set. Logging message instead:")
            logger.info(json.dumps(payload, indent=2))
            return

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.api_url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"WhatsApp message sent successfully to {payload.get('to')}")
            except httpx.HTTPStatusError as e:
                logger.error(f"WhatsApp API Error: {e.response.text}")
            except Exception as e:
                logger.error(f"Error sending WhatsApp message: {e}")


notifier = WhatsAppNotifier()
