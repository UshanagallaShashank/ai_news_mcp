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

    # Give the agent full summaries so it has enough context to write real insights.
    # We pass 250 chars — enough to understand the article without excessive tokens.
    data = [
        {
            "title": a.title,
            "source": a.source,
            "date": a.date or "",
            "url": a.url,
            "summary": (a.summary or "")[:250],
        }
        for a in articles
    ]

    return {
        "articles": data,
        "count": len(data),
        "sources": list({a.source for a in articles}),
    }


def format_for_telegram(
    articles: list[dict],
    header: str = "🤖 AI News Digest",
) -> str:
    """
    Format a list of articles into a beautiful Telegram-ready Markdown message.

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
        return "❌ No articles available right now. Try again later."

    # Get today's date for header
    from datetime import date
    today = date.today().strftime("%B %d, %Y")

    # Header with emoji and styling
    lines = [
        f"*{header}*",
        f"📅 {today} • {len(articles)} articles",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, article in enumerate(articles, start=1):
        title   = article.get("title", "Untitled")
        url     = article.get("url", "")
        source  = article.get("source", "Unknown")
        summary = article.get("summary", "")
        date_str = article.get("date", "")

        # Article number with priority emoji
        if i == 1:
            emoji = "🔥"
            priority = "TOP STORY"
        elif i == 2:
            emoji = "⭐"
            priority = "FEATURED"
        elif i == 3:
            emoji = "💎"
            priority = "TRENDING"
        else:
            emoji = "📌"
            priority = None

        # Title with priority badge
        if priority:
            lines.append(f"{emoji} *{i}. {title}*")
            lines.append(f"_`{priority}`_")
        else:
            lines.append(f"{emoji} *{i}. {title}*")
        lines.append("")

        # Enhanced summary with better formatting
        if summary:
            # Clean and format summary
            clean_summary = summary.strip()
            
            # Smart truncation at sentence or word boundary
            max_len = 250
            if len(clean_summary) > max_len:
                # Try to cut at sentence
                sentences = clean_summary[:max_len].split('. ')
                if len(sentences) > 1:
                    clean_summary = '. '.join(sentences[:-1]) + '.'
                else:
                    # Cut at word boundary
                    clean_summary = clean_summary[:max_len].rsplit(' ', 1)[0] + '...'
            
            # Format as quote-style
            lines.append(f"💬 _{clean_summary}_")
            lines.append("")

        # Metadata line with rich icons
        meta_parts = []
        
        # Source with specific icon
        source_icons = {
            "Marktechpost": "📰",
            "HackerNews": "🔶",
            "DEV.to": "�",
            "arXiv": "📄",
            "Reddit": "🔴"
        }
        icon = source_icons.get(source, "📰")
        meta_parts.append(f"{icon} *{source}*")
        
        # Date with icon
        if date_str:
            meta_parts.append(f"📅 {date_str}")
        
        lines.append(" • ".join(meta_parts))

        # Call-to-action link with better text
        if url:
            lines.append(f"🔗 [📖 Read Full Article →]({url})")

        # Visual separator between articles
        if i < len(articles):
            lines.append("")
            lines.append("─────────────────────────")
            lines.append("")

    # Rich footer with actions
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 _Curated by AI • Powered by Google Gemini_",
        "",
        "🔄 Refresh: /ainews",
        "⚡ Quick Mode: /quick",
        "ℹ️ Help: /help",
        "📡 Sources: /sources"
    ]

    return "\n".join(lines)


# ── Formatter ────────────────────────────────────────────────────

def _escape_md1(text: str) -> str:
    """Escape Telegram Markdown v1 special chars."""
    for c in ['*', '_', '[', ']', '`']:
        text = text.replace(c, '\\' + c)
    return text


def _format_ai_news(articles: list[dict]) -> str:
    """Format AI-curated articles into a Telegram message (Markdown v1)."""
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")

    source_icons = {
        "Marktechpost": "📰", "HackerNews": "🔶",
        "DEV.to": "💻", "arXiv": "📄", "Reddit": "🔴",
    }

    lines = [
        "🤖 *AI News Digest*",
        f"📅 {today} • {len(articles)} articles",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, a in enumerate(articles, start=1):
        emoji = "🔥" if i == 1 else "⭐" if i == 2 else "📌"
        title    = _escape_md1(a.get("title", "Untitled"))
        source   = a.get("source", "Unknown")
        date_str = a.get("date", "")
        url      = a.get("url", "")
        analysis = a.get("analysis", "")

        lines.append(f"{emoji} *{i}. {title}*")
        lines.append("")

        if analysis:
            lines.append(f"_{_escape_md1(analysis.strip())}_")
            lines.append("")

        icon = source_icons.get(source, "📰")
        date_part = f" • 📅 {date_str}" if date_str else ""
        lines.append(f"{icon} {_escape_md1(source)}{date_part}")

        if url:
            lines.append(f"🔗 [Read full article]({url})")

        if i < len(articles):
            lines.append("")
            lines.append("─────────────────────────")
            lines.append("")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "_Curated by Gemini AI · /quick for raw feed · /help for commands_",
    ]
    return "\n".join(lines)


# ── Create the ADK Agent ──────────────────────────────────────────
# The Agent object is the core of ADK.
# It combines a Gemini model with tools and instructions.

news_agent = Agent(
    name="ai_news_agent",
    model="gemini-2.5-flash-lite",
    description="AI news curator that writes insightful analysis of AI/ML news for Telegram.",
    instruction="""You are an AI news analyst. Your job: curate and analyze AI/ML news.

STEP 1: Call fetch_latest_news to get articles.

STEP 2: Return ONLY a JSON array. No other text, no markdown fences.

Each object in the array must have exactly these fields:
- title: article title (string)
- url: article url (string)
- source: source name (string)
- date: date string (string)
- analysis: 2-3 sentences of YOUR OWN insight — why it matters, what is novel, real-world impact. Do NOT restate the summary. Be dense and useful.

Example output format:
[{"title":"...", "url":"...", "source":"...", "date":"...", "analysis":"..."}]

RULES:
- Return ONLY the JSON array, nothing else
- Your own analysis, not copied summaries
- Prioritize: model releases, benchmarks, research breakthroughs, tools""",
    tools=[fetch_latest_news],
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
        prompt = f"Fetch the latest {settings.news_limit} AI news articles and write the newsletter."

    # Each run gets its own session (fresh context)
    # Using a unique session ID based on a counter keeps things clean
    import time
    session_id = f"news_{int(time.time())}"

    try:
        # Create a new session for this run
        _session_service.create_session(
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
        total_input_tokens = 0
        total_output_tokens = 0

        async for event in runner.run_async(
            user_id="system",
            session_id=session_id,
            new_message=user_message,
        ):
            # Accumulate token usage from every event that has it
            usage = getattr(event, "usage_metadata", None)
            if usage:
                total_input_tokens  += getattr(usage, "prompt_token_count", 0) or 0
                total_output_tokens += getattr(usage, "candidates_token_count", 0) or 0

            # Check if this event has text content
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_response = part.text
                        
            # Once we see the final response, stop updating (but let generator exhaust)
            # Do NOT break — breaking causes GeneratorExit which triggers an
            # OpenTelemetry context detach error ("Token was created in a different Context")

        if total_input_tokens or total_output_tokens:
            logger.info(
                f"[Tokens] input={total_input_tokens} "
                f"output={total_output_tokens} "
                f"total={total_input_tokens + total_output_tokens}"
            )

        if final_response:
            logger.info("ADK agent completed successfully")
            import json
            # Strip markdown code fences if the model wrapped the JSON
            text = final_response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            articles = json.loads(text)
            return _format_ai_news(articles)
        else:
            logger.warning("ADK agent completed but returned no text response")

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
