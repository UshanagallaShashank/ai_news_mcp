"""
Telegram Bot
============

The user-facing interface for the AI news bot.

Commands:
  /start   — Welcome message with instructions
  /ainews  — AI-curated news digest (uses Google ADK agent)
  /quick   — Quick news without AI (faster, useful as fallback)
  /sources — Show available news sources
  /help    — Show all commands

Architecture:
  - User sends /ainews to Telegram
  - Telegram sends the update to our webhook (or we poll in dev mode)
  - The handler calls the ADK agent
  - Agent fetches news, formats it, returns a message
  - We send it back to the user

Why python-telegram-bot?
  - Official Python wrapper for Telegram Bot API
  - Supports both webhook (production) and polling (development)
  - Well documented and actively maintained
  - Docs: https://python-telegram-bot.org/

Install: pip install python-telegram-bot
"""

import logging
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config.settings import settings
from agent.agent import run_news_agent
from scraper.news import scrape_news
from scraper.arxiv import fetch_arxiv_papers, ARXIV_CATEGORIES
from scraper.reddit import fetch_reddit_posts

logger = logging.getLogger(__name__)


# ── Build the Application ─────────────────────────────────────────
# Application is the main class in python-telegram-bot v21+
# Think of it like creating a Flask app — it wires everything together

application = (
    Application.builder()
    .token(settings.telegram_token)
    .build()
)


# ── Helper: Send Long Messages ────────────────────────────────────

async def send_long_message(
    chat_id: int | str,
    text: str,
    parse_mode: str = ParseMode.MARKDOWN,
) -> None:
    """
    Send a message to a chat, splitting into chunks if it's too long.

    Telegram's limit is 4096 characters per message.
    We split at newlines to keep formatting clean.

    Args:
        chat_id:    Telegram chat ID to send to
        text:       Message text (may be very long)
        parse_mode: "Markdown" or "HTML"
    """
    max_len = 4096

    if len(text) <= max_len:
        await application.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
        )
        return

    # Split into chunks at line breaks
    chunks: list[str] = []
    current = ""

    for line in text.split("\n"):
        candidate = current + "\n" + line if current else line
        if len(candidate) > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    for chunk in chunks:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=parse_mode,
            )
        except TelegramError as e:
            logger.error(f"Failed to send chunk: {e}")


# ── Command Handlers ──────────────────────────────────────────────
# Each handler is an async function that receives an Update object.
# Update contains info about the incoming message, user, chat, etc.

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — show welcome message."""
    text = (
        "👋 *Welcome to AI News Bot\\!*\n\n"
        "Latest AI news from 5 sources, free & real\\-time\\.\n\n"
        "*Commands:*\n"
        "/ainews           — AI\\-curated digest\n"
        "/quick            — Fast news, no AI\n"
        "/arxiv \\[topic\\]   — Research papers \\(ai/ml/nlp/cv\\)\n"
        "/reddit \\[sub\\]    — Community discussions\n"
        "/sources          — All news sources\n"
        "/help             — Full help\n\n"
        "Auto\\-sends every morning at 09:00 UTC 🌅\n\n"
        "_Built with Python · FastAPI · MCP · Google ADK_"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — show command list."""
    text = (
        "🤖 *AI News Bot Help*\n\n"
        "*/ainews* — AI\\-curated digest \\(10\\-30s\\)\n"
        "  Gemini ranks and summarizes top AI news\\.\n\n"
        "*/quick* — Fast news \\(2\\-5s, no AI\\)\n"
        "  Direct scrape from all sources\\.\n\n"
        "*/arxiv \\[topic\\]* — Research papers\n"
        "  Topics: ai, ml, nlp, cv, robotics\n"
        "  Example: /arxiv nlp\n\n"
        "*/reddit \\[subreddit\\]* — Community posts\n"
        "  Example: /reddit LocalLLaMA\n"
        "  Default: r/MachineLearning\n\n"
        "*/sources* — Show all sources\n\n"
        "*Auto\\-send:* Every day at 09:00 UTC\n\n"
        "_Tip: /quick if /ainews is slow_"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def ainews_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /ainews — fetch and deliver AI-curated news.

    Flow:
    1. Show loading message (user knows it's working)
    2. Run the ADK agent (may take 10-30 seconds)
    3. Delete loading message
    4. Send formatted news
    """
    loading_msg = await update.message.reply_text(
        "⏳ Fetching AI news\\.\\.\\. This takes 10\\-30 seconds\\.  Please wait\\!",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    try:
        # Run the ADK agent — this is where the magic happens
        # It fetches news, ranks it, and formats it with Gemini AI
        news_text = await run_news_agent()

        await loading_msg.delete()
        await send_long_message(update.effective_chat.id, news_text)

    except Exception as e:
        logger.error(f"Error in /ainews: {e}", exc_info=True)
        await loading_msg.edit_text(
            "❌ Failed to fetch news\\. Try /quick instead or try again later\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /quick — fast news without AI processing.

    Directly scrapes and formats articles.
    No AI = faster response but no intelligent summarization.
    """
    loading_msg = await update.message.reply_text("⚡ Fetching news quickly\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

    try:
        articles = await scrape_news(limit=settings.news_limit)

        if not articles:
            await loading_msg.edit_text(
                "❌ No articles found\\. Try again in a few minutes\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        # Build better formatted message
        date_str = _escape_md(str(__import__('datetime').date.today()))
        lines = [
            f"⚡ *Quick AI News*",
            f"📅 {date_str} • {len(articles)} articles",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        
        for i, article in enumerate(articles, start=1):
            # Emoji based on position
            emoji = "🔥" if i == 1 else "⭐" if i == 2 else "📌"
            lines.append(f"{emoji} *{i}\\. {_escape_md(article.title)}*")
            lines.append("")
            
            # Summary if available
            if article.summary:
                summary = article.summary[:150]
                if len(article.summary) > 150:
                    summary += "\\.\\.\\."
                lines.append(f"_{_escape_md(summary)}_")
                lines.append("")
            
            # Source with icon
            source_icons = {
                "Marktechpost": "📰",
                "HackerNews": "🔶",
                "DEV.to": "💻",
                "arXiv": "📄",
                "Reddit": "🔴"
            }
            icon = source_icons.get(article.source, "📰")
            src = _escape_md(article.source)
            date_part = f" • 📅 {_escape_md(article.date)}" if article.date else ""
            lines.append(f"{icon} {src}{date_part}")
            
            if article.url:
                lines.append(f"🔗 [Read full article]({article.url})")
            
            # Separator
            if i < len(articles):
                lines.append("")
                lines.append("─────────────────────────")
                lines.append("")

        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "⚡ _Quick mode \\(no AI curation\\)_",
            "",
            "🤖 /ainews • ℹ️ /help"
        ]

        message = "\n".join(lines)
        await loading_msg.delete()
        await send_long_message(update.effective_chat.id, message, parse_mode=ParseMode.MARKDOWN_V2)

    except Exception as e:
        logger.error(f"Error in /quick: {e}", exc_info=True)
        await loading_msg.edit_text(
            "❌ Scraping failed\\. Try again later\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def arxiv_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /arxiv [topic] — fetch latest research papers from Arxiv.

    Usage:
      /arxiv        → AI papers (default)
      /arxiv ml     → Machine Learning papers
      /arxiv nlp    → NLP / Language papers
      /arxiv cv     → Computer Vision papers
    """
    # Get topic from command args, e.g. "/arxiv nlp" → "nlp"
    topic = (context.args[0].lower() if context.args else "ai")
    valid_topics = list(ARXIV_CATEGORIES.keys())

    if topic not in valid_topics:
        await update.message.reply_text(
            f"Unknown topic\\. Use: {', '.join(valid_topics)}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    category = ARXIV_CATEGORIES[topic]
    loading_msg = await update.message.reply_text(
        f"🔬 Fetching Arxiv papers for *{_escape_md(topic.upper())}* \\({_escape_md(category)}\\)\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    try:
        papers = await fetch_arxiv_papers(topic=topic, limit=5)

        if not papers:
            await loading_msg.edit_text(
                "❌ No papers found\\. Try again in a few minutes\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        lines = [f"🔬 *Arxiv \u2014 {_escape_md(topic.upper())} Papers*\n"]
        for i, p in enumerate(papers, start=1):
            lines.append(f"*{i}\\. {_escape_md(p['title'])}*")
            if p.get("authors"):
                lines.append(f"👤 _{_escape_md(p['authors'][:60])}_")
            date_part = f" · {_escape_md(p['date'])}" if p.get("date") else ""
            lines.append(f"📰 Arxiv{date_part}")
            if p.get("url"):
                lines.append(f"🔗 [Read paper]({p['url']})")
            lines.append("")

        await loading_msg.delete()
        await send_long_message(
            update.effective_chat.id,
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    except Exception as e:
        logger.error(f"Error in /arxiv: {e}", exc_info=True)
        await loading_msg.edit_text("❌ Failed to fetch papers\\. Try again later\\.", parse_mode=ParseMode.MARKDOWN_V2)


async def reddit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /reddit [subreddit] — fetch top posts from a subreddit.

    Usage:
      /reddit                  → r/MachineLearning (default)
      /reddit LocalLLaMA       → r/LocalLLaMA
      /reddit artificial       → r/artificial
    """
    subreddit = (context.args[0] if context.args else "MachineLearning")

    loading_msg = await update.message.reply_text(
        f"💬 Fetching r/{_escape_md(subreddit)} top posts\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    try:
        posts = await fetch_reddit_posts(subreddit=subreddit, sort="top", time_filter="day", limit=5)

        if not posts:
            await loading_msg.edit_text(
                f"❌ No posts found in r/{_escape_md(subreddit)}\\. It may be private or empty\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        lines = [f"💬 *r/{_escape_md(subreddit)} \u2014 Today\\'s Top*\n"]
        for i, p in enumerate(posts, start=1):
            lines.append(f"*{i}\\. {_escape_md(p['title'])}*")
            score_text = _escape_md(f"⬆ {p['score']} · 💬 {p['comments']} comments")
            lines.append(score_text)
            date_part = f" · {_escape_md(p['date'])}" if p.get("date") else ""
            lines.append(f"📰 Reddit{date_part}")
            if p.get("url"):
                lines.append(f"🔗 [Open post]({p['url']})")
            lines.append("")

        await loading_msg.delete()
        await send_long_message(
            update.effective_chat.id,
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    except Exception as e:
        logger.error(f"Error in /reddit: {e}", exc_info=True)
        await loading_msg.edit_text("❌ Failed to fetch Reddit posts\\. Try again later\\.", parse_mode=ParseMode.MARKDOWN_V2)


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sources — show list of news sources."""
    text = (
        "📡 *News Sources*\n\n"
        "*Standard \\(/quick, /ainews\\):*\n"
        "1\\. *Marktechpost* — AI industry news \\(RSS\\)\n"
        "2\\. *HackerNews* — Tech community picks \\(Algolia API\\)\n"
        "3\\. *DEV\\.to* — Developer articles \\(Public API\\)\n\n"
        "*Research \\(/arxiv \\[topic\\]\\):*\n"
        "4\\. *Arxiv* — Research papers \\(cs\\.AI, cs\\.LG, cs\\.CL, cs\\.CV\\)\n"
        "   Topics: ai, ml, nlp, cv, robotics\n\n"
        "*Community \\(/reddit \\[sub\\]\\):*\n"
        "5\\. *Reddit* — Community discussions \\(JSON API\\)\n"
        "   Default: r/MachineLearning\n"
        "   Also try: r/LocalLLaMA, r/artificial\n\n"
        "_All free · No API keys required_"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# ── Utility: Escape Markdown V2 Special Characters ────────────────

def _escape_md(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    Required for: . ! - ( ) [ ] { } > # + = | ~
    """
    special_chars = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special_chars else c for c in text)


# ── Channel Send (used by scheduler) ─────────────────────────────

async def send_news_to_channel(message: str) -> None:
    """
    Send a news message to the configured Telegram channel/chat.

    Called by:
    - scheduler/jobs.py (daily auto-send)
    - The /trigger REST endpoint

    Args:
        message: Formatted news text (Markdown)
    """
    logger.info(f"Sending news to channel {settings.telegram_chat_id}")

    try:
        await send_long_message(
            chat_id=settings.telegram_chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info("News sent to channel successfully")
    except TelegramError as e:
        logger.error(f"Failed to send news to channel: {e}")
        raise


# ── Setup: Register Commands in Telegram ─────────────────────────

async def setup_bot_commands() -> None:
    """
    Register bot commands so they appear in Telegram's menu.
    Users see these when they type "/" in the chat.
    """
    commands = [
        BotCommand("ainews",  "AI-curated news digest"),
        BotCommand("quick",   "Fast news, no AI"),
        BotCommand("arxiv",   "Research papers — /arxiv [ai|ml|nlp|cv]"),
        BotCommand("reddit",  "Community posts — /reddit [subreddit]"),
        BotCommand("sources", "Show all news sources"),
        BotCommand("help",    "Show help and commands"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


# ── Register All Handlers ─────────────────────────────────────────

application.add_handler(CommandHandler("start",   start_command))
application.add_handler(CommandHandler("help",    help_command))
application.add_handler(CommandHandler("ainews",  ainews_command))
application.add_handler(CommandHandler("quick",   quick_command))
application.add_handler(CommandHandler("arxiv",   arxiv_command))
application.add_handler(CommandHandler("reddit",  reddit_command))
application.add_handler(CommandHandler("sources", sources_command))
