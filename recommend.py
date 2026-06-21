#!/usr/bin/env python3
"""
recommend.py - Recommend articles based on vocabulary coverage.

Usage:
    recommend.py --freq freq.tsv --vocab vocab.txt --articles articles/
    recommend.py --freq freq.tsv --vocab vocab.txt --articles articles/ -n 20
    recommend.py --freq freq.tsv --vocab vocab.txt --articles articles/ --dict moe.txt
    recommend.py --freq freq.tsv --vocab vocab.txt --articles articles/ --heuristic total
    recommend.py --freq freq.tsv --vocab vocab.txt --articles articles/ --verbose
"""

import argparse
import sys
from string import printable

import spacy_pkuseg as pkuseg

from storage import iter_articles

FILTER_CHARS = set(printable)

try:
    import opencc

    _t2s = opencc.OpenCC("t2s")
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_freq_table(path: str) -> dict[str, int]:
    """Load a word frequency table: <word>\t<frequency> one entry per line."""
    freq = {}
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(
                    f"[warn] freq table line {lineno} malformed: {line!r}",
                    file=sys.stderr,
                )
                continue
            try:
                freq[parts[0]] = int(parts[1])
            except ValueError:
                print(
                    f"[warn] freq table line {lineno} non-integer: {line!r}",
                    file=sys.stderr,
                )
    return freq


def load_wordlist(path: str) -> set[str]:
    """
    Load a word list, one word per line.
    Strips tab-separated annotations and bracket annotations.
    Converts to simplified if opencc is available.
    Excludes entries with no Chinese characters.
    """
    words = set()
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            word = line.split("\t")[0].strip()
            if not word or word.startswith("#"):
                continue
            word = word.split("[")[0].strip()
            if not set(word) - FILTER_CHARS:
                continue
            if HAS_OPENCC:
                word = _t2s.convert(word)
            words.add(word)
    return words


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


def tokenize(text: str, seg, reference: set[str] | None = None) -> list[str]:
    """
    Segment article text into words, converting to simplified first.
    If reference is provided, only tokens present in it are returned.
    Otherwise falls back to keeping tokens with at least one Chinese character.
    """
    tokens = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if HAS_OPENCC:
            line = _t2s.convert(line)
        for token in seg.cut(line):
            if reference is not None:
                if token in reference:
                    tokens.append(token)
            else:
                if set(token) - FILTER_CHARS:
                    tokens.append(token)
    return tokens


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_avg(
    tokens: list[str], freq: dict[str, int], vocab: set[str]
) -> tuple[float, dict]:
    """
    Heuristic 'avg' (default): average corpus frequency of unknown words.
    Normalised for article length.
    """
    unknown = set(tokens) - vocab
    freqs = {w: freq.get(w, 0) for w in unknown}
    score = sum(freqs.values()) / len(unknown) if unknown else 0.0
    top = sorted(freqs, key=freqs.__getitem__, reverse=True)
    return score, {
        "total_tokens": len(tokens),
        "unique_tokens": len(set(tokens)),
        "unknown_count": len(unknown),
        "unknown_list": top,  # full list, highest freq first
        "top_unknown": top[:10],  # for display
    }


def score_total(
    tokens: list[str], freq: dict[str, int], vocab: set[str]
) -> tuple[float, dict]:
    """
    Heuristic 'total': sum of corpus frequencies of unknown words.
    Length-biased — longer articles tend to score higher.
    """
    unknown = set(tokens) - vocab
    freqs = {w: freq.get(w, 0) for w in unknown}
    score = float(sum(freqs.values()))
    top = sorted(freqs, key=freqs.__getitem__, reverse=True)
    return score, {
        "total_tokens": len(tokens),
        "unique_tokens": len(set(tokens)),
        "unknown_count": len(unknown),
        "total_freq": int(score),
        "unknown_list": top,
        "top_unknown": top[:10],
    }


HEURISTICS: dict = {
    "avg": score_avg,
    "total": score_total,
}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def format_stats(stats: dict, heuristic: str) -> str:
    """Format a stats dict into a human-readable string for verbose output."""
    lines = []
    lines.append(
        f"    tokens: {stats['total_tokens']} total, "
        f"{stats['unique_tokens']} unique, "
        f"{stats['unknown_count']} unknown"
    )
    if heuristic == "total" and "total_freq" in stats:
        lines.append(f"    total freq: {stats['total_freq']:,}")
    if stats["top_unknown"]:
        lines.append(f"    top unknown: {' '.join(stats['top_unknown'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Recommend articles based on unknown word frequency."
    )
    p.add_argument(
        "--freq",
        required=True,
        metavar="FILE",
        help="Word frequency table (word\\tfreq, one per line).",
    )
    p.add_argument(
        "--vocab",
        required=True,
        metavar="FILE",
        help="Known vocabulary file, one word per line.",
    )
    p.add_argument(
        "--articles",
        required=True,
        metavar="DIR",
        help="Directory of scraped articles.",
    )
    p.add_argument(
        "--dict",
        metavar="FILE",
        default=None,
        help="Reference dictionary (e.g. MOE). Tokens not in this "
        "dictionary are ignored.",
    )
    p.add_argument(
        "-n",
        type=int,
        default=10,
        metavar="N",
        help="Number of top articles to recommend (default: 10).",
    )
    p.add_argument(
        "--source",
        metavar="NAME",
        help="Only consider articles from this source (substring match).",
    )
    p.add_argument(
        "--heuristic",
        choices=list(HEURISTICS),
        default="avg",
        help="Scoring heuristic: avg (default) or total.",
    )
    p.add_argument(
        "--model",
        metavar="MODEL",
        default=None,
        help="pkuseg domain model: news, web, medicine, tourism.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print per-article stats alongside recommendations.",
    )
    return p


def main():
    args = build_parser().parse_args()

    print("Loading frequency table...", file=sys.stderr)
    freq = load_freq_table(args.freq)
    print(f"  {len(freq):,} entries", file=sys.stderr)

    print("Loading vocabulary...", file=sys.stderr)
    vocab = load_wordlist(args.vocab)
    print(f"  {len(vocab):,} words", file=sys.stderr)

    reference = None
    if args.dict:
        print("Loading reference dictionary...", file=sys.stderr)
        reference = load_wordlist(args.dict)
        print(f"  {len(reference):,} entries", file=sys.stderr)

    print("Loading segmenter...", file=sys.stderr)
    seg_kwargs = {}
    if args.model:
        seg_kwargs["model_name"] = args.model
    seg = pkuseg.pkuseg(**seg_kwargs)

    scorer = HEURISTICS[args.heuristic]
    results: list[tuple[float, str, str, dict]] = []  # score, url, title, stats

    print("Scoring articles...", file=sys.stderr)
    for i, article in enumerate(iter_articles(args.articles, source=args.source)):
        if not article.text:
            continue
        tokens = tokenize(article.text, seg, reference=reference)
        if not tokens:
            continue
        score, stats = scorer(tokens, freq, vocab)
        results.append((score, article.url, article.title or "", stats))
        if (i + 1) % 50 == 0:
            print(f"  scored {i+1} articles...", file=sys.stderr)

    if not results:
        print("No articles found.", file=sys.stderr)
        sys.exit(1)

    results.sort(reverse=True)
    print(
        f"\nTop {args.n} recommendations "
        f"(scored {len(results)} articles, heuristic={args.heuristic}):\n"
    )

    for rank, (score, url, title, stats) in enumerate(results[: args.n], 1):
        print(f"{rank:>3}. [{score:>10.1f}] {title}")
        print(f"       {url}")
        if args.verbose:
            print(format_stats(stats, args.heuristic))


if __name__ == "__main__":
    main()
