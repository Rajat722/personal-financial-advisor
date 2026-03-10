# news_ingest_pipeline.py
import sys
import json
import time
from pathlib import Path

# Ensure project root is on sys.path when this file is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.logging import get_logger
from news.normalize import normalize_article
from news.newsdata import fetch_finance_news_from_newsdataio
from model.embedder import GeminiEmbedder
from storage.vector_store import upsert_to_collection, get_article_collection

log = get_logger("news_ingest_pipeline")
embedder = GeminiEmbedder()

ROOT = Path(__file__).resolve().parent.parent

# NewsData free plan: ~10 results per call. Use company names (not tickers) since
# NewsData searches article text. Comma = AND, so keep groups to 2-3 terms max
# to avoid zero results. Each call returns up to 10 articles.
_TICKER_GROUPS = [
    "Apple Microsoft Nvidia",           # mega-cap tech (OR search)
    "Tesla Meta JPMorgan Costco",       # diversified large-cap
    "CrowdStrike Cloudflare Shopify",   # growth / cyber / e-commerce
    "Nvidia semiconductor chip GPU",    # semiconductor deep-dive
    "Verizon Coca-Cola Johnson",        # defensive / dividend
    "AI cloud computing stock market",  # macro / sector terms
]


def _load_portfolio() -> tuple[list[str], list[str]]:
    """Load portfolio tickers and sectors from portfolio.json."""
    portfolio_path = ROOT / "user_portfolio" / "portfolio.json"
    with open(portfolio_path, "r") as f:
        data = json.load(f)
    tickers = [item["ticker"].upper() for item in data.get("equities", [])]
    sectors = [s.lower() for s in data.get("sectors", [])]
    return tickers, sectors


def _match_article_tickers(raw_keywords: list, portfolio_tickers: list[str]) -> list[str]:
    """Return portfolio tickers that appear in the article's keyword list."""
    if not raw_keywords:
        return []
    kw_upper = {k.upper() for k in raw_keywords}
    return [t for t in portfolio_tickers if t in kw_upper]


def _fetch_all_articles() -> list[dict]:
    """Fetch articles for all ticker groups; deduplicate by article_id before returning."""
    seen_ids: set[str] = set()
    all_raw: list[dict] = []
    for group in _TICKER_GROUPS:
        try:
            log.info(f"Fetching news for group: {group}")
            batch = fetch_finance_news_from_newsdataio(q=group)
            new = [a for a in batch if a.get("article_id") not in seen_ids]
            seen_ids.update(a["article_id"] for a in new if a.get("article_id"))
            all_raw.extend(new)
            log.info(f"  +{len(new)} new articles (running total: {len(all_raw)})")
        except Exception as e:
            log.warning(f"Failed to fetch group '{group}': {e}")
        time.sleep(1)  # brief pause between NewsData calls
    return all_raw


# --- Main ingestion pipeline ---
def ingest_daily_news() -> int:
    """Fetch, embed, and store today's finance articles. Returns count of stored articles."""
    portfolio_tickers, portfolio_sectors = _load_portfolio()

    log.info("Fetching news for all portfolio ticker groups...")
    articles = _fetch_all_articles()
    log.info(f"Fetched {len(articles)} unique raw articles across all groups.")

    # Pre-load existing article IDs for deduplication
    existing_ids: set[str] = set()
    try:
        col = get_article_collection()
        existing = col.get(include=[])
        existing_ids = set(existing.get("ids", []))
        log.info(f"{len(existing_ids)} articles already in store — duplicates will be skipped.")
    except Exception as e:
        log.warning(f"Could not load existing IDs for deduplication: {e}")

    stored_count = 0
    for raw in articles:
        # Match article keywords against portfolio tickers for accurate tagging
        article_tickers = _match_article_tickers(
            raw.get("keywords", []), portfolio_tickers
        )
        # Only store tickers that were explicitly keyword-matched.
        # Falling back to all portfolio tickers would poison the ticker metadata
        # and cause the pipeline to fetch OHLCV data for every holding on every run.
        context_tickers = article_tickers
        context_sectors = portfolio_sectors

        try:
            article = normalize_article(raw, context_tickers, context_sectors)
        except Exception as e:
            log.warning(f"Skipping article — normalization failed: {e}")
            continue

        if article is None:
            log.warning("Skipping article — normalize_article returned None")
            continue

        doc_id = article.id

        # Deduplication: skip if already stored
        if doc_id in existing_ids:
            log.info(f"Skipping duplicate: {doc_id}")
            continue

        if not article.summary:
            log.info(f"Skipping (no summary): {article.title}")
            continue

        # Embed title + summary
        try:
            embed_input = (article.title or "") + " — " + (article.summary or "")
            embedding = embedder.embed_text(embed_input)
        except Exception as e:
            log.warning(f"Skipping '{article.title}' — embedding failed: {e}")
            time.sleep(settings.GEMINI_RETRY_DELAY)
            continue

        if embedding is None:
            log.warning(f"Skipping '{article.title}' — embedding returned None")
            continue

        metadata = {
            "url": article.url,
            "title": article.title,
            "source": article.source_domain,
            "published_ts": int(article.published_at_utc.timestamp()),
            "published_iso": article.published_at_utc.isoformat(),
            "tickers": ",".join(article.tickers),  # ChromaDB metadata must be scalar
        }
        document = (article.title or "") + " — " + (article.summary or "")[:1500]

        try:
            upsert_to_collection("articles", doc_id, document, embedding, metadata)
            existing_ids.add(doc_id)
            stored_count += 1
            log.info(f"Stored [{stored_count}]: {article.title}")
        except Exception as e:
            log.warning(f"Failed to store '{article.title}': {e}")

        # Rate-limit: pause between Gemini embedding calls
        time.sleep(settings.GEMINI_RETRY_DELAY)

    log.info(f"Ingestion complete: {stored_count} new articles stored.")
    return stored_count


if __name__ == "__main__":
    ingest_daily_news()
    log.info("News ingestion for today completed.")
