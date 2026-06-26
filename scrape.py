#!/usr/bin/env python3
"""
scrape.py - Fetch articles from configured sources and store them locally.

Usage:
    scrape.py                            # use sources.yaml, store in ./articles
    scrape.py -c path/to/sources.yaml
    scrape.py -o path/to/article/store
    scrape.py -s 科技新報                # only scrape named source
    scrape.py --delay 2.0               # seconds between requests (default 1.5)
    scrape.py --limit 50                # max articles to save per source
    scrape.py --depth 2                 # crawl depth for spider sources
    scrape.py --since 2024-01-01        # only articles published on/after this date
    scrape.py --max-stale 15            # stop discovery after this many consecutive old/no-date articles
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from extractor import extract_all
from feeds import fetch_feed
from article import Article, normalize_date
from spider import fetch_index
from storage import is_fetched, save


def load_sources(config_path: str) -> list[dict]:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def discover_articles(source: dict, limit: int, depth: int, since: datetime | None = None, max_stale: int = 15) -> list[Article]:
    """
    Collect article stubs. For spider sources, uses generator + stale counter.
    """
    name = source["name"]
    seen: set[str] = set()
    articles: list[Article] = []
    stale_count = 0

    def add(candidates):
        nonlocal stale_count
        for a in candidates:
            if a.url in seen:
                continue
            seen.add(a.url)

            if since and a.date:
                a_date = normalize_date(a.date)
                since_norm = normalize_date(since)
                if a_date and a_date < since_norm:
                    stale_count += 1
                    if stale_count >= max_stale:
                        print(f"[{name}] stopping discovery — too many stale articles", file=sys.stderr)
                        return True  # signal stop
                    continue  # skip old
                else:
                    stale_count = 0  # reset on good article

            articles.append(a)
            if len(articles) >= limit * 2:  # over-fetch a bit for filtering
                return True
        return False

    if "rss" in source:
        add(fetch_feed(source))

    if "url" in source:
        for art in fetch_index(source, max_articles=limit * 3, depth=depth):
            if add([art]):
                break

    if not articles:
        print(f"[{name}] no discovery method found (need rss or url)", file=sys.stderr)

    return articles[:limit * 2]  # still over-fetch slightly


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape Chinese news articles.")
    p.add_argument(
        "-c", "--config", default="sources.yaml", metavar="CONFIG",
        help="Path to sources YAML file (default: sources.yaml).",
    )
    p.add_argument(
        "-o", "--output-dir", default="data/articles", metavar="DIR",
        help="Directory to store articles (default: ./articles).",
    )
    p.add_argument(
        "-s", "--source", metavar="NAME",
        help="Only scrape the named source (substring match).",
    )
    p.add_argument(
        "--delay", type=float, default=1.5, metavar="SECS",
        help="Seconds to wait between article fetches (default: 1.5).",
    )
    p.add_argument(
        "--limit", type=int, default=50, metavar="N",
        help="Max articles to save per source (default: 50).",
    )
    p.add_argument(
        "--depth", type=int, default=2, metavar="N",
        help="Crawl depth for spider sources (default: 2).",
    )
    p.add_argument(
        "--since",
        type=lambda s: datetime.fromisoformat(s.replace("Z", "+00:00") if "Z" in s else s),
        metavar="YYYY-MM-DD",
        help="Only fetch articles published on/after this date (e.g. 2024-01-01).",
    )
    p.add_argument(
        "--max-stale", type=int, default=15, metavar="N",
        help="Stop spider discovery after this many consecutive old/no-date articles (default: 15).",
    )
    return p


def main():
    args = build_parser().parse_args()
    sources = load_sources(args.config)
    base_dir = Path(args.output_dir)
    since = args.since
    max_stale = args.max_stale

    if args.source:
        sources = [s for s in sources if args.source in s["name"]]
        if not sources:
            print(f"No sources matched '{args.source}'", file=sys.stderr)
            sys.exit(1)

    for source in sources:
        name = source["name"]
        print(f"\n[{name}] discovering articles...", file=sys.stderr)
        articles = discover_articles(source, args.limit, args.depth, since, max_stale)
        print(f"[{name}] found {len(articles)} candidate URLs", file=sys.stderr)

        # Filter already-fetched URLs
        pending = [a for a in articles if not is_fetched(base_dir, a.source, a.url)]
        skipped = len(articles) - len(pending)
        if skipped:
            print(f"[{name}] skipping {skipped} already fetched", file=sys.stderr)
        if not pending:
            print(f"[{name}] nothing new to fetch", file=sys.stderr)
            continue

        print(f"[{name}] fetching {len(pending)} new articles...", file=sys.stderr)
        fetched = 0
        failed = 0
        for i, article in enumerate(pending):
            if i > 0:
                time.sleep(args.delay)
            extract_all([article])
            if article.text:
                # Post-extract date filter (for spider sources where discovery date may be missing)
                if since and article.date:
                    a_date = normalize_date(article.date)
                    since_norm = normalize_date(since)
                    if a_date and a_date < since_norm:
                        print(f"[{name}] skipping {article.url} (published {article.date.date()})", file=sys.stderr)
                        continue
                save(base_dir, article)
                fetched += 1
            else:
                failed += 1
            print(
                f"[{name}] {i+1}/{len(pending)} fetched={fetched} failed={failed}",
                end="\r",
                file=sys.stderr,
            )

        print(f"\n[{name}] done — {fetched} saved, {failed} failed", file=sys.stderr)


if __name__ == "__main__":
    main()
