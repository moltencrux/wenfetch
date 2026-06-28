"""
Discover article URLs by crawling a site to a configurable depth.

Strategy:
  - URLs matching article_regex are collected as articles
  - URLs not matching article_regex are queued for further crawling (up to depth)
  - All crawling stays within the same domain
  - Visited URLs are tracked to avoid re-crawling
Yields Article stubs lazily (BFS order).
"""

import re
import sys
from collections import deque
from urllib.parse import urljoin, urlparse
from typing import Iterator

import trafilatura
from trafilatura.utils import load_html

from article import Article, normalize_date


def _same_domain(base: str, url: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def _extract_links(downloaded: str, base_url: str) -> list[str]:
    """Return all same-domain absolute URLs found in a page."""
    tree = load_html(downloaded)
    if tree is None:
        return []
    links = []
    for el in tree.iter("a"):
        href = el.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        full_url = urljoin(base_url, href)
        # Strip fragment
        full_url = full_url.split("#")[0]
        if _same_domain(base_url, full_url):
            links.append(full_url)
    return links


def fetch_index(source: dict) -> Iterator[Article]:
    """
    Generator: Crawl site starting from source['url'].
    Yields Article stubs (with early date if possible).
    """
    base_url = source["url"]
    name = source["name"]
    # depth = source.get("depth", depth)
    pattern = re.compile(source["article_regex"]) if "article_regex" in source else None

    # Queue entries are (url, current_depth)
    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    visited: set[str] = set()
    article_urls: set[str] = set()
    yielded = 0

    while queue:
        url, current_depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            print(f"[{name}] failed to fetch: {url}", file=sys.stderr)
            continue

        links = _extract_links(downloaded, base_url)

        for link in links:
            if link in visited:
                continue
            if pattern and pattern.search(link):
                if link not in article_urls:
                    article_urls.add(link)
                    art = Article(url=link, source=name)

                    # Attempt early date extraction from listing page
                    try:
                        meta = trafilatura.extract_metadata(downloaded)
                        if meta and meta.date:
                            art.date = normalize_date(meta.date)
                    except Exception:
                        pass

                    yielded += 1
                    yield art, current_depth
            elif link not in visited:
                print(f"[{name}] following: {link}", file=sys.stderr)
                queue.append((link, current_depth + 1))

    print(
        f"[{name}] crawled {len(visited)} pages, yielded {yielded} articles",
        file=sys.stderr,
    )
