"""
Article fetching from Towards Data Science, Medium, ArXiv, RSS feeds, and Hacker News.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from html import unescape
from typing import Optional

import aiohttp
import feedparser

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    url: str
    source: str
    category: str
    published: Optional[datetime] = None
    summary: str = ""
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    score: float = 0.0
    hn_points: int = 0
    priority_source: bool = False
    reading_time: str = ""
    insight: str = ""
    classification: str = ""
    problem_summary: str = ""
    image_url: str = ""

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return isinstance(other, Article) and self.url == other.url

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "category": self.category,
            "published": self.published.isoformat() if self.published else None,
            "summary": self.summary,
            "authors": self.authors,
            "tags": self.tags,
            "score": round(self.score, 3),
            "hn_points": self.hn_points,
            "priority_source": self.priority_source,
            "reading_time": self.reading_time,
            "insight": self.insight,
            "classification": self.classification,
            "problem_summary": self.problem_summary,
            "image_url": self.image_url,
        }


def _clean_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _estimate_reading_time(summary: str) -> str:
    word_count = len(summary.split())
    minutes = max(2, word_count // 50)
    return f"{minutes} min read"


def _parse_date(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _extract_image(entry) -> str:
    """Extract thumbnail/image URL from RSS entry using multiple strategies."""
    # media:thumbnail (Google News, many feeds)
    thumbs = getattr(entry, "media_thumbnail", [])
    if thumbs and isinstance(thumbs, list):
        url = thumbs[0].get("url", "")
        if url:
            return url

    # media:content with image type
    media = getattr(entry, "media_content", [])
    if media and isinstance(media, list):
        for m in media:
            if "image" in m.get("type", "") or m.get("medium") == "image":
                url = m.get("url", "")
                if url:
                    return url

    # enclosure with image type
    enclosures = getattr(entry, "enclosures", [])
    if enclosures:
        for enc in enclosures:
            if "image" in enc.get("type", ""):
                return enc.get("href", "") or enc.get("url", "")

    # og:image or img in summary HTML
    raw_summary = getattr(entry, "summary", "")
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_summary)
    if img_match:
        return img_match.group(1)

    return ""


async def _fetch_feed(session: aiohttp.ClientSession, feed_cfg: dict,
                      max_age: timedelta) -> list[Article]:
    url = feed_cfg["url"]
    name = feed_cfg["name"]
    category = feed_cfg.get("category", "general")
    is_priority = feed_cfg.get("priority", False)
    articles = []
    cutoff = datetime.now(timezone.utc) - max_age

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                logger.warning(f"[{name}] HTTP {resp.status}")
                return []
            body = await resp.text()
    except Exception as e:
        logger.warning(f"[{name}] Fetch error: {e}")
        return []

    feed = feedparser.parse(body)
    for entry in feed.entries:
        pub_date = _parse_date(entry)
        if pub_date and pub_date < cutoff:
            continue

        title = _clean_html(getattr(entry, "title", ""))
        if not title:
            continue

        summary = _clean_html(getattr(entry, "summary", ""))[:600]
        link = getattr(entry, "link", "")

        authors = []
        if hasattr(entry, "authors"):
            authors = [a.get("name", "") for a in entry.authors if a.get("name")]
        elif hasattr(entry, "author"):
            authors = [entry.author]

        tags = [t.get("term", "") for t in getattr(entry, "tags", []) if t.get("term")]

        articles.append(Article(
            title=title,
            url=link,
            source=name,
            category=category,
            published=pub_date or datetime.now(timezone.utc),
            summary=summary,
            authors=authors,
            tags=tags,
            priority_source=is_priority,
            reading_time=_estimate_reading_time(summary),
            image_url=_extract_image(entry),
        ))

    logger.info(f"[{name}] Fetched {len(articles)} articles")
    return articles


async def fetch_rss_feeds(feed_configs: list[dict], max_age_hours: int = 36) -> list[Article]:
    max_age = timedelta(hours=max_age_hours)
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": "AI-News-Agent/1.0 (Personal Digest)"}
    ) as session:
        tasks = [_fetch_feed(session, f, max_age) for f in feed_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    articles = []
    for result in results:
        if isinstance(result, list):
            articles.extend(result)
        elif isinstance(result, Exception):
            logger.warning(f"Feed task failed: {result}")

    return articles


async def fetch_hackernews(config: dict, max_age_hours: int = 36) -> list[Article]:
    if not config.get("enabled", False):
        return []

    min_score = config.get("min_score", 50)
    keywords = [kw.lower() for kw in config.get("ai_keywords", [])]
    max_age = timedelta(hours=max_age_hours)
    cutoff = datetime.now(timezone.utc) - max_age
    articles = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return []
                top_ids = await resp.json()

            sem = asyncio.Semaphore(30)

            async def fetch_story(story_id: int) -> Optional[Article]:
                async with sem:
                    try:
                        async with session.get(
                            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            if resp.status != 200:
                                return None
                            item = await resp.json()
                    except Exception:
                        return None

                    if not item or item.get("type") != "story":
                        return None

                    title = item.get("title", "")
                    score = item.get("score", 0)
                    url = item.get("url", "")
                    ts = item.get("time", 0)

                    if not title or not url or score < min_score:
                        return None

                    pub_date = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
                    if pub_date and pub_date < cutoff:
                        return None

                    title_lower = title.lower()
                    if not any(kw in title_lower for kw in keywords):
                        return None

                    return Article(
                        title=title,
                        url=url,
                        source="Hacker News",
                        category="community",
                        published=pub_date,
                        summary=f"Score: {score} | Comments: {item.get('descendants', 0)}",
                        hn_points=score,
                        reading_time="varies",
                    )

            tasks = [fetch_story(sid) for sid in top_ids[:200]]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Article):
                    articles.append(r)

    except Exception as e:
        logger.warning(f"[HackerNews] Error: {e}")

    logger.info(f"[HackerNews] Fetched {len(articles)} AI-related stories")
    return articles


async def fetch_all_articles(config: dict) -> list[Article]:
    max_age = config.get("digest", {}).get("max_age_hours", 36)

    rss_articles, hn_articles = await asyncio.gather(
        fetch_rss_feeds(config.get("sources", {}).get("rss_feeds", []), max_age_hours=max_age),
        fetch_hackernews(config.get("sources", {}).get("hackernews", {}), max_age_hours=max_age),
    )

    all_articles = rss_articles + hn_articles

    seen_urls = set()
    seen_titles = set()
    unique = []
    for article in all_articles:
        title_key = re.sub(r"\W+", "", article.title.lower())
        if article.url not in seen_urls and title_key not in seen_titles:
            seen_urls.add(article.url)
            seen_titles.add(title_key)
            unique.append(article)

    logger.info(f"Total unique articles fetched: {len(unique)}")
    return unique


# ── Live Search: fetch fresh articles on demand ────────────────────────

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}+AI+machine+learning&hl=en&gl=US&ceid=US:en"
_HN_ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"

async def _live_google_news(session: aiohttp.ClientSession,
                            query: str, limit: int = 25) -> list[Article]:
    url = _GOOGLE_NEWS_RSS.format(query=query.replace(" ", "+"))
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            body = await resp.text()
    except Exception as e:
        logger.warning(f"[LiveGoogleNews] fetch error: {e}")
        return []

    feed = feedparser.parse(body)
    articles = []
    for entry in feed.entries[:limit]:
        title = _clean_html(getattr(entry, "title", ""))
        link = getattr(entry, "link", "")
        if not title or not link:
            continue
        summary = _clean_html(getattr(entry, "summary", ""))[:400]
        pub_date = _parse_date(entry)
        source_name = getattr(entry, "source", {})
        if hasattr(source_name, "get"):
            source_name = source_name.get("title", "Google News")
        elif hasattr(source_name, "title"):
            source_name = source_name.title
        else:
            source_name = "Google News"

        articles.append(Article(
            title=title, url=link, source=source_name,
            category="live_search",
            published=pub_date or datetime.now(timezone.utc),
            summary=summary,
            reading_time=_estimate_reading_time(summary),
        ))
    logger.info(f"[LiveGoogleNews] fetched {len(articles)} for '{query}'")
    return articles


async def _live_medium_tags(session: aiohttp.ClientSession,
                            query: str, limit: int = 20) -> list[Article]:
    tags = [w.lower().strip() for w in re.split(r'[\s,]+', query) if len(w) > 2][:4]
    all_articles = []
    for tag in tags:
        url = f"https://medium.com/feed/tag/{tag}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    continue
                body = await resp.text()
        except Exception:
            continue
        feed = feedparser.parse(body)
        for entry in feed.entries[:8]:
            title = _clean_html(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")
            if not title or not link:
                continue
            summary = _clean_html(getattr(entry, "summary", ""))[:400]
            pub_date = _parse_date(entry)
            all_articles.append(Article(
                title=title, url=link, source=f"Medium/{tag}",
                category="live_search",
                published=pub_date or datetime.now(timezone.utc),
                summary=summary,
                reading_time=_estimate_reading_time(summary),
            ))
    logger.info(f"[LiveMedium] fetched {len(all_articles)} for '{query}'")
    return all_articles[:limit]


async def _live_hn_algolia(session: aiohttp.ClientSession,
                           query: str, limit: int = 15) -> list[Article]:
    params = {"query": query, "tags": "story", "hitsPerPage": limit}
    try:
        async with session.get(_HN_ALGOLIA, params=params,
                               timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception as e:
        logger.warning(f"[LiveHN] error: {e}")
        return []

    articles = []
    for hit in data.get("hits", []):
        title = hit.get("title", "")
        url = hit.get("url", "")
        if not title or not url:
            continue
        points = hit.get("points", 0) or 0
        comments = hit.get("num_comments", 0) or 0
        ts = hit.get("created_at_i")
        pub = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
        articles.append(Article(
            title=title, url=url, source="Hacker News",
            category="live_search", published=pub,
            summary=f"Points: {points} | Comments: {comments}",
            hn_points=points,
            reading_time="varies",
        ))
    logger.info(f"[LiveHN] fetched {len(articles)} for '{query}'")
    return articles


async def _live_arxiv(session: aiohttp.ClientSession,
                      query: str, limit: int = 10) -> list[Article]:
    api_url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query=all:{query.replace(' ', '+')}&start=0&max_results={limit}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )
    try:
        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            body = await resp.text()
    except Exception as e:
        logger.warning(f"[LiveArXiv] error: {e}")
        return []

    feed = feedparser.parse(body)
    articles = []
    for entry in feed.entries[:limit]:
        title = _clean_html(getattr(entry, "title", "")).replace("\n", " ")
        link = getattr(entry, "link", "")
        if not title or not link:
            continue
        summary = _clean_html(getattr(entry, "summary", ""))[:400]
        pub_date = _parse_date(entry)
        authors = [a.get("name", "") for a in getattr(entry, "authors", []) if a.get("name")]
        tags = [t.get("term", "") for t in getattr(entry, "tags", []) if t.get("term")]
        articles.append(Article(
            title=title, url=link, source="ArXiv",
            category="research", published=pub_date or datetime.now(timezone.utc),
            summary=summary, authors=authors, tags=tags,
            reading_time=_estimate_reading_time(summary),
        ))
    logger.info(f"[LiveArXiv] fetched {len(articles)} for '{query}'")
    return articles


_NEWS_FEEDS = [
    {"url": "https://news.google.com/rss/search?q=LLM+model+release+AI&hl=en&gl=US&ceid=US:en",
     "name": "Google News", "category": "news"},
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/",
     "name": "TechCrunch AI", "category": "news"},
    {"url": "https://www.marktechpost.com/feed/",
     "name": "MarkTechPost", "category": "news"},
    {"url": "https://huggingface.co/blog/feed.xml",
     "name": "Hugging Face", "category": "news"},
    {"url": "https://blog.google/technology/ai/rss/",
     "name": "Google AI", "category": "news"},
]


async def fetch_news_feed() -> list[dict]:
    """Fetch latest AI/LLM news with images for the sidebar."""
    max_age = timedelta(hours=72)
    connector = aiohttp.TCPConnector(limit=15, ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": "AI-News-Agent/1.0 (Personal Digest)"}
    ) as session:
        tasks = [_fetch_feed(session, f, max_age) for f in _NEWS_FEEDS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles = []
    for r in results:
        if isinstance(r, list):
            all_articles.extend(r)

    seen = set()
    unique = []
    for a in all_articles:
        key = re.sub(r"\W+", "", a.title.lower())
        if key not in seen:
            seen.add(key)
            unique.append(a)

    unique.sort(key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    items = []
    for a in unique[:20]:
        items.append({
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "image_url": a.image_url,
            "published": a.published.isoformat() if a.published else None,
            "summary": a.summary[:150] if a.summary else "",
        })

    logger.info(f"[NewsFeed] {len(items)} items, {sum(1 for i in items if i['image_url'])} with images")
    return items


async def live_search_articles(query: str) -> list[Article]:
    """Fetch fresh articles from multiple sources based on a user query."""
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": "AI-News-Agent/1.0 (Personal Digest)"}
    ) as session:
        results = await asyncio.gather(
            _live_google_news(session, query),
            _live_medium_tags(session, query),
            _live_hn_algolia(session, query),
            _live_arxiv(session, query),
            return_exceptions=True,
        )

    all_articles = []
    for r in results:
        if isinstance(r, list):
            all_articles.extend(r)
        elif isinstance(r, Exception):
            logger.warning(f"Live search source failed: {r}")

    seen_urls = set()
    seen_titles = set()
    unique = []
    for art in all_articles:
        title_key = re.sub(r"\W+", "", art.title.lower())
        if art.url not in seen_urls and title_key not in seen_titles:
            seen_urls.add(art.url)
            seen_titles.add(title_key)
            unique.append(art)

    logger.info(f"[LiveSearch] total unique: {len(unique)} for '{query}'")
    return unique
