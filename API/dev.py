"""
Development Runner
==================

Use this for LOCAL DEVELOPMENT only.

Differences from main.py (production):
  - Uses Telegram POLLING instead of webhook
    (No public URL needed — bot asks Telegram for updates every second)
  - No APScheduler (run manually with: curl -X POST localhost:8080/trigger)
  - Runs FastAPI + Telegram polling simultaneously

How to use:
  1. Copy .env.example to .env
  2. Fill in GOOGLE_API_KEY and TELEGRAM_TOKEN
  3. Leave WEBHOOK_URL empty
  4. Run: python dev.py

You'll see:
  - FastAPI server at http://localhost:8080
  - MCP server at http://localhost:8080/mcp/sse
  - API docs at http://localhost:8080/docs
  - Telegram bot responding to your commands

To test in Telegram: open your bot and send /ainews
To test the API:     curl http://localhost:8080/news
To test MCP:         connect Claude Desktop to http://localhost:8080/mcp/sse

Note: For Telegram to work on free ngrok / no public URL, use polling mode.
Polling works perfectly for development but isn't recommended for production
(it creates constant HTTP requests to Telegram's servers).
"""

import asyncio
import logging
import threading

import uvicorn
from telegram.ext import Application

from config.settings import settings
from bot.telegram_bot import application as telegram_app, setup_bot_commands
from mcp_server.server import mcp

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── FastAPI App (lighter version for dev) ─────────────────────────
# Import only what we need, skip webhook and scheduler setup

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse


@asynccontextmanager
async def dev_lifespan(app: FastAPI):
    """Dev-only startup: no webhook, no scheduler."""
    logger.info("[DEV] Starting FastAPI (dev mode)...")
    yield
    logger.info("[DEV] FastAPI shutting down...")


dev_app = FastAPI(
    title="AI News Bot (Dev Mode)",
    description="Development server — Telegram polling mode",
    version="1.0.0-dev",
    lifespan=dev_lifespan,
)

# Mount MCP server so you can test with Claude Desktop locally
dev_app.mount("/mcp", mcp.sse_app())


@dev_app.get("/health")
async def health():
    return {"status": "healthy", "mode": "development"}


@dev_app.get("/news")
async def get_news(limit: int = 5):
    from scraper.news import scrape_news
    articles = await scrape_news(limit=limit)
    return {"count": len(articles), "articles": [a.to_dict() for a in articles]}


@dev_app.post("/trigger")
async def manual_trigger():
    """Manually run the news job for testing."""
    from scheduler.jobs import run_news_job
    asyncio.create_task(run_news_job())
    return {"status": "triggered"}


# ── Run Everything ────────────────────────────────────────────────

async def run_telegram_polling():
    """Run Telegram bot with polling in the same asyncio loop."""
    logger.info("[DEV] Starting Telegram bot (polling mode)...")
    await telegram_app.initialize()
    await setup_bot_commands()
    await telegram_app.start()
    await telegram_app.updater.start_polling(
        allowed_updates=["message"],
        drop_pending_updates=True,   # Ignore messages sent while bot was offline
    )
    logger.info("[DEV] Telegram bot polling — send /ainews to your bot!")


async def main():
    """Start FastAPI and Telegram polling concurrently."""

    # Create uvicorn server config (non-blocking)
    config = uvicorn.Config(
        app=dev_app,
        host="0.0.0.0",
        port=settings.app_port,
        log_level="info",
        reload=False,
    )
    server = uvicorn.Server(config)

    # Run both FastAPI and Telegram polling in the same event loop
    await asyncio.gather(
        server.serve(),
        run_telegram_polling(),
    )


if __name__ == "__main__":
    print("\n" + "="*50)
    print("  AI News Bot — Development Mode")
    print("="*50)
    print(f"  API:      http://localhost:{settings.app_port}")
    print(f"  API docs: http://localhost:{settings.app_port}/docs")
    print(f"  MCP SSE:  http://localhost:{settings.app_port}/mcp/sse")
    print(f"  News API: http://localhost:{settings.app_port}/news")
    print(f"  Trigger:  POST http://localhost:{settings.app_port}/trigger")
    print("="*50 + "\n")

    asyncio.run(main())
