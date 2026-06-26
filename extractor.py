"""Fetch and extract clean article text using trafilatura."""

import trafilatura

from article import Article, normalize_date


def extract(article: Article) -> Article:
    """
    Fetch an article URL and populate article.text, article.title, and article.date.
    Returns the same Article object (mutated in place) for easy chaining.
    """
    downloaded = trafilatura.fetch_url(article.url)
    if not downloaded:
        return article

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
        no_fallback=False,       # allow readability-lxml fallback
    )
    if text:
        article.text = text

    # Extract title and date if not already set (e.g. for spider-sourced articles)
    if not article.title or not article.date:
        metadata = trafilatura.extract_metadata(downloaded)
        if metadata:
            if not article.title and metadata.title:
                article.title = metadata.title
            # NEW: Extract publish date from metadata (trafilatura returns datetime-aware or str in some cases)
            if not article.date and metadata.date:
                article.date = normalize_date(metadata.date)

    return article


def extract_all(articles: list[Article]) -> list[Article]:
    """Extract text and title for a list of articles, skipping any that fail."""
    results = []
    for article in articles:
        extract(article)
        if article.text:
            results.append(article)
    return results
