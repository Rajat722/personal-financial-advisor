from pydantic import AnyUrl
from datetime import datetime

class Article():
    id: str                    # fingerprint: domain|norm_title|datepart
    url: AnyUrl
    source_domain: str
    title: str
    summary: str | None = None
    body: str | None = None
    tickers: list[str] = []
    sectors: list[str] = []
    published_at_utc: datetime
    def __init__(self, url, source_domain, title, summary, body=None, tickers=None, sectors=None, published_at_utc=None):
        self.url = url
        self.source_domain = source_domain
        self.title = title
        self.summary = summary
        self.body = body if body != None else None
        self.tickers = tickers if tickers != None else None
        self.sectors = sectors if sectors != None else None
        self.published_at_utc = published_at_utc if published_at_utc != None else None

class DigestItem():
    article_id: str
    url: AnyUrl
    title: str
    tickers: list[str]
    tldr: str
    why_matters: str
    confidence: str           # "High" | "Medium" | "Low"
    source: str
    published_local: str

class Digest():
    window: str               # "pre" | "post"
    date_et: str              # e.g., "2025-08-15"
    top_items: list[DigestItem]
    movers: list[dict]        # simplified for MVP
    sector_bullets: list[str]
    events: list[dict]        # [{title, why}]
