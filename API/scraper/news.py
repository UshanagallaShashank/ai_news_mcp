"""
News Scraper
============

Fetches AI news from 3 reliable, free sources — NO API keys needed:

  1. Marktechpost  — via RSS feed  (avoids 403 from HTML scraping)
  2. HackerNews    — via Algolia search API (official, free)
  3. DEV.to        — via public REST API  (developer AI articles)

Why RSS instead of HTML scraping for Marktechpost?
  - The homepage returns 403 Forbidden to bots
  - RSS feeds are designed to be consumed by programs — always allowed
  - Gives cleaner, structured data (no HTML parsing needed)

Features:
  - Async HTTP (all 3 sources fetched simultaneously if needed)
  - 30-min in-memory cache (avoid hammering sites)
  - Each source fails independently (one 404 won't kill the others)
"""

import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional
import xml.etree.ElementTree as ET   # Built-in XML parser for RSS feeds
import re

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Data Model ────────────────────────────────────────────────────

@dataclass
class Article:
    """One news article from any source."""
    title: str
    url: str
    source: str
    summary: Optional[str] = None
    date: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Cache ─────────────────────────────────────────────────────────
# Simple dict: key → (articles_list, timestamp)
_cache: dict[str, tuple[list, float]] = {}


def _cache_get(key: str) -> Optional[list[Article]]:
    if key not in _cache:
        return None
    articles, cached_at = _cache[key]
    if time.time() - cached_at < settings.news_cache_ttl:
        logger.info(f"Cache hit: '{key}'")
        return articles
    return None


def _cache_set(key: str, articles: list[Article]) -> None:
    _cache[key] = (articles, time.time())


# ── Helpers ───────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common HTML entities."""
    text = re.sub(r"<[^>]+>", "", html)        # Remove tags
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#8217;", "'")
    text = text.replace("&#8220;", '"')
    text = text.replace("&#8221;", '"')
    text = text.replace("&nbsp;", " ")
    return text.strip()


def _parse_rss_date(rss_date: str) -> str:
    """
    Convert RSS pubDate string to YYYY-MM-DD format.
    RSS dates look like: 'Tue, 11 Mar 2025 12:00:00 +0000'
    """
    try:
        from email.utils import parsedate
        from datetime import date
        parsed = parsedate(rss_date)
        if parsed:
            return f"{parsed[0]:04d}-{parsed[1]:02d}-{parsed[2]:02d}"
    except Exception:
        pass
    # Return first 10 chars as fallback if parsing fails
    return rss_date[:10] if len(rss_date) >= 10 else rss_date


# ── Source 1: Marktechpost RSS Feed ──────────────────────────────

async def fetch_marktechpost(limit: int = 5) -> list[Article]:
    """
    Fetch AI research news from Marktechpost via their RSS feed.

    RSS URL: https://www.marktechpost.com/feed/
    Format:  RSS 2.0 XML

    Using RSS instead of scraping the homepage because:
    - Homepage returns 403 Forbidden to automated requests
    - RSS is explicitly designed for programmatic consumption
    - Data is already structured — no HTML parsing needed

    XML namespaces used by this feed:
      dc:   http://purl.org/dc/elements/1.1/   (for dc:creator)
      content: http://purl.org/rss/1.0/modules/content/
    """
    cache_key = f"marktechpost_{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    rss_url = "https://www.marktechpost.com/feed/"
    articles: list[Article] = []

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(rss_url, headers={
                # RSS readers identify themselves — sites always allow this
                "User-Agent": "Mozilla/5.0 (compatible; RSS Reader/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            })
            response.raise_for_status()

        # Parse RSS XML
        # ElementTree requires we handle namespaces manually
        NS = {
            "dc":      "http://purl.org/dc/elements/1.1/",
            "content": "http://purl.org/rss/1.0/modules/content/",
            "media":   "http://search.yahoo.com/mrss/",
        }

        root = ET.fromstring(response.text)
        channel = root.find("channel")

        if channel is None:
            logger.warning("Marktechpost RSS: no <channel> element found")
            return []

        for item in channel.findall("item")[:limit]:
            # Required fields
            title_el = item.find("title")
            link_el  = item.find("link")

            if title_el is None or link_el is None:
                continue

            title = (title_el.text or "").strip()
            url   = (link_el.text or "").strip()

            if not title or not url:
                continue

            # Optional: publication date
            pub_date_el = item.find("pubDate")
            date = _parse_rss_date(pub_date_el.text or "") if pub_date_el is not None else None

            # Optional: description/summary (may contain HTML)
            desc_el = item.find("description")
            summary = None
            if desc_el is not None and desc_el.text:
                raw = _strip_html(desc_el.text)
                summary = raw[:300] + "..." if len(raw) > 300 else raw

            articles.append(Article(
                title=title,
                url=url,
                source="Marktechpost",
                summary=summary,
                date=date,
            ))

        logger.info(f"Marktechpost RSS: fetched {len(articles)} articles")
        _cache_set(cache_key, articles)
        return articles

    except ET.ParseError as e:
        logger.error(f"Marktechpost RSS XML parse error: {e}")
        return []
    except httpx.TimeoutException:
        logger.warning("Marktechpost RSS timed out")
        return []
    except Exception as e:
        logger.error(f"Marktechpost RSS failed: {e}")
        return []


# ── Source 2: HackerNews via Algolia API ─────────────────────────

async def fetch_hackernews(limit: int = 5) -> list[Article]:
    """
    Fetch top AI/ML stories from HackerNews via Algolia search API.

    API: https://hn.algolia.com/api/v1/search
    - Free, no API key required
    - Returns JSON, much easier than parsing HTML
    - We filter by points>15 to keep only quality stories

    API docs: https://hn.algolia.com/api
    """
    cache_key = f"hackernews_{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    articles: list[Article] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://hn.algolia.com/api/v1/search",
                params={
                    "query": "artificial intelligence machine learning LLM",
                    "tags": "story",           # Only stories, not comments
                    "numericFilters": "points>15",  # Quality filter
                    "hitsPerPage": limit,
                },
            )
            response.raise_for_status()

        for hit in response.json().get("hits", []):
            title = (hit.get("title") or "").strip()
            if not title:
                continue

            # Use the linked article URL, fall back to HN discussion
            story_url = hit.get("url") or (
                f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            )

            points  = hit.get("points", 0)
            comments = hit.get("num_comments", 0)
            date     = (hit.get("created_at") or "")[:10]  # "2024-01-15T..." → "2024-01-15"

            articles.append(Article(
                title=title,
                url=story_url,
                source="HackerNews",
                summary=f"{points} points · {comments} comments",
                date=date,
            ))

        logger.info(f"HackerNews: fetched {len(articles)} articles")
        _cache_set(cache_key, articles)
        return articles

    except httpx.TimeoutException:
        logger.warning("HackerNews API timed out")
        return []
    except Exception as e:
        logger.error(f"HackerNews fetch failed: {e}")
        return []


# ── Source 3: DEV.to Public API ───────────────────────────────────

async def fetch_devto(limit: int = 5) -> list[Article]:
    """
    Fetch AI-tagged articles from DEV.to (developer community blog).

    API: https://dev.to/api/articles?tag=ai
    - Free, no API key required
    - Returns JSON with full article metadata
    - Great source for practical/tutorial AI content

    API docs: https://developers.forem.com/api
    """
    cache_key = f"devto_{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    articles: list[Article] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://dev.to/api/articles",
                params={
                    "tag": "ai",
                    "per_page": limit,
                    "top": 1,       # Sort by most popular in last 24h
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

        for item in response.json():
            title = (item.get("title") or "").strip()
            url   = item.get("url") or item.get("canonical_url") or ""

            if not title or not url:
                continue

            # description is already plain text
            summary = item.get("description") or None
            if summary:
                summary = summary[:300] + "..." if len(summary) > 300 else summary

            # published_at looks like "2024-01-15T12:00:00Z"
            pub = item.get("published_at") or ""
            date = pub[:10] if len(pub) >= 10 else None

            reactions = item.get("public_reactions_count", 0)
            comments  = item.get("comments_count", 0)

            # Append reaction count to summary for context
            if reactions or comments:
                meta = f"{reactions} reactions · {comments} comments"
                summary = f"{summary}\n{meta}" if summary else meta

            articles.append(Article(
                title=title,
                url=url,
                source="DEV.to",
                summary=summary,
                date=date,
            ))

        logger.info(f"DEV.to: fetched {len(articles)} articles")
        _cache_set(cache_key, articles)
        return articles

    except httpx.TimeoutException:
        logger.warning("DEV.to API timed out")
        return []
    except Exception as e:
        logger.error(f"DEV.to fetch failed: {e}")
        return []


# ── Main Function ─────────────────────────────────────────────────

# Map source name → fetch function
_SOURCE_MAP = {
    "marktechpost": fetch_marktechpost,
    "hackernews":   fetch_hackernews,
    "devto":        fetch_devto,
}

ALL_SOURCES = list(_SOURCE_MAP.keys())


async def scrape_news(
    limit: int = 5,
    sources: Optional[list[str]] = None,
) -> list[Article]:
    """
    Fetch AI news from multiple sources and return a combined list.

    This is the single entry point used by:
    - MCP server tools
    - ADK agent tools
    - REST API (/news endpoint)
    - Scheduler (daily job)

    Args:
        limit:   Total number of articles to return (split across sources)
        sources: Which sources to use. Defaults to all three.
                 Valid values: "marktechpost", "hackernews", "devto"

    Returns:
        Combined list of Articles, up to `limit` total.
        Order: Marktechpost → HackerNews → DEV.to

    Example:
        # Get 6 articles: 2 from each source
        articles = await scrape_news(limit=6)

        # Get only from HackerNews
        articles = await scrape_news(limit=5, sources=["hackernews"])
    """
    if sources is None:
        sources = ALL_SOURCES

    # Validate source names
    valid_sources = [s for s in sources if s in _SOURCE_MAP]
    if not valid_sources:
        logger.warning(f"No valid sources in: {sources}. Using all.")
        valid_sources = ALL_SOURCES

    # Distribute the limit as evenly as possible across sources
    n = len(valid_sources)
    per_source = max(1, limit // n)
    # First source gets any leftover (e.g. limit=5, n=2 → [3, 2])
    quotas = [per_source + (limit - per_source * n if i == 0 else 0)
              for i in range(n)]

    all_articles: list[Article] = []

    for source_name, quota in zip(valid_sources, quotas):
        fetch_fn = _SOURCE_MAP[source_name]
        try:
            articles = await fetch_fn(quota)
            all_articles.extend(articles)
        except Exception as e:
            # One source failing should never crash the entire job
            logger.error(f"Source '{source_name}' raised an exception: {e}")

    logger.info(f"Total articles returned: {len(all_articles[:limit])}")
    return all_articles[:limit]
