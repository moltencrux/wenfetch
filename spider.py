"""
Discover article URLs by crawling a site to a configurable depth.

Strategy:
  - URLs matching article_regex are collected as articles
  - URLs not matching article_regex are queued for further crawling (up to depth)
  - All crawling stays within the same domain
  - Visited URLs are tracked to avoid re-crawling
"""

import re
import sys
from collections import deque
from urllib.parse import urljoin, urlparse

import trafilatura
from trafilatura.utils import load_html

from article import Article


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


def fetch_index(source: dict, max_articles: int = 20, depth: int = 2) -> list[Article]:
    """
    Crawl a site starting from source['url'] up to `depth` levels deep.

    URLs matching article_regex are collected as articles.
    URLs not matching article_regex are followed as navigation pages (up to depth).
    Returns at most max_articles Article stubs (text not yet fetched).
    """
    base_url = source["url"]
    name = source["name"]
    depth = source.get("depth", depth)
    pattern = re.compile(source["article_regex"]) if "article_regex" in source else None

    # Queue entries are (url, current_depth)
    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    visited: set[str] = set()
    articles: list[Article] = []
    article_urls: set[str] = set()

    while queue and len(articles) < max_articles:
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
                # It's an article URL
                if link not in article_urls:
                    article_urls.add(link)
                    articles.append(Article(url=link, source=name))
                    if len(articles) >= max_articles:
                        break
            else:
                # It's a navigation page — follow it if we have depth remaining
                if current_depth < depth and link not in visited:
                    print(f"[{name}] following: {link}", file=sys.stderr)
                    queue.append((link, current_depth + 1))

    print(
        f"[{name}] crawled {len(visited)} pages, found {len(articles)} articles",
        file=sys.stderr,
    )
    return articles
