"""
Reddit Scraper
==============

Fetches top posts from any public subreddit using Reddit's JSON API.

URL pattern: https://www.reddit.com/r/{subreddit}/{sort}.json

Why Reddit?
- No API key required for public subreddit JSON (just need a User-Agent)
- Real-time community discussions, not just news articles
- Great for: r/MachineLearning, r/artificial, r/LocalLLaMA, r/programming
- sort=top&t=day gives the best posts from last 24 hours

No authentication required.
"""

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────
_cache: dict[str, tuple[list[dict], float]] = {}
CACHE_TTL = 900  # 15 min — Reddit updates frequently


def _cache_get(key: str) -> Optional[list[dict]]:
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
    return None


def _cache_set(key: str, data: list[dict]) -> None:
    _cache[key] = (data, time.time())


# ── Good subreddits for AI/tech content ───────────────────────────
POPULAR_SUBREDDITS = [
    "MachineLearning",
    "artificial",
    "LocalLLaMA",
    "programming",
    "technology",
    "datascience",
]


async def fetch_reddit_posts(
    subreddit: str = "MachineLearning",
    sort: str = "top",          # hot | top | new
    time_filter: str = "day",   # hour | day | week | month (only for 'top')
    limit: int = 5,
) -> list[dict]:
    """
    Fetch top posts from a public subreddit.

    Args:
        subreddit:   Subreddit name without r/ (e.g. "MachineLearning")
        sort:        "hot", "top", or "new" (default: "top")
        time_filter: For 'top' only — "day", "week", "month" (default: "day")
        limit:       Number of posts to return (default: 5)

    Returns:
        List of dicts: {title, url, subreddit, score, comments, date, source}
    """
    cache_key = f"reddit_{subreddit}_{sort}_{time_filter}_{limit}"
    cached = _cache_get(cache_key)
    if cached:
        logger.info(f"Reddit cache hit: {cache_key}")
        return cached

    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    params: dict = {"limit": limit}
    if sort == "top":
        params["t"] = time_filter

    posts: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers={
                # Reddit blocks requests without a User-Agent
                "User-Agent": "AI-News-MCP-Bot/1.0 (educational project)",
                "Accept": "application/json",
            })
            resp.raise_for_status()

        data = resp.json()
        children = data.get("data", {}).get("children", [])

        for child in children:
            post = child.get("data", {})

            title = (post.get("title") or "").strip()
            if not title:
                continue

            # Use crosspost URL if available, else the Reddit post link
            link_url = post.get("url") or ""
            reddit_url = f"https://www.reddit.com{post.get('permalink', '')}"

            # For self-posts (text only), link to the Reddit discussion
            is_self = post.get("is_self", False)
            final_url = reddit_url if is_self else link_url

            score    = post.get("score", 0)
            comments = post.get("num_comments", 0)
            flair    = post.get("link_flair_text") or ""

            # Convert Unix timestamp to date string
            created = post.get("created_utc", 0)
            date = ""
            if created:
                import datetime
                date = datetime.datetime.utcfromtimestamp(created).strftime("%Y-%m-%d")

            # Short summary from selftext or flair
            selftext = (post.get("selftext") or "").strip()
            summary = selftext[:150] + "..." if len(selftext) > 150 else selftext
            if not summary and flair:
                summary = f"[{flair}]"

            posts.append({
                "title":     title,
                "url":       final_url,
                "reddit_url": reddit_url,
                "subreddit": f"r/{subreddit}",
                "score":     score,
                "comments":  comments,
                "summary":   f"{score} upvotes · {comments} comments" + (f" · {summary}" if summary else ""),
                "date":      date,
                "source":    "Reddit",
            })

        logger.info(f"Reddit r/{subreddit}: fetched {len(posts)} posts")
        _cache_set(cache_key, posts)
        return posts

    except httpx.TimeoutException:
        logger.warning(f"Reddit r/{subreddit} timed out")
        return []
    except Exception as e:
        logger.error(f"Reddit r/{subreddit} failed: {e}")
        return []
