from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import feedparser
from trafilatura import extract

from whatsup.config import NewsConfig

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 (compatible; WhatsUpTrendBot/1.0)"
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class NewsArticle:
    """News article content and metadata used for summarization."""

    title: str
    source: str
    published: str
    url: str
    content: str


def get_top_news_articles(trend: str, config: NewsConfig) -> list[NewsArticle]:
    """Fetch Top Google News RSS articles for a trend.

    Args:
        trend: Google Trends query text.
        config: Google News retrieval configuration.

    Returns:
        Up to `config.top_n` news articles with extracted content or RSS fallback text.
    """
    feed_url = build_google_news_rss_url(trend, config)
    feed_content = _fetch_text(feed_url, config.request_timeout_seconds)
    if feed_content is None:
        return []

    feed = feedparser.parse(feed_content)
    articles: list[NewsArticle] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for entry in feed.entries:
        title = str(entry.get("title", "")).strip()
        rss_url = str(entry.get("link", "")).strip()
        if not title or not rss_url:
            continue

        article_url = resolve_news_url(rss_url, config.request_timeout_seconds)
        dedupe_url = article_url.rstrip("/")
        dedupe_title = title.casefold()
        if dedupe_url in seen_urls or dedupe_title in seen_titles:
            continue

        seen_urls.add(dedupe_url)
        seen_titles.add(dedupe_title)
        source = _get_source_name(entry)
        published = str(entry.get("published", "")).strip()
        fallback_content = _build_fallback_content(title, source, entry)
        article_content = extract_article_text(
            article_url,
            fallback_content,
            config.request_timeout_seconds,
            config.max_article_chars,
        )
        articles.append(
            NewsArticle(
                title=title,
                source=source,
                published=published,
                url=article_url,
                content=article_content,
            )
        )

        if len(articles) >= config.top_n:
            break

    return articles


def build_google_news_rss_url(trend: str, config: NewsConfig) -> str:
    """Build a US Google News RSS URL constrained to the last day."""
    query = f"{trend} when:1d"
    params = {
        "q": query,
        "hl": config.locale_hl,
        "gl": config.locale_gl,
        "ceid": config.locale_ceid,
    }
    return f"{GOOGLE_NEWS_RSS_URL}?{urlencode(params)}"


def resolve_news_url(url: str, timeout_seconds: int) -> str:
    """Resolve a news URL with a bounded HTTP redirect attempt."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.geturl()
    except (HTTPError, URLError, TimeoutError, OSError):
        return url


def extract_article_text(
    url: str,
    fallback_content: str,
    timeout_seconds: int,
    max_article_chars: int,
) -> str:
    """Extract readable article text, falling back to RSS metadata.

    Args:
        url: Publisher or Google News URL.
        fallback_content: RSS metadata to use if extraction fails.
        timeout_seconds: HTTP timeout for article download.
        max_article_chars: Maximum article text to keep for summarization.

    Returns:
        Extracted article text or fallback metadata.
    """
    html_content = _fetch_text(url, timeout_seconds)
    if html_content is None:
        return fallback_content

    extracted_text = extract(
        html_content,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not extracted_text:
        return fallback_content

    return extracted_text.strip()[:max_article_chars]


def _fetch_text(url: str, timeout_seconds: int) -> str | None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, OSError):
        return None


def _get_source_name(entry: object) -> str:
    source = entry.get("source", {}) if hasattr(entry, "get") else {}
    if hasattr(source, "get"):
        return str(source.get("title", "")).strip()
    return ""


def _build_fallback_content(title: str, source: str, entry: object) -> str:
    summary = str(entry.get("summary", "")).strip() if hasattr(entry, "get") else ""
    clean_summary = html.unescape(HTML_TAG_PATTERN.sub("", summary)).strip()
    parts = [f"Title: {title}"]
    if source:
        parts.append(f"Source: {source}")
    if clean_summary:
        parts.append(f"RSS summary: {clean_summary}")
    return "\n".join(parts)
