"""
Main Application Entry Point
=============================

This is the FastAPI server — the backbone of the entire system.

What runs here:
  1. FastAPI HTTP server       — REST API endpoints
  2. MCP Server (at /mcp)     — For AI clients like Claude Desktop, Cursor
  3. Telegram webhook handler  — Receives updates from Telegram

How to run:
  Production:  uvicorn main:app --host 0.0.0.0 --port 8080
  Development: python dev.py   (uses polling instead of webhook)

Environment:
  Set WEBHOOK_URL for production (webhook mode)
  Leave it empty for dev (handled by dev.py)

FastAPI docs:  https://fastapi.tiangolo.com/
Uvicorn docs:  https://www.uvicorn.org/
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config.settings import settings
from mcp_server.server import mcp
from bot.telegram_bot import application as telegram_app, setup_bot_commands

# ── Logging ───────────────────────────────────────────────────────
# Configure logging early so we see all startup messages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan: Startup & Shutdown ──────────────────────────────────
# @asynccontextmanager turns this into a "startup/shutdown" hook for FastAPI.
# Code before `yield` runs on startup.
# Code after `yield` runs on shutdown.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────
    logger.info("Starting News MCP Server...")

    # Initialize the Telegram bot application
    await telegram_app.initialize()
    await telegram_app.start()
    await setup_bot_commands()

    if settings.webhook_url:
        # PRODUCTION mode: Telegram sends updates TO our server
        webhook_url = f"{settings.webhook_url}/telegram/webhook"
        await telegram_app.bot.set_webhook(url=webhook_url)
        logger.info(f"Telegram webhook registered: {webhook_url}")
    else:
        # DEV mode is handled by dev.py (polling)
        # Here we just skip webhook setup
        logger.info(
            "No WEBHOOK_URL set — Telegram updates won't arrive via webhook. "
            "Run dev.py for local development with polling."
        )

    logger.info("Server ready!")

    yield  # ← Server runs here, handling requests

    # ── SHUTDOWN ──────────────────────────────
    logger.info("Shutting down...")
    await telegram_app.stop()
    await telegram_app.shutdown()
    logger.info("Shutdown complete")


# ── Create FastAPI App ────────────────────────────────────────────

app = FastAPI(
    title="News MCP Server",
    description=(
        "News bot backend.\n\n"
        "**MCP Server**: AI clients connect at `/mcp/sse`\n"
        "**Telegram**: Webhook at `/telegram/webhook`\n"
        "**REST API**: Direct access at `/news`"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ── Mount MCP Server ──────────────────────────────────────────────
# Streamable HTTP transport — works with Cloud Run and Claude Code
# Claude Code connects to: https://your-app.run.app/mcp/

app.mount("/mcp", mcp.streamable_http_app())


# ── REST API Endpoints ────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint.

    Used by:
    - Cloud Run / load balancers to verify the server is alive
    - Monitoring tools
    - Quick sanity check

    Returns 200 OK if the server is running.
    """
    return {
        "status": "healthy",
        "service": "news-mcp-server",
        "version": "1.0.0",
    }


@app.get("/news", tags=["News"])
async def get_news(
    limit: int = 5,
    sources: str = "marktechpost,hackernews,devto",
):
    """
    Fetch news directly via REST API.

    Useful for:
    - Testing the scraper
    - Building other integrations
    - Checking what articles are available

    Args:
        limit:   Number of articles (1-20)
        sources: Comma-separated list: "marktechpost,hackernews"

    Returns:
        JSON with articles list
    """
    from scraper.news import scrape_news

    limit = max(1, min(20, limit))
    source_list = [s.strip() for s in sources.split(",")]

    articles = await scrape_news(limit=limit, sources=source_list)

    return {
        "count": len(articles),
        "sources": source_list,
        "articles": [a.to_dict() for a in articles],
    }


# ── Telegram Webhook Endpoint ─────────────────────────────────────

@app.post("/telegram/webhook", tags=["Telegram"])
async def telegram_webhook(request: Request):
    """
    Receive Telegram bot updates via webhook.

    When a user sends a message to your bot, Telegram calls this URL.
    We parse the update and pass it to the bot's handler functions.

    This only works when WEBHOOK_URL is set.
    For local dev, use dev.py (polling mode).
    """
    try:
        data = await request.json()

        from telegram import Update
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)

        return JSONResponse(content={"ok": True})

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "error": str(e)},
            status_code=500,
        )


# ── Run the Server ────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,       # Never use reload=True in production
        log_level="info",
        workers=1,          # Keep at 1 — scheduler and telegram app aren't fork-safe
    )
