from news.article_model_classes import Article
from hashlib import sha256
from urllib.parse import urlparse
from datetime import datetime, timezone

def normalize_article(raw_response: dict, context_tickers: list[str], context_sectors: list[str]) -> "Article | None":
    """Normalize a raw NewsData.io article dict into an Article dataclass with a deterministic SHA256 ID."""
    url = raw_response["link"]
    title = raw_response["title"].strip()
    domain = urlparse(url).netloc.lower()
    pub = datetime.fromisoformat(raw_response["pubDate"]).astimezone(timezone.utc)
    fid = sha256(f"{domain}|{title.lower()}|{pub.date()}".encode()).hexdigest()
    return Article(
        id=fid, url=url, source_domain=domain, title=title,
        summary=raw_response.get("description"), body=None,
        tickers=context_tickers, sectors=context_sectors,
        published_at_utc=pub
    )