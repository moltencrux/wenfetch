"""Shared data types for the scraper pipeline."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    url: str
    source: str
    title: str = ""
    date: datetime | None = None
    text: str = ""
