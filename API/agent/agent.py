"""
Google ADK Agent
================

This is the AI "brain" of the news bot.

What is Google ADK?
  - Agent Development Kit by Google
  - Makes it easy to build AI agents using Gemini models
  - An "agent" can use tools, reason about what to do, and chain steps
  - Docs: https://google.github.io/adk-docs/

How this agent works:
  1. You give it a prompt: "fetch and format today's AI news"
  2. It calls fetch_latest_news() tool to get articles
  3. It reads the articles and picks the most interesting ones
  4. It calls format_for_telegram() to create a nice message
  5. It returns the final formatted message

Why use an Agent instead of just calling functions directly?
  - The AI adds value: it summarizes themes, ranks by importance
  - It can handle varied prompts: "give me 3 articles about LLMs"
  - It's the right abstraction for a resume project showcasing AI

Install: pip install google-adk
Docs:    https://google.github.io/adk-docs/get-started/quickstart/
"""

import logging
import os
from typing import Optional

# ── Google ADK Imports ─────────────────────────────────────────────
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# ── Our scraper ────────────────────────────────────────────────────
from scraper.news import scrape_news, Article
from config.settings import settings

logger = logging.getLogger(__name__)

# Make sure Google AI API key is set for ADK to use
os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
os.environ.setdefault(
    "GOOGLE_GENAI_USE_VERTEXAI",
    "TRUE" if settings.google_genai_use_vertexai else "FALSE",
)


# ── Tool Functions ─────────────────────────────────────────────────
# These are Python functions the ADK agent can call.
# ADK reads the docstrings to understand what each tool does.
# Type hints tell ADK what arguments are expected.

async def fetch_latest_news(limit: int = 5) -> dict:
    """
    Fetch the latest AI and machine learning news articles.

    Scrapes from Marktechpost and HackerNews.
    Results are cached for 30 minutes to avoid overloading sites.

    Args:
        limit: Number of articles to fetch (between 1 and 10)

    Returns:
        Dictionary with:
        - articles: list of article dicts (title, url, source, summary, date)
        - count: total number of articles found
        - sources: list of source names used
    """
    # Clamp limit to a reasonable range
    limit = max(1, min(10, limit))

    logger.info(f"[Agent Tool] fetch_latest_news — limit={limit}")
    articles = await scrape_news(limit=limit)

    return {
        "articles": [a.to_dict() for a in articles],
        "count": len(articles),
        "sources": list({a.source for a in articles}),
    }


def format_for_telegram(
    articles: list[dict],
    header: str = "Daily AI News Digest",
) -> str:
    """
    Format a list of articles into a Telegram-ready Markdown message.

    Telegram Markdown rules:
    - *bold*  _italic_  `code`  [link text](url)
    - Max 4096 characters per message

    Args:
        articles: List of article dicts from fetch_latest_news
        header:   Title shown at top of message

    Returns:
        Formatted string safe to send via Telegram
    """
    if not articles:
        return "No articles available right now. Try again later."

    lines = [
        f"🤖 *{header}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, article in enumerate(articles, start=1):
        title   = article.get("title", "Untitled")
        url     = article.get("url", "")
        source  = article.get("source", "Unknown")
        summary = article.get("summary", "")
        date    = article.get("date", "")

        lines.append(f"*{i}. {title}*")

        if summary:
            short = summary[:180] + "..." if len(summary) > 180 else summary
            lines.append(f"_{short}_")

        meta = f"📰 {source}"
        if date:
            meta += f" · {date}"
        lines.append(meta)

        if url:
            lines.append(f"🔗 [Read more]({url})")

        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_Powered by AI News Bot · Google ADK + Gemini_",
    ]

    return "\n".join(lines)


# ── Create the ADK Agent ──────────────────────────────────────────
# The Agent object is the core of ADK.
# It combines a Gemini model with tools and instructions.

news_agent = Agent(
    name="ai_news_agent",
    model="gemini-2.0-flash",   # Fast and free-tier friendly
    description=(
        "An AI news curator that fetches, summarizes, and delivers "
        "AI/ML news via Telegram."
    ),
    instruction="""
    You are an AI news curator helping developers and tech enthusiasts
    stay up-to-date with artificial intelligence and machine learning.

    When asked to fetch and deliver news:
    1. Call fetch_latest_news to get articles (use the requested limit)
    2. Review the articles and identify the most important/interesting ones
    3. Call format_for_telegram with the selected articles
    4. Add a brief 1-2 sentence "today's theme" summary at the top if relevant
    5. Return the formatted message

    Guidelines:
    - Be concise and informative
    - Prioritize breakthrough research, new model releases, and industry news
    - Keep the tone professional but accessible to beginners
    - If asked for a specific topic (e.g., "LLMs only"), filter articles accordingly
    """,
    tools=[fetch_latest_news, format_for_telegram],
)


# ── Session Service ───────────────────────────────────────────────
# Sessions store conversation history so the agent remembers context.
# InMemorySessionService: stored in RAM (resets on restart)
# For production, you'd use a persistent session service (database).

_session_service = InMemorySessionService()


# ── Runner: How to Run the Agent ──────────────────────────────────

async def run_news_agent(prompt: Optional[str] = None) -> str:
    """
    Run the ADK news agent and return a formatted Telegram message.

    This is the main function called by:
    - The Telegram bot (/ainews command)
    - The scheduler (daily auto-send)
    - The /trigger REST endpoint

    Args:
        prompt: Custom instruction. Default: fetch and format today's news.

    Returns:
        Formatted news message ready to send to Telegram.
        Falls back to direct formatting if the agent fails.
    """
    if prompt is None:
        prompt = (
            f"Please fetch the latest {settings.news_limit} AI news articles. "
            "Summarize the overall theme in 1 sentence, then format the articles "
            "nicely for Telegram."
        )

    # Each run gets its own session (fresh context)
    # Using a unique session ID based on a counter keeps things clean
    import time
    session_id = f"news_{int(time.time())}"

    try:
        # Create a new session for this run
        await _session_service.create_session(
            app_name="ai_news_bot",
            user_id="system",
            session_id=session_id,
        )

        # Runner connects the agent, session, and model together
        runner = Runner(
            agent=news_agent,
            app_name="ai_news_bot",
            session_service=_session_service,
        )

        # Wrap the prompt in the format ADK expects
        user_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)],
        )

        logger.info(f"Running ADK agent — session={session_id}")

        final_response = ""

        # Process events from the agent
        # The agent may call tools multiple times before giving a final answer
        async for event in runner.run_async(
            user_id="system",
            session_id=session_id,
            new_message=user_message,
        ):
            # is_final_response() is True when the agent is done
            if event.is_final_response():
                if event.content and event.content.parts:
                    final_response = event.content.parts[0].text
                break

        if final_response:
            logger.info("ADK agent completed successfully")
            return final_response

    except Exception as e:
        logger.error(f"ADK agent failed: {e}")

    # ── Fallback: Format without AI ───────────────────────────────
    # If ADK fails (quota, network, etc.), we still send news
    # Just without the AI summarization layer
    logger.warning("Using fallback: direct formatting without ADK")

    articles_data = await fetch_latest_news(settings.news_limit)
    return format_for_telegram(
        articles_data["articles"],
        header="Daily AI News Digest",
    )
