"""
Segment scraped articles and import their tokens into the database.
Run this after scrape.py has fetched new articles.

Usage:
    manage.py import_tokens
    manage.py import_tokens --articles /path/to/articles
    manage.py import_tokens --source 科技新報
"""

import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

import spacy_pkuseg as pkuseg

from apps.recommender.models import ArticleToken

try:
    import opencc

    _t2s = opencc.OpenCC("t2s")
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False

FILTER_CHARS = set(__import__("string").printable)


def tokenize(text: str, seg) -> set[str]:
    """Segment text into unique tokens, converting to simplified first."""
    tokens = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if HAS_OPENCC:
            line = _t2s.convert(line)
        for token in seg.cut(line):
            if set(token) - FILTER_CHARS:
                tokens.add(token)
    return tokens


class Command(BaseCommand):
    help = "Segment scraped articles and store tokens in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--articles",
            default=None,
            help="Path to articles directory (default: settings.ARTICLES_DIR).",
        )
        parser.add_argument(
            "--source",
            default=None,
            help="Only process articles from this source subdirectory.",
        )
        parser.add_argument(
            "--model",
            default=None,
            help="pkuseg domain model: news, web, medicine, tourism.",
        )

    def handle(self, *args, **options):
        articles_dir = Path(options["articles"] or settings.ARTICLES_DIR)
        if not articles_dir.exists():
            self.stderr.write(f"Articles directory not found: {articles_dir}")
            sys.exit(1)

        self.stdout.write("Loading segmenter...")
        seg_kwargs = {}
        if options["model"]:
            seg_kwargs["model_name"] = options["model"]
        seg = pkuseg.pkuseg(**seg_kwargs)

        # Find source directories
        if options["source"]:
            source_dirs = [articles_dir / options["source"]]
        else:
            source_dirs = [d for d in articles_dir.iterdir() if d.is_dir()]

        # Already-indexed keys — skip to avoid re-processing
        existing_keys = set(
            ArticleToken.objects.values_list("article_key", flat=True).distinct()
        )

        total_added = 0
        total_skipped = 0

        for source_dir in sorted(source_dirs):
            source_name = source_dir.name
            json_files = list(source_dir.glob("*.json"))
            new_files = [f for f in json_files if f.stem not in existing_keys]

            self.stdout.write(
                f"[{source_name}] {len(json_files)} articles, " f"{len(new_files)} new"
            )

            for meta_path in new_files:
                txt_path = meta_path.with_suffix(".txt")
                if not txt_path.exists():
                    continue
                text = txt_path.read_text(encoding="utf-8")
                tokens = tokenize(text, seg)
                if not tokens:
                    continue

                article_key = meta_path.stem
                entries = [
                    ArticleToken(
                        article_key=article_key,
                        source=source_name,
                        token=token,
                    )
                    for token in tokens
                ]
                ArticleToken.objects.bulk_create(
                    entries, ignore_conflicts=True, batch_size=1000
                )
                total_added += len(entries)

            total_skipped += len(json_files) - len(new_files)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done — {total_added} tokens added, {total_skipped} articles skipped."
            )
        )
