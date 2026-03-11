"""
MCP Server (Python)
===================

This is a Model Context Protocol (MCP) server.
Think of it like a plugin store for AI models.

What MCP Does:
  - Exposes "tools" that ANY MCP-compatible AI can discover and call
  - Tools run HERE on the server, not inside the AI model
  - The AI just decides WHEN to call them and WHAT arguments to pass

Who can connect to this MCP server?
  - Claude Desktop  (Add to claude_desktop_config.json)
  - Cursor IDE      (Add to .cursor/mcp.json)
  - Your Telegram bot  (via the ADK agent)
  - Any MCP-compatible client

Transport: SSE (Server-Sent Events) over HTTP
  - MCP clients connect to: http://your-server/mcp/sse
  - This is more flexible than stdio (works over the internet)

Tools exposed:
  1. scrape_ai_news      — Fetch latest AI articles
  2. format_for_telegram — Format articles as Telegram message
  3. get_news_summary    — Quick stats about available articles

Install: pip install mcp
Docs: https://modelcontextprotocol.io/
"""

import json
import logging

from mcp.server.fastmcp import FastMCP

from scraper.news import scrape_news

logger = logging.getLogger(__name__)


# ── Create the MCP Server ─────────────────────────────────────────
# FastMCP wraps the MCP SDK to make it easier to use.
# It's like creating a FastAPI app, but for the MCP protocol.

mcp = FastMCP(
    name="ai-news-mcp-server",
    instructions=(
        "An MCP server that scrapes and delivers AI/ML news from "
        "Marktechpost and HackerNews. Tools: scrape_ai_news, "
        "format_for_telegram, get_news_summary."
    ),
)


# ── Tool 1: Scrape AI News ────────────────────────────────────────
# The @mcp.tool() decorator registers this function as an MCP tool.
# The docstring becomes the tool's description (AI models read this!).
# The type hints become the tool's input schema.

@mcp.tool()
async def scrape_ai_news(limit: int = 5) -> str:
    """
    Scrapes the latest AI and machine learning news from multiple sources.

    Sources:
    - Marktechpost: AI research papers and industry news
    - HackerNews: Tech community discussions about AI

    Args:
        limit: Number of articles to fetch (default: 5, max recommended: 10)

    Returns:
        JSON string containing:
        {
            "articles": [
                {
                    "title": "...",
                    "url": "...",
                    "source": "Marktechpost" | "HackerNews",
                    "summary": "...",
                    "date": "YYYY-MM-DD"
                }
            ],
            "count": 5
        }
    """
    logger.info(f"[MCP] scrape_ai_news called — limit={limit}")

    articles = await scrape_news(limit=limit)

    result = {
        "articles": [a.to_dict() for a in articles],
        "count": len(articles),
    }

    logger.info(f"[MCP] Returning {len(articles)} articles")
    return json.dumps(result, ensure_ascii=False)


# ── Tool 2: Format for Telegram ───────────────────────────────────

@mcp.tool()
async def format_for_telegram(
    articles_json: str,
    title: str = "Daily AI News Digest",
    include_summary: bool = True,
) -> str:
    """
    Formats a list of news articles into a clean Telegram message.

    Telegram supports a subset of Markdown:
    - *bold*  _italic_  `code`  [text](url)

    Args:
        articles_json:   JSON string from scrape_ai_news tool
        title:           Header shown at the top of the message
        include_summary: Whether to include article summaries (default: True)

    Returns:
        Formatted string ready to send via Telegram Bot API
    """
    logger.info("[MCP] format_for_telegram called")

    try:
        data = json.loads(articles_json)
        articles = data.get("articles", [])
    except (json.JSONDecodeError, AttributeError) as e:
        return f"Error: Could not parse articles JSON — {e}"

    if not articles:
        return "No articles available."

    lines = [
        f"🤖 *{title}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, article in enumerate(articles, start=1):
        article_title = article.get("title", "Untitled")
        url = article.get("url", "")
        source = article.get("source", "Unknown")
        summary = article.get("summary", "")
        date = article.get("date", "")

        lines.append(f"*{i}. {article_title}*")

        if include_summary and summary:
            # Keep summaries short for readability
            short = summary[:200] + "..." if len(summary) > 200 else summary
            lines.append(f"_{short}_")

        source_line = f"📰 {source}"
        if date:
            source_line += f" · {date}"
        lines.append(source_line)

        if url:
            lines.append(f"🔗 [Read more]({url})")

        lines.append("")  # Blank line between articles

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_Powered by AI News MCP Server · Google ADK_",
    ]

    return "\n".join(lines)


# ── Tool 3: Get News Summary ──────────────────────────────────────

@mcp.tool()
async def get_news_summary(limit: int = 10) -> str:
    """
    Get a quick overview of what news is currently available.

    Useful for checking how many articles are available before
    deciding how many to fetch with scrape_ai_news.

    Args:
        limit: How many articles to check (default: 10)

    Returns:
        Plain text summary with counts per source
    """
    logger.info("[MCP] get_news_summary called")

    articles = await scrape_news(limit=limit)

    # Count articles per source
    source_counts: dict[str, int] = {}
    for article in articles:
        source_counts[article.source] = source_counts.get(article.source, 0) + 1

    lines = [f"Found {len(articles)} recent AI/ML articles:"]
    for source, count in sorted(source_counts.items()):
        lines.append(f"  • {source}: {count} article(s)")

    return "\n".join(lines)
