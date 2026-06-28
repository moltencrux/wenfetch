"""Fetch and extract clean article text using trafilatura."""

import trafilatura
from requests_ratelimiter import LimiterSession

from article import Article, normalize_date


def extract(article: Article, session: LimiterSession) -> Article:
    """
    Fetch an article URL and populate article.text, article.title, and article.date.
    Uses the provided rate-limited session for all HTTP requests.
    Returns the same Article object (mutated in place) for easy chaining.
    """
    try:
        response = session.get(article.url, timeout=15)
    except Exception as e:
        return article

    if response.status_code != 200:
        return article

    downloaded = response.text

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    if text:
        article.text = text

    # Extract title and date from metadata if not already set (e.g. spider sources)
    if not article.title or not article.date:
        metadata = trafilatura.extract_metadata(downloaded)
        if metadata:
            if not article.title and metadata.title:
                article.title = metadata.title
            if not article.date and metadata.date:
                article.date = normalize_date(metadata.date)

    return article


def extract_all(articles: list[Article], session: LimiterSession) -> list[Article]:
    """
    Fetch and extract text for a list of articles.
    Returns only articles where extraction succeeded.
    """
    results = []
    for article in articles:
        extract(article, session)
        if article.text:
            results.append(article)
    return results
