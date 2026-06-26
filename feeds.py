"""Fetch article listings from RSS feeds."""

import re
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from article import Article, normalize_date


def _parse_date(entry) -> datetime | None:
    """Try to extract a publish date from a feedparser entry."""
    for attr in ("published", "updated"):
        if hasattr(entry, attr):
            try:
                return parsedate_to_datetime(getattr(entry, attr))
            except Exception:
                pass
    return None


def _check_url(url: str, pattern: re.Pattern | None, source_name: str) -> bool:
    """Return True if URL matches the article regex, logging rejections."""
    if pattern is None:
        return True
    if pattern.search(url):
        return True
    print(f"[{source_name}] rejected: {url}", file=sys.stderr)
    return False


def fetch_feed(source: dict) -> list[Article]:
    """
    Parse an RSS feed and return a list of Articles (text not yet fetched).
    Filters URLs against article_regex if specified in the source config.
    """
    name = source["name"]
    pattern = re.compile(source["article_regex"]) if "article_regex" in source else None

    feed = feedparser.parse(source["rss"])
    articles = []
    for entry in feed.entries:
        url = getattr(entry, "link", None)
        if not url:
            continue
        if not _check_url(url, pattern, name):
            continue
        date = _parse_date(entry)
        if date:
            date = normalize_date(date)
        articles.append(
            Article(
                url=url,
                source=name,
                title=getattr(entry, "title", ""),
                date=date,
            )
        )
    return articles
