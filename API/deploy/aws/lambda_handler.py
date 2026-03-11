"""
AWS Lambda Handler
==================

Wraps the FastAPI app for AWS Lambda + API Gateway.

Uses 'mangum' — an adapter that translates between:
  - AWS Lambda event format (API Gateway request)
  - ASGI format (what FastAPI expects)

Install: pip install mangum
"""

import asyncio
import logging

# Mangum wraps FastAPI for Lambda
from mangum import Mangum

# Import your main FastAPI app
from main import app

logger = logging.getLogger(__name__)

# ── HTTP Handler (API Gateway → FastAPI) ──────────────────────────
# This handles all HTTP requests (Telegram webhook, /news, /trigger, etc.)
handler = Mangum(app, lifespan="off")


# ── Scheduled Handler (EventBridge → news job) ───────────────────
def scheduled_handler(event, context):
    """
    Called by AWS EventBridge on the cron schedule.
    Directly runs the news job without going through HTTP.
    """
    logger.info("EventBridge trigger received — running news job")

    async def run():
        from scheduler.jobs import run_news_job
        await run_news_job()

    asyncio.run(run())
    return {"statusCode": 200, "body": "News job completed"}
