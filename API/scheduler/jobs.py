"""
Scheduler — Auto-Trigger News Jobs
====================================

Automatically fetches and sends AI news on a schedule.

TWO ways to trigger news delivery:

  1. APScheduler (this file)
     - Runs inside the Python process
     - Good for always-on servers (VPS, VM)
     - Simple, no extra services needed

  2. External Scheduler (recommended for serverless/free tier)
     - GCP Cloud Scheduler → hits POST /trigger endpoint
     - AWS EventBridge    → hits POST /trigger endpoint
     - Better for Cloud Run / Lambda (you pay only when it runs)
     - No cost when idle (scales to zero!)

How to choose:
  - Local dev / VPS       → APScheduler (built-in, always running)
  - Cloud Run / Lambda    → External scheduler (serverless, cheaper)

Install: pip install APScheduler
Docs:    https://apscheduler.readthedocs.io/
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Create Scheduler ──────────────────────────────────────────────
# AsyncIOScheduler works with Python's asyncio event loop.
# This means it can run async functions directly.
# timezone="UTC" ensures consistent scheduling regardless of server location.

scheduler = AsyncIOScheduler(timezone="UTC")


# ── Main Job ──────────────────────────────────────────────────────

async def run_news_job() -> None:
    """
    Main scheduled job: fetch AI news and send it to Telegram.

    This function is called by:
    1. APScheduler (automatically, on schedule)
    2. The POST /trigger endpoint (manually or from Cloud Scheduler)

    Steps:
    1. Run the ADK agent to get formatted news
    2. Send it to the configured Telegram channel/chat
    3. Log errors and send an alert if something goes wrong
    """
    logger.info("=== Running daily news job ===")

    try:
        # Import inside function to avoid circular imports at module load
        from agent.agent import run_news_agent
        from bot.telegram_bot import send_news_to_channel

        # Step 1: Get AI-curated news via ADK agent
        logger.info("Step 1: Running ADK agent...")
        news_message = await run_news_agent()

        # Step 2: Send to Telegram
        logger.info("Step 2: Sending to Telegram channel...")
        await send_news_to_channel(news_message)

        logger.info("=== News job completed successfully ===")

    except Exception as e:
        logger.error(f"News job failed: {e}", exc_info=True)

        # Try to send an error notification to Telegram
        # (so you know something broke without checking logs)
        try:
            from bot.telegram_bot import send_news_to_channel
            error_msg = (
                f"⚠️ *Daily news job failed*\n\n"
                f"Error: `{str(e)[:300]}`\n\n"
                f"Check your server logs for details."
            )
            await send_news_to_channel(error_msg)
        except Exception:
            pass  # Don't raise — we don't want to crash on a notification failure


# ── Start Scheduler ───────────────────────────────────────────────

def start_scheduler() -> None:
    """
    Start the background scheduler.

    This runs in the same process as FastAPI.
    The job runs at the configured hour/minute every day.

    Called from main.py on startup.
    """
    scheduler.add_job(
        run_news_job,
        trigger=CronTrigger(
            hour=settings.schedule_hour,
            minute=settings.schedule_minute,
            timezone="UTC",
        ),
        id="daily_news",
        name="Daily AI News Delivery",
        replace_existing=True,   # Replace if already scheduled (after restart)
        misfire_grace_time=300,  # If job fires 5min late, still run it
    )

    scheduler.start()

    logger.info(
        f"Scheduler started — news job runs daily at "
        f"{settings.schedule_hour:02d}:{settings.schedule_minute:02d} UTC"
    )
