"""Shared data types for the scraper pipeline."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    url: str
    source: str                        # name from sources.yaml
    title: str = ""
    date: datetime | None = None
    text: str = ""                     # populated by extractor
