"""
Settings / Configuration
========================

All configuration lives here.
Values come from environment variables (loaded from .env file).

Why pydantic-settings?
- Validates types automatically  (e.g. "8080" string → 8080 int)
- Gives clear error if a required variable is missing
- Documents all config in one place

Usage:
    from config.settings import settings
    print(settings.telegram_token)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """
    All app settings.
    Set these in your .env file for local development.
    Set as environment variables in GCP / AWS for production.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars (safe to have extras)
    )

    # ── Telegram ───────────────────────────────────────────────────
    # Get from: @BotFather on Telegram → /newbot
    telegram_token: str

    # Where to send auto news updates (channel, group, or your user ID)
    # Get your user ID from: @userinfobot on Telegram
    # For channels: -100xxxxxxxxxx (note the -100 prefix)
    telegram_chat_id: str

    # ── App Server ─────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8080

    # ── Webhook (production) ───────────────────────────────────────
    # Your public HTTPS URL (e.g. https://your-app.run.app)
    # Leave empty for local development (will use polling instead)
    webhook_url: Optional[str] = None

    # ── News Scraping ──────────────────────────────────────────────
    # Sources: "marktechpost" (RSS feed), "hackernews" (API), "devto" (API)
    news_limit: int = 6          # 6 total = 2 from each of the 3 sources
    news_cache_ttl: int = 1800   # Cache articles for 30 minutes (seconds)


# Single instance used across the entire app
# Import this everywhere: `from config.settings import settings`
settings = Settings()
