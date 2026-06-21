"""
Business logic for the recommender app.
Views should be thin — all non-trivial logic lives here.
"""

import json
from pathlib import Path
from string import printable

from django.conf import settings
from django.db import transaction

from .models import ArticleToken, FreqEntry, VocabEntry, VocabList

FILTER_CHARS = set(printable)

try:
    import opencc

    _t2s = opencc.OpenCC("t2s")
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False


# ---------------------------------------------------------------------------
# Vocab management
# ---------------------------------------------------------------------------


def parse_vocab_text(text: str) -> list[str]:
    """
    Parse pasted or uploaded vocab text into a list of simplified words.
    Accepts one word per line; ignores blank lines, comments, and annotations.
    """
    words = []
    for line in text.splitlines():
        word = line.split("\t")[0].strip()
        if not word or word.startswith("#"):
            continue
        word = word.split("[")[0].strip()
        if not set(word) - FILTER_CHARS:
            continue
        if HAS_OPENCC:
            word = _t2s.convert(word)
        words.append(word)
    return words


def import_vocab(vocab_list: VocabList, text: str) -> tuple[int, int]:
    """
    Import words from text into a vocab list.
    Returns (added, skipped) counts.
    """
    words = parse_vocab_text(text)
    existing = set(
        VocabEntry.objects.filter(vocab_list=vocab_list).values_list("word", flat=True)
    )
    to_add = [
        VocabEntry(vocab_list=vocab_list, word=w) for w in words if w not in existing
    ]
    VocabEntry.objects.bulk_create(to_add, ignore_conflicts=True)
    return len(to_add), len(words) - len(to_add)


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


def recommend(
    vocab_list: VocabList, source: str = None, heuristic: str = "avg", n: int = 10
) -> list[dict]:
    """
    Return top N recommended articles for a user's vocab list.

    For each article, computes a score over its tokens that:
    - appear in the frequency table (known to be useful vocabulary)
    - do NOT appear in the user's vocab list (still unknown to the user)

    heuristic='avg':   average frequency of qualifying unknown tokens
    heuristic='total': sum of frequencies of qualifying unknown tokens

    Returns a list of dicts with keys:
        article_key, source, score, unknown_count, top_unknown
    """
    vocab_words = VocabEntry.objects.filter(vocab_list=vocab_list).values_list(
        "word", flat=True
    )

    # Tokens that are in the freq table but not in user vocab
    qs = ArticleToken.objects.filter(
        token__in=FreqEntry.objects.values_list("word", flat=True)
    ).exclude(token__in=vocab_words)

    if source:
        qs = qs.filter(source=source)

    # Pull (article_key, source, token, frequency) for scoring in Python.
    # We do this rather than a pure SQL AVG because we need top_unknown too,
    # and fetching per-token data once is cheaper than two round-trips.
    rows = qs.values("article_key", "source", "token").order_by("article_key")

    # Build freq lookup
    freq_map = dict(FreqEntry.objects.values_list("word", "frequency"))

    # Aggregate per article
    articles: dict[str, dict] = {}
    for row in rows:
        key = row["article_key"]
        if key not in articles:
            articles[key] = {
                "article_key": key,
                "source": row["source"],
                "tokens": [],
            }
        articles[key]["tokens"].append((row["token"], freq_map.get(row["token"], 0)))

    # Score and sort
    results = []
    for key, data in articles.items():
        tokens = data["tokens"]
        if not tokens:
            continue
        freqs = [f for _, f in tokens]
        if heuristic == "avg":
            score = sum(freqs) / len(freqs)
        else:  # total
            score = float(sum(freqs))
        top = sorted(tokens, key=lambda x: x[1], reverse=True)[:10]
        results.append(
            {
                "article_key": key,
                "source": data["source"],
                "score": score,
                "unknown_count": len(tokens),
                "top_unknown": [w for w, _ in top],
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:n]


def enrich_with_metadata(results: list[dict]) -> list[dict]:
    """
    Add url and title to recommendation results by reading article JSON files.
    Modifies results in place and returns them.
    """
    articles_dir = Path(settings.ARTICLES_DIR)
    for r in results:
        # Search across all source subdirs for this key
        for meta_path in articles_dir.glob(f"*/{r['article_key']}.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                r["url"] = meta.get("url", "")
                r["title"] = meta.get("title", "")
                r["published"] = meta.get("published", "")
            except Exception:
                pass
            break
        else:
            r["url"] = ""
            r["title"] = r["article_key"]
            r["published"] = ""
    return results


def get_sources() -> list[str]:
    """Return all distinct source names present in the article token store."""
    return list(
        ArticleToken.objects.values_list("source", flat=True)
        .distinct()
        .order_by("source")
    )
