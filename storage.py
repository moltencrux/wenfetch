"""
storage.py - Flat-file storage for scraped articles.

Directory layout:
    <base_dir>/
        <source_name>/
            <url_hash>.txt    # extracted article text
            <url_hash>.json   # metadata (url, title, published, fetched_at)
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from models import Article


def url_to_key(url: str) -> str:
    """Return a 16-character hex hash of the URL for use as a filename stem."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _source_dir(base_dir: Path, source: str) -> Path:
    return base_dir / source


def article_paths(base_dir: Path, source: str, url: str) -> tuple[Path, Path]:
    """Return (text_path, meta_path) for a given source and URL."""
    key = url_to_key(url)
    d = _source_dir(base_dir, source)
    return d / f"{key}.txt", d / f"{key}.json"


def is_fetched(base_dir: Path, source: str, url: str) -> bool:
    """Return True if this URL has already been fetched and stored."""
    _, meta_path = article_paths(base_dir, source, url)
    return meta_path.exists()


def save(base_dir: Path, article: Article) -> None:
    """
    Persist an Article to disk.
    Creates the source subdirectory if needed.
    Skips saving if article.text is empty.
    """
    if not article.text:
        return

    text_path, meta_path = article_paths(base_dir, article.source, article.url)
    text_path.parent.mkdir(parents=True, exist_ok=True)

    text_path.write_text(article.text, encoding="utf-8")

    meta = {
        "url": article.url,
        "source": article.source,
        "title": article.title,
        "published": article.date.isoformat() if article.date else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load(base_dir: Path, source: str, url: str) -> Article | None:
    """Load a previously stored Article from disk. Returns None if not found."""
    text_path, meta_path = article_paths(base_dir, source, url)
    if not meta_path.exists():
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""

    from datetime import datetime

    date = None
    if meta.get("published"):
        try:
            date = datetime.fromisoformat(meta["published"])
        except ValueError:
            pass

    return Article(
        url=meta["url"],
        source=meta["source"],
        title=meta.get("title", ""),
        date=date,
        text=text,
    )


def iter_articles(base_dir: Path, source: str | None = None) -> list[Article]:
    """
    Iterate over all stored articles, optionally filtered by source name.
    Yields Article objects with text populated.
    """
    base = Path(base_dir)
    if source:
        source_dirs = [base / source]
    else:
        source_dirs = [d for d in base.iterdir() if d.is_dir()]

    for source_dir in source_dirs:
        for meta_path in sorted(source_dir.glob("*.json")):
            text_path = meta_path.with_suffix(".txt")
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                text = (
                    text_path.read_text(encoding="utf-8") if text_path.exists() else ""
                )
                date = None
                if meta.get("published"):
                    try:
                        date = datetime.fromisoformat(meta["published"])
                    except ValueError:
                        pass
                yield Article(
                    url=meta["url"],
                    source=meta["source"],
                    title=meta.get("title", ""),
                    date=date,
                    text=text,
                )
            except Exception as e:
                print(f"[warn] could not load {meta_path}: {e}")
