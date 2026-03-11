"""
News Scraper
============

Scrapes AI news from multiple sources:
  1. Marktechpost  — AI/ML research articles
  2. HackerNews    — Tech community stories (via free Algolia API)

Features:
  - Async HTTP requests (fast, non-blocking)
  - In-memory cache (avoids hammering sites repeatedly)
  - Graceful error handling (one source failing won't crash everything)

Dependencies:
  httpx          — Async HTTP client (better than requests for async apps)
  beautifulsoup4 — HTML parser
  lxml           — Fast HTML parser backend for BeautifulSoup
"""

import time
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Data Model ────────────────────────────────────────────────────

@dataclass
class Article:
    """
    Represents a single news article.

    @dataclass automatically generates __init__, __repr__, etc.
    Think of it as a simple container/struct.
    """
    title: str
    url: str
    source: str
    summary: Optional[str] = None
    date: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to plain dictionary (for JSON serialization)"""
        return asdict(self)


# ── Simple In-Memory Cache ─────────────────────────────────────────
# Avoids scraping the same sites multiple times in a short window.
# Key: cache key string  →  Value: (data, timestamp)
_cache: dict[str, tuple[list, float]] = {}


def _get_from_cache(key: str) -> Optional[list[Article]]:
    """Return cached articles if still fresh, else None."""
    if key not in _cache:
        return None
    articles, cached_at = _cache[key]
    age = time.time() - cached_at
    if age < settings.news_cache_ttl:
        logger.info(f"Cache hit for '{key}' (age: {int(age)}s)")
        return articles
    logger.info(f"Cache expired for '{key}' (age: {int(age)}s)")
    return None


def _save_to_cache(key: str, articles: list[Article]) -> None:
    """Save articles to cache with current timestamp."""
    _cache[key] = (articles, time.time())


# ── HTTP Client Config ────────────────────────────────────────────
# Pretend to be a browser so sites don't block us
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Source 1: Marktechpost ────────────────────────────────────────

async def scrape_marktechpost(limit: int = 5) -> list[Article]:
    """
    Scrape latest AI research news from Marktechpost.com

    How it works:
    1. Fetch the homepage HTML
    2. Find <article> tags (each one is a news card)
    3. Extract title, URL, summary, and date from each card

    Args:
        limit: Max articles to return

    Returns:
        List of Article objects (may be empty if scraping fails)
    """
    cache_key = f"marktechpost_{limit}"
    cached = _get_from_cache(cache_key)
    if cached:
        return cached

    url = "https://www.marktechpost.com/"
    articles: list[Article] = []

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=HEADERS, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Each article is inside an <article> HTML tag
        for card in soup.select("article")[:limit * 2]:  # Fetch extra, filter later
            # Title and URL are in a heading's anchor tag
            title_tag = card.select_one("h2 a, h3 a, h4 a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            article_url = title_tag.get("href", "")

            if not title or not article_url:
                continue

            # Optional: get excerpt/summary
            summary_tag = card.select_one(".entry-content p, .excerpt p, p")
            summary = summary_tag.get_text(strip=True)[:300] if summary_tag else None

            # Optional: get date
            date_tag = card.select_one("time, .post-date, .entry-date")
            date = date_tag.get_text(strip=True) if date_tag else None

            articles.append(Article(
                title=title,
                url=article_url,
                source="Marktechpost",
                summary=summary,
                date=date,
            ))

            if len(articles) >= limit:
                break

        logger.info(f"Scraped {len(articles)} articles from Marktechpost")
        _save_to_cache(cache_key, articles)
        return articles

    except httpx.TimeoutException:
        logger.warning("Marktechpost request timed out")
        return []
    except Exception as e:
        logger.error(f"Marktechpost scraping failed: {e}")
        return []


# ── Source 2: HackerNews (via Algolia API) ────────────────────────

async def scrape_hackernews(limit: int = 5) -> list[Article]:
    """
    Fetch AI/ML stories from HackerNews via the free Algolia search API.

    Why Algolia API instead of scraping?
    - HN has an official search API (no scraping needed!)
    - More reliable than HTML scraping
    - Returns structured JSON data

    API docs: https://hn.algolia.com/api

    Args:
        limit: Max articles to return

    Returns:
        List of Article objects
    """
    cache_key = f"hackernews_{limit}"
    cached = _get_from_cache(cache_key)
    if cached:
        return cached

    # Algolia's free HackerNews search API
    api_url = "https://hn.algolia.com/api/v1/search"
    articles: list[Article] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(api_url, params={
                "query": "artificial intelligence machine learning LLM",
                "tags": "story",                    # Only top-level stories (not comments)
                "numericFilters": "points>15",       # Filter low-quality stories
                "hitsPerPage": limit,
            })
            response.raise_for_status()

        data = response.json()

        for hit in data.get("hits", []):
            title = hit.get("title", "").strip()
            if not title:
                continue

            # Story URL or HN discussion page as fallback
            story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            date_str = hit.get("created_at", "")[:10]  # "2024-01-15T..." → "2024-01-15"

            points = hit.get("points", 0)
            comments = hit.get("num_comments", 0)

            articles.append(Article(
                title=title,
                url=story_url,
                source="HackerNews",
                summary=f"{points} points · {comments} comments",
                date=date_str,
            ))

        logger.info(f"Fetched {len(articles)} articles from HackerNews")
        _save_to_cache(cache_key, articles)
        return articles

    except httpx.TimeoutException:
        logger.warning("HackerNews API request timed out")
        return []
    except Exception as e:
        logger.error(f"HackerNews fetch failed: {e}")
        return []


# ── Main Scraping Function ────────────────────────────────────────

async def scrape_news(
    limit: int = 5,
    sources: Optional[list[str]] = None,
) -> list[Article]:
    """
    Fetch AI news from all sources and combine results.

    This is the main function used by the MCP server, ADK agent, and API.

    Args:
        limit:   Total number of articles to return
        sources: Which sources to use. Default: all sources.
                 Options: "marktechpost", "hackernews"

    Returns:
        Combined list of Article objects, up to `limit` total.

    Example:
        articles = await scrape_news(limit=6)
        # → 3 from Marktechpost + 3 from HackerNews
    """
    if sources is None:
        sources = ["marktechpost", "hackernews"]

    # Split limit evenly across sources
    per_source = max(1, limit // len(sources))
    remainder = limit - (per_source * len(sources))

    all_articles: list[Article] = []

    if "marktechpost" in sources:
        # Give first source any remainder articles
        fetch_limit = per_source + (remainder if not all_articles else 0)
        articles = await scrape_marktechpost(fetch_limit)
        all_articles.extend(articles)

    if "hackernews" in sources:
        articles = await scrape_hackernews(per_source)
        all_articles.extend(articles)

    logger.info(f"Total articles fetched: {len(all_articles)}")
    return all_articles[:limit]
