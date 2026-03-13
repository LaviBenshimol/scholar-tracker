import logging
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("scholar_tracker")


class Settings(BaseSettings):
    # WhatsApp Webhook Secrets
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""

    # Private Usage Whitelist
    allowed_phone_numbers: str = ""

    # Scheduler & Tracking config
    scholar_author_id: Optional[str] = None
    orcid_id: str = ""
    check_interval_hours: int = 24
    scraper_api_key: Optional[str] = None

    db_path: str = "data/citations.db"
    log_path: str = "data/scholar_tracker.log"

    # Notification Details
    template_name: str = "citation_update"
    template_language: str = "en"

    # LLM (Groq)
    groq_api_key: str = ""
    llm_model: str = "moonshotai/kimi-k2-instruct-0905"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def whitelisted_numbers(self) -> List[str]:
        if not self.allowed_phone_numbers:
            return []
        return [num.strip() for num in self.allowed_phone_numbers.split(",")]

    def validate_startup(self) -> None:
        """Warn about missing configuration on startup."""
        if not self.whatsapp_token:
            logger.warning("WHATSAPP_TOKEN not set — outbound messages will be logged only")
        if not self.whatsapp_verify_token:
            logger.warning("WHATSAPP_VERIFY_TOKEN not set — webhook verification will fail")
        if not self.scholar_author_id:
            logger.warning("SCHOLAR_AUTHOR_ID not set — auto-tracking disabled")
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not set — LLM features disabled")


settings = Settings()
