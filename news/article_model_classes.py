from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class Article(BaseModel):
    """Normalized representation of a single news article."""

    id: str  # SHA256 fingerprint: domain|norm_title|datepart
    url: str
    source_domain: str
    title: str
    published_at_utc: datetime
    summary: Optional[str] = None
    body: Optional[str] = None  # Full article body text, if extracted
    tickers: List[str] = []
    sectors: List[str] = []


class DigestItem(BaseModel):
    """A single curated item in the end-of-day digest."""

    article_id: str
    url: str
    title: str
    tickers: List[str]
    tldr: str
    why_matters: str
    confidence: str  # "High" | "Medium" | "Low"
    source: str
    published_local: str


class Digest(BaseModel):
    """Full end-of-day digest containing top items, movers, and sector bullets."""

    window: str  # "pre" | "post"
    date_et: str  # e.g., "2025-08-15"
    top_items: List[DigestItem]
    movers: List[dict]  # Simplified for MVP
    sector_bullets: List[str]
    events: List[dict]  # [{"title": ..., "why": ...}]
