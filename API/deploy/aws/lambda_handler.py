"""
AWS Lambda Handler
==================

Wraps the FastAPI app for AWS Lambda + API Gateway.

Uses 'mangum' — an adapter that translates between:
  - AWS Lambda event format (API Gateway request)
  - ASGI format (what FastAPI expects)

Install: pip install mangum
"""

import logging

# Mangum wraps FastAPI for Lambda
from mangum import Mangum

# Import your main FastAPI app
from main import app

logger = logging.getLogger(__name__)

# ── HTTP Handler (API Gateway → FastAPI) ──────────────────────────
# This handles all HTTP requests (Telegram webhook, /news, etc.)
handler = Mangum(app, lifespan="off")
