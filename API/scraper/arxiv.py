"""
Arxiv Scraper
=============

Fetches the latest AI/ML research papers from Arxiv via RSS.

Feed URL: http://export.arxiv.org/rss/cs.AI  (cs.AI = AI category)
Also available: cs.LG (Machine Learning), cs.CL (NLP), cs.CV (Vision)

Why Arxiv?
- Free, no API key needed
- Official RSS feeds — always up-to-date (daily updates at ~midnight ET)
- Real-time research papers, not just blog posts
- Huge value for researchers / engineers wanting to stay current

No authentication required.
"""

import logging
import time
import html
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────
_cache: dict[str, tuple[list[dict], float]] = {}
CACHE_TTL = 3600  # Arxiv updates once a day, 1hr cache is fine


def _cache_get(key: str) -> Optional[list[dict]]:
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
    return None


def _cache_set(key: str, data: list[dict]) -> None:
    _cache[key] = (data, time.time())


# ── Arxiv category feeds ───────────────────────────────────────────
ARXIV_CATEGORIES = {
    "ai":      "cs.AI",   # Artificial Intelligence
    "ml":      "cs.LG",   # Machine Learning
    "nlp":     "cs.CL",   # Natural Language Processing
    "cv":      "cs.CV",   # Computer Vision
    "robotics": "cs.RO",  # Robotics
}


async def fetch_arxiv_papers(
    topic: str = "ai",
    limit: int = 5,
) -> list[dict]:
    """
    Fetch the latest research papers from Arxiv for a given topic.

    Args:
        topic: One of "ai", "ml", "nlp", "cv", "robotics" (default: "ai")
        limit: Number of papers to return (default: 5)

    Returns:
        List of dicts: {title, url, authors, summary, date, category}
    """
    category = ARXIV_CATEGORIES.get(topic.lower(), "cs.AI")
    cache_key = f"arxiv_{category}_{limit}"
    cached = _cache_get(cache_key)
    if cached:
        logger.info(f"Arxiv cache hit: {cache_key}")
        return cached

    feed_url = f"http://export.arxiv.org/rss/{category}"
    papers: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(feed_url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; RSS Reader/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            })
            resp.raise_for_status()

        # Arxiv RSS uses standard RSS 2.0 with some Dublin Core extensions
        NS = {"dc": "http://purl.org/dc/elements/1.1/"}
        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item")[:limit]:
            title_el = item.find("title")
            link_el  = item.find("link")
            if title_el is None or link_el is None:
                continue

            title = html.unescape((title_el.text or "").strip())
            url   = (link_el.text or "").strip()

            if not title or not url:
                continue

            # Description contains abstract (may have HTML)
            desc_el = item.find("description")
            abstract = ""
            if desc_el is not None and desc_el.text:
                # Strip HTML tags and unescape
                raw = desc_el.text
                no_tags = ""
                in_tag = False
                for ch in raw:
                    if ch == "<":
                        in_tag = True
                    elif ch == ">":
                        in_tag = False
                    elif not in_tag:
                        no_tags += ch
                abstract = html.unescape(no_tags).strip()[:300]

            # Authors from dc:creator
            creator_el = item.find("dc:creator", NS)
            authors = (creator_el.text or "").strip() if creator_el is not None else ""

            # Publication date
            pub_el = item.find("pubDate")
            date = ""
            if pub_el is not None and pub_el.text:
                try:
                    from email.utils import parsedate
                    parsed = parsedate(pub_el.text)
                    if parsed:
                        date = f"{parsed[0]:04d}-{parsed[1]:02d}-{parsed[2]:02d}"
                except Exception:
                    date = (pub_el.text or "")[:10]

            papers.append({
                "title":    title,
                "url":      url,
                "authors":  authors,
                "summary":  abstract,
                "date":     date,
                "category": category,
                "source":   "Arxiv",
            })

        logger.info(f"Arxiv ({category}): fetched {len(papers)} papers")
        _cache_set(cache_key, papers)
        return papers

    except ET.ParseError as e:
        logger.error(f"Arxiv RSS parse error: {e}")
        return []
    except httpx.TimeoutException:
        logger.warning("Arxiv RSS timed out")
        return []
    except Exception as e:
        logger.error(f"Arxiv fetch failed: {e}")
        return []
