"""Fetch and extract clean article text using trafilatura."""

import trafilatura

from article import Article


def extract(article: Article) -> Article:
    """
    Fetch an article URL and populate article.text and article.title.
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

    # Extract title if not already set (e.g. for spider-sourced articles)
    if not article.title:
        metadata = trafilatura.extract_metadata(downloaded)
        if metadata and metadata.title:
            article.title = metadata.title

    return article


def extract_all(articles: list[Article]) -> list[Article]:
    """Extract text and title for a list of articles, skipping any that fail."""
    results = []
    for article in articles:
        extract(article)
        if article.text:
            results.append(article)
    return results
