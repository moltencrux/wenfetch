#!/usr/bin/env python3
"""
scrape.py - Fetch articles from configured sources and store them locally.

Usage:
    scrape.py                            # use sources.yaml, store in ./data/articles
    scrape.py -c path/to/sources.yaml
    scrape.py -o path/to/article/store
    scrape.py -s 科技新報                # only scrape named source
    scrape.py --limit 50                # max articles to save per source
    scrape.py --depth 2                 # crawl depth for spider sources
    scrape.py --rate 2                  # max requests per second (default: 2)
    scrape.py --since 2024-01-01        # only save articles published on/after this date
    scrape.py --max-stale 15            # stop discovery after N consecutive old/undated articles
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml
from requests_ratelimiter import LimiterSession

from article import Article, normalize_date
from extractor import extract, extract_all
from feeds import fetch_feed
from spider import fetch_index
from storage import is_fetched, save


def load_sources(config_path: str) -> list[dict]:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def discover_articles(source: dict, limit: int, depth: int,
                      since: datetime | None,
                      max_stale: int, session: LimiterSession) -> list[Article]:
    """
    Collect article stubs from RSS and/or spider discovery.
    Deduplicates by URL. If --since is set, stops after max_stale consecutive
    articles that predate the cutoff.
    """
    name = source["name"]
    seen: set[str] = set()
    articles: list[Article] = []
    stale_count = 0

    def add(candidates):
        stale_count = 0
        for art, cur_depth in candidates:
            if cur_depth > depth:
                return True

            if art.url in seen:
                continue
            seen.add(art.url)

            if not (since and art.date):
                # date not needed or can't be determined w/o fetching
                extract(art, session)

            if not art.date or art.date < since:
                # article is stale or assumed stale if undated
                print(f"[{name}] skipping {art.url} (published {art.date.date()})", file=sys.stderr)
                stale_count += 1
                if stale_count >= max_stale:
                    print(f"[{name}] stopping discovery — too many stale articles", file=sys.stderr)
                    return True
                continue

            articles.append(art)

            if len(articles) >= limit:
                return True


    if "rss" in source:
        if add(fetch_feed(source)):
            return articles

    if "url" in source:
        if add(fetch_index(source)):
            return articles

    if not articles:
        print(f"[{name}] no articles discovered (need rss or url in config)", file=sys.stderr)

    return articles


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape Chinese news articles.")
    p.add_argument("-c", "--config", default="sources.yaml", metavar="CONFIG",
                   help="Path to sources YAML file (default: sources.yaml).")
    p.add_argument("-o", "--output-dir", default="data/articles", metavar="DIR",
                   help="Directory to store articles (default: data/articles).")
    p.add_argument("-s", "--source", metavar="NAME",
                   help="Only scrape the named source (substring match).")
    p.add_argument("--limit", type=int, default=50, metavar="N",
                   help="Max articles to save per source (default: 50).")
    p.add_argument("--depth", type=int, default=2, metavar="N",
                   help="Crawl depth for spider sources (default: 2).")
    p.add_argument("--rate", type=float, default=2.0, metavar="N",
                   help="Max requests per second (default: 2).")
    p.add_argument("--since", type=normalize_date, metavar="YYYY-MM-DD",
                   help="Only save articles published on/after this date.")
    p.add_argument("--max-stale", type=int, default=15, metavar="N",
                   help="Stop discovery after N consecutive old/undated articles (default: 15).")
    return p


def main():
    args = build_parser().parse_args()
    sources = load_sources(args.config)
    base_dir = Path(args.output_dir)
    session = LimiterSession(per_second=args.rate)

    if args.source:
        sources = [s for s in sources if args.source in s["name"]]
        if not sources:
            print(f"No sources matched '{args.source}'", file=sys.stderr)
            sys.exit(1)

    for source in sources:
        name = source["name"]
        print(f"\n[{name}] discovering articles...", file=sys.stderr)

        articles = discover_articles(
            source, args.limit, args.depth, args.since, args.max_stale, session
        )
        print(f"[{name}] found {len(articles)} candidates", file=sys.stderr)

        # Filter already-fetched URLs before making any network requests
        pending = [a for a in articles if not is_fetched(base_dir, a.source, a.url)]
        skipped = len(articles) - len(pending)
        if skipped:
            print(f"[{name}] skipping {skipped} already fetched", file=sys.stderr)
        if not pending:
            print(f"[{name}] nothing new to fetch", file=sys.stderr)
            continue

        print(f"[{name}] fetching {len(pending)} new articles...", file=sys.stderr)
        fetched = failed = 0
        for i, article in enumerate(pending):
            extract(article, session)
            if article.text:
                # Post-extraction date filter for spider sources (date unknown pre-fetch)
                if args.since and article.date:
                    if normalize_date(article.date) < normalize_date(args.since):
                        print(f"[{name}] skipping {article.url} "
                              f"(published {article.date})", file=sys.stderr)
                        continue
                save(base_dir, article)
                fetched += 1
            else:
                failed += 1
            print(f"[{name}] {i+1}/{len(pending)} fetched={fetched} failed={failed}",
                  end="\r", file=sys.stderr)

        print(f"\n[{name}] done — {fetched} saved, {failed} failed", file=sys.stderr)


if __name__ == "__main__":
    main()
