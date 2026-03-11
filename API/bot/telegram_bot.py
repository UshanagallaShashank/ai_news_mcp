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
        "👋 *Welcome to AI News Bot!*\n\n"
        "I deliver the latest AI & machine learning news, curated by Gemini AI.\n\n"
        "*Commands:*\n"
        "/ainews  — AI\\-curated news digest \\(10\\-30 sec\\)\n"
        "/quick   — Fast news without AI\n"
        "/sources — List news sources\n"
        "/help    — Show this message\n\n"
        "I also send news *automatically every morning* 🌅\n\n"
        "_Built with Python · FastAPI · MCP · Google ADK_"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — show command list."""
    text = (
        "🤖 *AI News Bot Help*\n\n"
        "*/ainews* — Full AI digest\n"
        "  Uses Google ADK \\+ Gemini to fetch, rank,\n"
        "  and summarize the most important AI news\\.\n"
        "  Takes 10\\-30 seconds\\.\n\n"
        "*/quick* — Fast news\n"
        "  Direct scraping, no AI processing\\.\n"
        "  Results in 2\\-5 seconds\\.\n\n"
        "*/sources* — Show news sources\n\n"
        "*Auto\\-send:* Every day at 09:00 UTC\n\n"
        "_Tip: Use /quick if /ainews is slow_"
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

        lines = ["📰 *Quick AI News*\n"]
        for i, article in enumerate(articles, start=1):
            lines.append(f"*{i}\\. {_escape_md(article.title)}*")
            lines.append(f"📰 {article.source}")
            if article.url:
                lines.append(f"🔗 [Read more]({article.url})")
            lines.append("")

        message = "\n".join(lines)
        await loading_msg.delete()
        await send_long_message(update.effective_chat.id, message, parse_mode=ParseMode.MARKDOWN_V2)

    except Exception as e:
        logger.error(f"Error in /quick: {e}", exc_info=True)
        await loading_msg.edit_text(
            "❌ Scraping failed\\. Try again later\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sources — show list of news sources."""
    text = (
        "📡 *News Sources*\n\n"
        "1\\. *Marktechpost* \\(RSS\\)\n"
        "   AI/ML research papers and industry news\n"
        "   _marktechpost\\.com_\n\n"
        "2\\. *HackerNews* \\(Algolia API\\)\n"
        "   Tech community discussions about AI\n"
        "   _news\\.ycombinator\\.com_\n\n"
        "3\\. *DEV\\.to* \\(Public API\\)\n"
        "   Developer AI articles and tutorials\n"
        "   _dev\\.to_\n\n"
        "_All free · No API keys · Cached 30 min_"
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
        BotCommand("ainews", "Get AI-curated news digest"),
        BotCommand("quick",  "Quick news without AI (faster)"),
        BotCommand("sources", "Show news sources"),
        BotCommand("help",   "Show help and commands"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


# ── Register All Handlers ─────────────────────────────────────────
# Map each command string to its handler function

application.add_handler(CommandHandler("start",   start_command))
application.add_handler(CommandHandler("help",    help_command))
application.add_handler(CommandHandler("ainews",  ainews_command))
application.add_handler(CommandHandler("quick",   quick_command))
application.add_handler(CommandHandler("sources", sources_command))
