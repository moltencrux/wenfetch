#!/usr/bin/env python3
"""
scrape.py - Fetch articles from configured sources and store them locally.

Usage:
    scrape.py                            # use sources.yaml, store in ./articles
    scrape.py -c path/to/sources.yaml
    scrape.py -o path/to/article/store
    scrape.py -s 科技新報                # only scrape named source
    scrape.py --delay 2.0               # seconds between requests (default 1.5)
    scrape.py --limit 50                # max articles per source
    scrape.py --depth 2                 # crawl depth for spider sources (default 2)
"""

import argparse
import sys
import time
from pathlib import Path

import yaml

from extractor import extract_all
from feeds import fetch_feed
from models import Article
from spider import fetch_index
from storage import is_fetched, save


def load_sources(config_path: str) -> list[dict]:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def discover_articles(source: dict, limit: int, depth: int) -> list[Article]:
    """
    Collect article stubs from all configured discovery methods for a source
    (rss, url), deduplicating by URL.
    """
    name = source["name"]
    seen: set[str] = set()
    articles: list[Article] = []

    def add(candidates: list[Article]) -> None:
        for a in candidates:
            if a.url not in seen:
                seen.add(a.url)
                articles.append(a)

    if "rss" in source:
        add(fetch_feed(source))

    if "url" in source:
        add(fetch_index(source, max_articles=limit, depth=depth))

    if not articles:
        print(f"[{name}] no discovery method found (need rss or url)", file=sys.stderr)

    return articles[:limit]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape Chinese news articles.")
    p.add_argument(
        "-c",
        "--config",
        default="sources.yaml",
        metavar="CONFIG",
        help="Path to sources YAML file (default: sources.yaml).",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        default="articles",
        metavar="DIR",
        help="Directory to store articles (default: ./articles).",
    )
    p.add_argument(
        "-s",
        "--source",
        metavar="NAME",
        help="Only scrape the named source (substring match).",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=1.5,
        metavar="SECS",
        help="Seconds to wait between article fetches (default: 1.5).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Max articles to fetch per source (default: 50).",
    )
    p.add_argument(
        "--depth",
        type=int,
        default=2,
        metavar="N",
        help="Crawl depth for spider sources (default: 2). Per-source 'depth' in yaml overrides.",
    )
    return p


def main():
    args = build_parser().parse_args()
    sources = load_sources(args.config)
    base_dir = Path(args.output_dir)

    if args.source:
        sources = [s for s in sources if args.source in s["name"]]
        if not sources:
            print(f"No sources matched '{args.source}'", file=sys.stderr)
            sys.exit(1)

    for source in sources:
        name = source["name"]
        print(f"\n[{name}] discovering articles...", file=sys.stderr)
        articles = discover_articles(source, args.limit, args.depth)
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
