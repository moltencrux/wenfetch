"""Fetch article listings from RSS feeds."""

import re
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterator

import feedparser

from article import Article, normalize_date


def _parse_date(entry) -> datetime | None:
    """Try to extract a publish date from a feedparser entry."""
    for attr in ("published", "updated"):
        if hasattr(entry, attr):
            try:
                return normalize_date(parsedate_to_datetime(getattr(entry, attr)))
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


def fetch_feed(source: dict) -> Iterator[Article]:
    """
    Parse an RSS feed and yield Articles (text not yet fetched).
    Filters URLs against article_regex if specified in the source config.
    """
    name = source["name"]
    pattern = re.compile(source["article_regex"]) if "article_regex" in source else None

    feed = feedparser.parse(source["rss"])
    for entry in feed.entries:
        url = getattr(entry, "link", None)
        if not url:
            continue
        if not _check_url(url, pattern, name):
            continue
        yield Article(
            url=url,
            source=name,
            title=getattr(entry, "title", ""),
            date=_parse_date(entry),
        ), 0
