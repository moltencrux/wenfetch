#!/usr/bin/env python3
"""
segment.py - Tokenize Chinese text using pkuseg, one token per line.

Usage:
    segment.py [FILE ...] [-o OUTPUT] [-m MODEL] [-d DICT]
    echo "我愛北京" | segment.py
"""

import argparse
import pickle
import sys
import tempfile
from pathlib import Path

import spacy_pkuseg as pkuseg

# opencc is optional — used to expand custom dict entries with script variants
try:
    import opencc

    _t2s = opencc.OpenCC("t2s")
    _s2t = opencc.OpenCC("s2t")
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False


def build_merged_dict(user_dict_path: str) -> str:
    """
    Merge the pkuseg default dictionary with a user-supplied one.

    If opencc is available, each custom word is also added in its opposite
    script variant (traditional↔simplified) so entries work regardless of
    which script appears in the input.

    Returns the path to a temporary merged file valid for the life of the process.
    """
    pkg = Path(pkuseg.__file__).parent
    default_pkl = pkg / "dicts" / "default.pkl"

    with open(default_pkl, "rb") as f:
        default_words_str = pickle.load(f)  # newline-delimited string

    default_words = set(default_words_str.splitlines())

    user_lines = Path(user_dict_path).read_text(encoding="utf-8").splitlines()

    extra = []
    for line in user_lines:
        word = line.split("\t")[0].strip()  # strip optional POS tag
        if not word:
            continue
        extra.append(line)  # original entry (may include POS)
        if HAS_OPENCC:
            simp = _t2s.convert(word)
            trad = _s2t.convert(word)
            for variant in (simp, trad):
                if variant != word and variant not in default_words:
                    extra.append(variant)  # variant without POS tag

    merged = default_words_str + "\n" + "\n".join(extra)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8", delete=False
    )
    tmp.write(merged)
    tmp.close()
    return tmp.name


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Segment Chinese text into tokens, one per line."
    )
    p.add_argument(
        "files",
        metavar="FILE",
        nargs="*",
        help="Input file(s). Reads from stdin if none given.",
    )
    p.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT",
        help="Output file. Defaults to stdout.",
    )
    p.add_argument(
        "-m",
        "--model",
        metavar="MODEL",
        default=None,
        help="Domain model: news, web, medicine, tourism (default: mixed).",
    )
    p.add_argument(
        "-d",
        "--dict",
        metavar="DICT",
        default=None,
        help="Path to a user dictionary file, one word per line.",
    )
    return p


def iter_input(files: list[str]):
    """Yield lines from each file in turn, or stdin if no files given."""
    if not files:
        yield from sys.stdin
    else:
        for path in files:
            with open(path, encoding="utf-8") as f:
                yield from f


def main() -> None:
    args = build_parser().parse_args()

    kwargs = {}
    if args.model:
        kwargs["model_name"] = args.model
    if args.dict:
        kwargs["user_dict"] = build_merged_dict(args.dict)
        if HAS_OPENCC:
            print(
                "[info] opencc available — script variants added to custom dict",
                file=sys.stderr,
            )
        else:
            print(
                "[info] opencc not available — custom dict used as-is", file=sys.stderr
            )

    seg = pkuseg.pkuseg(**kwargs)

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout

    try:
        for line in iter_input(args.files):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            tokens = seg.cut(line)
            for token in tokens:
                out.write(token + "\n")
    finally:
        if args.output:
            out.close()


if __name__ == "__main__":
    main()
