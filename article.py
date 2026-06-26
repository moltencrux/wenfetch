"""Shared data types for the scraper pipeline."""

from dataclasses import dataclass
from datetime import datetime, timezone
from dateutil import parser as date_parser  # pip install python-dateutil if needed


def normalize_date(dt: datetime | str | None) -> datetime | None:
    """Normalize date to naive UTC datetime for consistent comparisons/storage.
    Handles datetime (aware/naive), ISO strings, or other parseable strings."""
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            # Try parsing flexible date strings (trafilatura often returns these)
            dt = date_parser.parse(dt)
        except Exception:
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except Exception:
                return None  # unparseable

    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            # Convert aware to naive UTC
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    return None

@dataclass
class Article:
    url: str
    source: str
    title: str = ""
    date: datetime | None = None
    text: str = ""
