"""
Business logic for the recommender app.
Views should be thin — all non-trivial logic lives here.
"""

import json
import heapq
from itertools import count
from collections import namedtuple
from pathlib import Path
from typing import Callable
from string import printable

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import ArticleToken, FreqEntry, CharFreqEntry, VocabEntry, VocabList
from .utils import process_vocab_entry_on_add, t2s, s2t


FILTER_CHARS = set(printable)


# ---------------------------------------------------------------------------
# Vocab management
# ---------------------------------------------------------------------------

Heuristic = namedtuple("Heuristic", "key label scorer")

def known_chars(vocab_list: VocabList) -> set[str]:
    """Unique characters from the vocab list, plus both script variants."""
    words = VocabEntry.objects.filter(vocab_list=vocab_list).values_list("word", flat=True)
    chars: set[str] = set()
    for w in words:
        for c in w:
            chars.add(c)
            chars.add(t2s.convert(c))
            chars.add(s2t.convert(c))
    return chars


def _article_text_path(article_key: str, source: str) -> Path | None:
    """Return the .txt path for an article, or None if it cannot be found."""
    articles_dir = Path(settings.ARTICLES_DIR)
    # Prefer the known source directory first
    candidate = articles_dir / source / f"{article_key}.txt"
    if candidate.exists():
        return candidate
    # Fallback: search any source sub-directory
    for p in articles_dir.glob(f"*/{article_key}.txt"):
        return p
    return None


def _extract_chars(text: str) -> set[str]:
    """Unique non-ASCII / non-printable characters from article text."""
    return {c for c in text if c not in FILTER_CHARS}


def parse_vocab_text(text: str) -> list[str]:
    """
    Parse pasted or uploaded vocab text into a list of simplified words.
    Accepts one word per line; ignores blank lines, comments, and annotations.
    """
    words = []
    for line in text.splitlines():
        word = line.split("\t")[0].strip()
        if not word or word.startswith("#") or word.startswith("//"):
            continue
        word = word.split("[")[0].strip()
        if not set(word) - FILTER_CHARS:
            continue
        words.append(word)
    return words


def import_vocab(vocab_list: VocabList, text: str) -> tuple[int, int]:
    """
    Import words using the new processing logic.
    """
    raw_words = parse_vocab_text(text)

    existing = set(
        VocabEntry.objects.filter(vocab_list=vocab_list)
        .values_list("word", flat=True)   # we'll improve this later
    )

    new_words = {
        process_vocab_entry_on_add(w) for w in raw_words if w not in existing
    }

    to_add = [VocabEntry(vocab_list=vocab_list, word=w) for w in new_words]

    if to_add:
        VocabEntry.objects.bulk_create(list(to_add), ignore_conflicts=True)

    skipped = len(raw_words) - len(to_add)
    return len(to_add), skipped


# ---------------------------------------------------------------------------
# Word scorers
# ---------------------------------------------------------------------------

def _word_candidates(vocab_list: VocabList, source: str | None):
    user_words = VocabEntry.objects.filter(vocab_list=vocab_list).values_list("word", flat=True)
    vocab_normalized = {process_vocab_entry_on_add(w) for w in user_words}

    qs = ArticleToken.objects.filter(
        token__in=FreqEntry.objects.values_list("word", flat=True)
    ).exclude(token__in=vocab_normalized)

    if source:
        qs = qs.filter(source=source)

    rows = qs.values("article_key", "source", "token").order_by("article_key")
    freq_map = dict(FreqEntry.objects.values_list("word", "frequency"))

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
    return articles


def _all_word_candidates(vocab_list: VocabList, source: str | None):
    """Candidates for review mode – includes articles with zero unknowns."""
    user_words = VocabEntry.objects.filter(vocab_list=vocab_list).values_list("word", flat=True)
    vocab_normalized = {process_vocab_entry_on_add(w) for w in user_words}
    freq_map = dict(FreqEntry.objects.values_list("word", "frequency"))

    # 1. All articles that have *any* tokens (this is cheap)
    qs = ArticleToken.objects.values("article_key", "source").distinct()
    if source:
        qs = qs.filter(source=source)

    # 2. For each article, pull only its tokens and filter in Python
    articles: dict[str, dict] = {}
    for row in qs.iterator():          # iterator() keeps memory low
        key = row["article_key"]
        src = row["source"]

        # tokens that belong to this article
        tokens = ArticleToken.objects.filter(
            article_key=key
        ).values_list("token", flat=True)

        unknown = []
        for t in tokens:
            if t in freq_map and t not in vocab_normalized:
                unknown.append((t, freq_map[t]))

        articles[key] = {
            "article_key": key,
            "source": src,
            "tokens": unknown,          # may be empty → u == 0
        }

    return articles

def _score_word_avg(vocab_list: VocabList, source: str | None) -> list[dict]:
    articles = _word_candidates(vocab_list, source)
    results = []
    for data in articles.values():
        tokens = data["tokens"]
        if not tokens:
            continue
        freqs = [f for _, f in tokens]
        score = sum(freqs) / len(freqs)
        top = heapq.nlargest(10, tokens, key=lambda x: x[1])
        results.append({
            "article_key": data["article_key"],
            "source": data["source"],
            "score": score,
            "unknown_count": len(tokens),
            "top_unknown": [w for w, _ in top],
        })
    return results



def _score_word_total(vocab_list: VocabList, source: str | None) -> list[dict]:
    articles = _word_candidates(vocab_list, source)
    results = []
    for data in articles.values():
        tokens = data["tokens"]
        if not tokens:
            continue
        score = float(sum(f for _, f in tokens))
        top = heapq.nlargest(10, tokens, key=lambda x: x[1])
        results.append({
            "article_key": data["article_key"],
            "source": data["source"],
            "score": score,
            "unknown_count": len(tokens),
            "top_unknown": [w for w, _ in top],
        })
    return results


def _min_unknown_words(vocab_list: VocabList, source: str | None) -> list[dict]:
    articles = _all_word_candidates(vocab_list, source)
    results = []
    for data in articles.values():
        tokens = data["tokens"]
        freqs = [f for _, f in tokens]
        u = len(freqs)
        score = float("inf") if u == 0 else (sum(freqs) / (u * (u + 1)))
        top = heapq.nlargest(10, tokens, key=lambda x: x[1])

        results.append({
            "article_key": data["article_key"],
            "source": data["source"],
            "score": score,
            "unknown_count": len(tokens),
            "top_unknown": [w for w, _ in top],
        })
    return results


# ---------------------------------------------------------------------------
# Character scorers
# ---------------------------------------------------------------------------

def _char_candidates(vocab_list: VocabList, source: str | None):
    known = known_chars(vocab_list)
    char_freq = dict(CharFreqEntry.objects.values_list("char", "frequency"))

    qs = ArticleToken.objects.values("article_key", "source").distinct()
    if source:
        qs = qs.filter(source=source)

    results = []
    for row in qs:
        key = row["article_key"]
        src = row["source"]
        txt_path = _article_text_path(key, src)
        if not txt_path:
            continue
        try:
            text = txt_path.read_text(encoding="utf-8-sig")
        except OSError:
            continue

        unknown = _extract_chars(text) - known
        scored = [(c, char_freq[c]) for c in unknown if c in char_freq]
        if not scored:
            continue

        results.append({
            "article_key": key,
            "source": src,
            "scored": scored,          # temporary; turned into final dict below
        })
    return results


def _score_char_avg(vocab_list: VocabList, source: str | None) -> list[dict]:
    raw = _char_candidates(vocab_list, source)
    results = []
    for item in raw:
        scored = item["scored"]
        freqs = [f for _, f in scored]
        score = sum(freqs) / len(freqs)
        top = heapq.nlargest(10, scored, key=lambda x: x[1])
        results.append({
            "article_key": item["article_key"],
            "source": item["source"],
            "score": score,
            "unknown_count": len(scored),
            "top_unknown": [c for c, _ in top],
        })
    return results


def _score_char_total(vocab_list: VocabList, source: str | None) -> list[dict]:
    raw = _char_candidates(vocab_list, source)
    results = []
    for item in raw:
        scored = item["scored"]
        score = float(sum(f for _, f in scored))
        top = heapq.nlargest(10, scored, key=lambda x: x[1])

        results.append({
            "article_key": item["article_key"],
            "source": item["source"],
            "score": score,
            "unknown_count": len(scored),
            "top_unknown": [c for c, _ in top],
        })
    return results


# ---------------------------------------------------------------------------
# Registry & public entry point
# ---------------------------------------------------------------------------

HEURISTICS = [
    Heuristic("avg",         _("Average new word frequency"),      _score_word_avg),
    Heuristic("total",       _("Total new word frequency"),        _score_word_total),
    Heuristic("min",         _("Minimum new word count"),          _min_unknown_words),
    Heuristic("char-avg",    _("Average new character frequency"), _score_char_avg),
    Heuristic("char-total",  _("Total new character frequency"),   _score_char_total),
]


HEURISTIC_MAP = {h.key: h for h in HEURISTICS}



# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


def recommend(
    vocab_list: VocabList,
    source: str | None = None,
    heuristic: str = "avg",
    n: int = 10,
) -> list[dict]:
    """
    Return top-N recommended articles for the given vocab list.

    heuristic must be one of the keys registered in HEURISTICS.
    """

    h = HEURISTIC_MAP.get(heuristic, HEURISTIC_MAP['avg'])
    if heuristic not in HEURISTIC_MAP:
        self.stderr.write(f"Heuristic {heuristic} unknown, reverting to default.")

    results = h.scorer(vocab_list, source)

    return heapq.nlargest(n, results, key=lambda r: r["score"])

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


def get_heuristic_choices() -> list[tuple[str, str]]:
    """Convenience for forms / templates: [(key, label), ...]"""
    return [(h.key, h.label) for h in HEURISTICS]

def get_sources() -> list[str]:
    """Return all distinct source names present in the article token store."""
    return list(
        ArticleToken.objects.values_list("source", flat=True)
        .distinct()
        .order_by("source")
    )


def known_chars(vocab_list: VocabList) -> set[str]:
    """
    All unique characters that appear in any word of the user's list,
    plus both simplified and traditional forms of each character.
    """
    words = VocabEntry.objects.filter(vocab_list=vocab_list).values_list("word", flat=True)
    chars: set[str] = set()
    for w in words:
        for c in w:
            chars.add(c)
            chars.add(t2s.convert(c))
            chars.add(s2t.convert(c))
    return chars
