"""
MCP Server
==========

Exposes tools via the Model Context Protocol (MCP).

Any MCP-compatible client can connect and use these tools:
  - Claude Desktop  → add to claude_desktop_config.json
  - Cursor IDE      → add to .cursor/mcp.json
  - Any other project  → run standalone: python -m mcp_server

Transport: SSE (Server-Sent Events) over HTTP
  - Connect at: http://your-server/mcp/sse

Tools:
  1. scrape_ai_news(limit)              — Fetch latest AI articles (no AI)
  2. get_arxiv_papers(topic, limit)     — Latest research papers (no AI)
  3. get_reddit_posts(subreddit, limit) — Community hot posts (no AI)
  4. search_news(query, days_back)      — Search articles by keyword (no AI)
  5. get_news_summary(limit)            — Quick stats on available news (no AI)
  6. format_for_telegram(articles_json) — Format articles for Telegram (no AI)
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP

from scraper.news import scrape_news
from scraper.arxiv import fetch_arxiv_papers
from scraper.reddit import fetch_reddit_posts

logger = logging.getLogger(__name__)

# ── Create the MCP Server ─────────────────────────────────────────
mcp = FastMCP(
    name="ai-news-mcp-server",
    instructions=(
        "An MCP server for real-time AI/tech news. "
        "Sources: Marktechpost, HackerNews, DEV.to, Arxiv, Reddit. "
        "No AI required — all tools are pure data fetching and formatting. "
        "Use scrape_ai_news for general news, get_arxiv_papers for research, "
        "get_reddit_posts for community discussion, search_news to filter."
    ),
)


# ── Tool 1: Scrape AI News ────────────────────────────────────────

@mcp.tool()
async def scrape_ai_news(
    limit: int = 6,
    sources: str = "",
) -> str:
    """
    Fetch the latest AI/ML news from multiple sources. No AI used.

    Sources available: marktechpost, hackernews, devto
    Articles are deduplicated and filtered to last 7 days.

    Args:
        limit:   Number of articles to return (default: 6)
        sources: Comma-separated source names, or "" for all sources.
                 Example: "hackernews,devto"

    Returns:
        JSON: {"articles": [...], "count": N, "fetched_at": "ISO datetime"}
    """
    logger.info(f"[MCP] scrape_ai_news limit={limit} sources={sources!r}")

    source_list = [s.strip() for s in sources.split(",") if s.strip()] or None
    articles = await scrape_news(limit=limit, sources=source_list)

    result = {
        "articles": [a.to_dict() for a in articles],
        "count": len(articles),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(result, ensure_ascii=False)


# ── Tool 2: Arxiv Papers ──────────────────────────────────────────

@mcp.tool()
async def get_arxiv_papers(
    topic: str = "ai",
    limit: int = 5,
) -> str:
    """
    Fetch the latest research papers from Arxiv. No AI used.

    Updated daily by Arxiv. Great for staying current with research.

    Args:
        topic: One of "ai", "ml", "nlp", "cv", "robotics" (default: "ai")
               ai  = cs.AI  (Artificial Intelligence)
               ml  = cs.LG  (Machine Learning)
               nlp = cs.CL  (Natural Language Processing / Computation & Language)
               cv  = cs.CV  (Computer Vision)
               robotics = cs.RO (Robotics)
        limit: Number of papers to return (default: 5)

    Returns:
        JSON: {"papers": [{title, url, authors, summary, date, category}], "count": N}
    """
    logger.info(f"[MCP] get_arxiv_papers topic={topic} limit={limit}")

    papers = await fetch_arxiv_papers(topic=topic, limit=limit)

    return json.dumps({
        "papers": papers,
        "count": len(papers),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False)


# ── Tool 3: Reddit Posts ──────────────────────────────────────────

@mcp.tool()
async def get_reddit_posts(
    subreddit: str = "MachineLearning",
    sort: str = "top",
    time_filter: str = "day",
    limit: int = 5,
) -> str:
    """
    Fetch top posts from any public Reddit community. No AI used.

    Great for real-time community sentiment and discussions.

    Args:
        subreddit:   Subreddit name without r/ (default: "MachineLearning")
                     Popular: MachineLearning, artificial, LocalLLaMA,
                              programming, technology, datascience
        sort:        "hot", "top", or "new" (default: "top")
        time_filter: For sort=top: "hour", "day", "week", "month" (default: "day")
        limit:       Number of posts to return (default: 5)

    Returns:
        JSON: {"posts": [{title, url, subreddit, score, comments, date}], "count": N}
    """
    logger.info(f"[MCP] get_reddit_posts r/{subreddit} sort={sort} t={time_filter}")

    posts = await fetch_reddit_posts(
        subreddit=subreddit,
        sort=sort,
        time_filter=time_filter,
        limit=limit,
    )

    return json.dumps({
        "posts": posts,
        "count": len(posts),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False)


# ── Tool 4: Search News ───────────────────────────────────────────

@mcp.tool()
async def search_news(
    query: str,
    days_back: int = 7,
    limit: int = 10,
) -> str:
    """
    Search AI/ML news articles by keyword across all sources. No AI used.

    Fetches fresh articles then filters by your query.
    Case-insensitive. Matches title and summary.

    Args:
        query:     Search keyword or phrase (e.g. "GPT-4", "fine-tuning")
        days_back: Only include articles from this many days ago (default: 7)
        limit:     Max number of results to return (default: 10)

    Returns:
        JSON: {"query": "...", "articles": [...], "count": N}
    """
    logger.info(f"[MCP] search_news query={query!r} days={days_back}")

    # Fetch a wider pool then filter client-side
    articles = await scrape_news(limit=30)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    query_lower = query.lower()

    matched = []
    for a in articles:
        # Date filter
        if a.date:
            try:
                article_date = datetime.strptime(a.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if article_date < cutoff:
                    continue
            except ValueError:
                pass

        # Keyword filter — check title and summary
        text_to_search = f"{a.title} {a.summary or ''}".lower()
        if query_lower in text_to_search:
            matched.append(a.to_dict())

        if len(matched) >= limit:
            break

    return json.dumps({
        "query": query,
        "days_back": days_back,
        "articles": matched,
        "count": len(matched),
    }, ensure_ascii=False)


# ── Tool 5: Get News Summary ──────────────────────────────────────

@mcp.tool()
async def get_news_summary(limit: int = 10) -> str:
    """
    Get a quick overview of what AI news is currently available. No AI used.

    Useful for checking article counts per source before fetching.

    Args:
        limit: How many articles to check (default: 10)

    Returns:
        Plain text summary with counts per source and date range.
    """
    logger.info("[MCP] get_news_summary")

    articles = await scrape_news(limit=limit)

    source_counts: dict[str, int] = {}
    dates = []
    for a in articles:
        source_counts[a.source] = source_counts.get(a.source, 0) + 1
        if a.date:
            dates.append(a.date)

    lines = [f"Found {len(articles)} recent AI/ML articles:"]
    for source, count in sorted(source_counts.items()):
        lines.append(f"  • {source}: {count} article(s)")

    if dates:
        lines.append(f"Date range: {min(dates)} → {max(dates)}")

    return "\n".join(lines)


# ── Tool 6: Format for Telegram ───────────────────────────────────

@mcp.tool()
async def format_for_telegram(
    articles_json: str,
    title: str = "Daily AI News Digest",
    include_summary: bool = True,
) -> str:
    """
    Format news articles into a clean Telegram Markdown message. No AI used.

    Takes output from scrape_ai_news, get_arxiv_papers, or search_news.
    Handles both "articles" and "papers" keys.

    Args:
        articles_json:   JSON string from any fetch tool
        title:           Header shown at top of message
        include_summary: Whether to include article summaries (default: True)

    Returns:
        Formatted Markdown string safe to send via Telegram.
    """
    logger.info("[MCP] format_for_telegram")

    try:
        data = json.loads(articles_json)
        # Support both news articles ("articles") and arxiv papers ("papers")
        items = data.get("articles") or data.get("papers") or data.get("posts") or []
    except (json.JSONDecodeError, AttributeError) as e:
        return f"Error: Could not parse JSON — {e}"

    if not items:
        return "No articles available."

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"🤖 *{title}*",
        f"📅 {today}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, item in enumerate(items, start=1):
        item_title = item.get("title", "Untitled")
        url        = item.get("url", "")
        source     = item.get("source") or item.get("subreddit") or item.get("category") or "Unknown"
        summary    = item.get("summary") or item.get("abstract") or ""
        date       = item.get("date", "")
        authors    = item.get("authors", "")

        lines.append(f"*{i}. {item_title}*")

        if include_summary and summary:
            short = summary[:180] + "..." if len(summary) > 180 else summary
            lines.append(f"_{short}_")

        if authors:
            lines.append(f"👤 {authors[:80]}")

        meta = f"📰 {source}"
        if date:
            meta += f" · {date}"
        lines.append(meta)

        if url:
            lines.append(f"🔗 [Read more]({url})")

        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_Powered by AI News MCP Server_",
    ]

    return "\n".join(lines)
