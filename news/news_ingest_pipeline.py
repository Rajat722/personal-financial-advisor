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
from news.noise_filter import is_noise_article as _is_noise_article, is_generic_roundup as _is_generic_roundup
from model.embedder import GeminiEmbedder
from storage.vector_store import upsert_to_collection, get_article_collection

log = get_logger("news_ingest_pipeline")
embedder = GeminiEmbedder()

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Query strategy configuration
# ---------------------------------------------------------------------------
# NewsData.io free plan: 200 credits/day, 1 credit per API call, max 50 results/call.
#
# news_tier in portfolio.json controls query ORDER only — all tiers use one
# individual API call per company (tested: batch queries silently return 0 results
# beyond ~2 comma-separated terms on the free plan).
#
#   Tier 2  → runs FIRST — captures company-specific articles before tier-1's
#             high-volume calls flood the session-level deduplication set.
#
#   Tier 3  → runs SECOND — low-frequency holdings (defensive, dividend, REITs, ETFs).
#
#   Tier 1  → runs LAST — mega-caps generate ~50 articles/call; running last means
#             they deduplicate against tier-2/3 articles, not the other way around.
#
# + 1 fixed macro query for broad market conditions (rates, indices, earnings).
#
# Credit budget (this portfolio):
#   9 tier-2 + 9 tier-3 + 1 macro + 7 tier-1 = 26 calls/run
#   200 ÷ 26 = ~7 runs/day — sufficient for active development.

_MACRO_QUERY: str = "S&P 500,Nasdaq,stock market,earnings,investing"


# ---------------------------------------------------------------------------
def _load_portfolio() -> dict:
    """Load full portfolio data from portfolio.json."""
    with open(ROOT / "user_portfolio" / "portfolio.json", "r") as f:
        return json.load(f)


def _build_query_groups(equities: list[dict]) -> list[tuple[str, str]]:
    """Build all (label, query) pairs from portfolio equity tiers.

    All tiers use one individual API call per company ("CompanyName,TICKER").
    Batch queries (multiple companies per call) were confirmed to return 0
    results on the free plan — the API silently rejects beyond ~2 terms.

    Query order: tier-2 → tier-3 → macro → tier-1.
    """
    by_tier: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    for equity in equities:
        tier = equity.get("news_tier", 3)
        by_tier.setdefault(tier, []).append(equity)

    queries: list[tuple[str, str]] = []

    def _make_query(equity: dict) -> str:
        """Build query string; omit single-char tickers (e.g. T, O) to prevent false matches."""
        ticker = equity["ticker"]
        if len(ticker) == 1:
            return equity["company"]
        return f"{equity['company']},{ticker}"

    # Tier 2: run first — captures unique articles before tier-1 floods dedup set
    for equity in by_tier[2]:
        queries.append((f"tier2:{equity['ticker']}", _make_query(equity)))

    # Tier 3: run second — low-frequency holdings (defensive, dividend, REITs, ETFs)
    for equity in by_tier[3]:
        queries.append((f"tier3:{equity['ticker']}", _make_query(equity)))

    # Macro: fixed market-wide query (covers rates, indices, earnings sentiment)
    queries.append(("macro", _MACRO_QUERY))

    # Tier 1: run LAST — ~50 articles/call; deduplicates against tier-2/3, not vice versa
    for equity in by_tier[1]:
        queries.append((f"tier1:{equity['ticker']}", _make_query(equity)))

    return queries


def _match_article_tickers(raw_keywords: list, portfolio_tickers: list[str]) -> list[str]:
    """Return portfolio tickers that appear in the article's keyword list."""
    if not raw_keywords:
        return []
    kw_upper = {k.upper() for k in raw_keywords}
    return [t for t in portfolio_tickers if t in kw_upper]


def _fetch_all_articles(queries: list[tuple[str, str]]) -> list[dict]:
    """Fetch articles for all query strings; deduplicate by article_id before returning."""
    seen_ids: set[str] = set()
    all_raw: list[dict] = []
    for label, query in queries:
        try:
            log.info(f"Fetching [{label}]: {query[:90]}")
            batch = fetch_finance_news_from_newsdataio(q=query)
            new = [a for a in batch if a.get("article_id") not in seen_ids]
            seen_ids.update(a["article_id"] for a in new if a.get("article_id"))
            all_raw.extend(new)
            log.info(f"  +{len(new)} new articles (running total: {len(all_raw)})")
        except Exception as e:
            log.warning(f"Failed to fetch [{label}]: {e}")
        time.sleep(1)  # brief pause between NewsData calls
    return all_raw


# --- Main ingestion pipeline ---
def ingest_daily_news() -> int:
    """Fetch, embed, and store today's finance articles. Returns count of stored articles."""
    portfolio = _load_portfolio()

    # --- Cleanup: remove articles older than 7 days ---
    try:
        from datetime import datetime, timezone, timedelta
        cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
        col = get_article_collection()
        old_articles = col.get(where={"published_ts": {"$lt": cutoff_ts}})
        old_ids = old_articles.get("ids", [])
        if old_ids:
            col.delete(ids=old_ids)
            log.info(f"Cleanup: removed {len(old_ids)} articles older than 7 days.")
        else:
            log.info("Cleanup: no stale articles to remove.")
    except Exception as e:
        log.warning(f"Cleanup failed (non-fatal): {e}")

    equities = portfolio.get("equities", [])
    portfolio_tickers = [e["ticker"].upper() for e in equities]
    portfolio_sectors = [s.lower() for s in portfolio.get("sectors", [])]

    queries = _build_query_groups(equities)
    log.info(f"Built {len(queries)} queries (~{len(queries)} API credits this run):")
    for label, q in queries:
        log.info(f"  [{label}] {q[:90]}")

    articles = _fetch_all_articles(queries)
    log.info(f"Fetched {len(articles)} unique raw articles across all queries.")

    # Pre-load existing article IDs and titles for deduplication.
    # ID dedup catches exact duplicates; title dedup catches same article from different domains.
    existing_ids: set[str] = set()
    existing_titles: set[str] = set()
    try:
        col = get_article_collection()
        existing = col.get(include=["metadatas"])
        existing_ids = set(existing.get("ids", []))
        existing_titles = {
            m.get("title", "").lower().strip()
            for m in existing.get("metadatas", [])
            if m.get("title")
        }
        log.info(f"{len(existing_ids)} articles already in store — duplicates will be skipped.")
    except Exception as e:
        log.warning(f"Could not load existing IDs for deduplication: {e}")

    stored_count = 0
    noise_count = 0
    roundup_count = 0
    id_dup_count = 0
    title_dup_count = 0
    no_summary_count = 0
    norm_fail_count = 0
    session_titles: set[str] = set()  # title dedup within this run

    for raw in articles:
        try:
            article = normalize_article(
                raw,
                _match_article_tickers(raw.get("keywords", []), portfolio_tickers),
                portfolio_sectors,
            )
        except Exception as e:
            log.warning(f"Skipping article — normalization failed: {e}")
            norm_fail_count += 1
            continue

        if article is None:
            log.warning("Skipping article — normalize_article returned None")
            norm_fail_count += 1
            continue

        # ID-based dedup (exact same article)
        if article.id in existing_ids:
            log.debug(f"Skipping duplicate id: {article.id}")
            id_dup_count += 1
            continue

        # Title-based dedup (same article from different domains or slight variations)
        norm_title = article.title.lower().strip()
        if norm_title in existing_titles or norm_title in session_titles:
            log.debug(f"Skipping duplicate title: {article.title}")
            title_dup_count += 1
            continue

        # Noise filter: institutional holding disclosures and other low-signal articles
        if _is_noise_article(article.title):
            log.debug(f"Filtering noise: {article.title}")
            noise_count += 1
            continue

        # Roundup filter: generic SEO stock-list articles ("Best Tech Stocks To Watch Today")
        if _is_generic_roundup(article.title):
            log.debug(f"Filtering roundup: {article.title}")
            roundup_count += 1
            continue

        if not article.summary:
            log.debug(f"Skipping (no summary): {article.title}")
            no_summary_count += 1
            continue

        try:
            embed_input = (article.title or "") + " — " + (article.summary or "")
            embedding = embedder.embed_text(embed_input)
        except Exception as e:
            log.warning(f"Skipping '{article.title}' — embedding failed: {e}")
            time.sleep(settings.GEMINI_RETRY_DELAY)  # back off on error
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
            "tickers": ",".join(article.tickers),
        }
        document = (article.title or "") + " — " + (article.summary or "")[:1500]

        try:
            upsert_to_collection("articles", article.id, document, embedding, metadata)
            existing_ids.add(article.id)
            session_titles.add(norm_title)
            stored_count += 1
            log.info(f"Stored [{stored_count}]: {article.title}")
        except Exception as e:
            log.warning(f"Failed to store '{article.title}': {e}")

        time.sleep(0.1)  # minimal rate control between Gemini embedding calls

    log.info(
        f"Ingestion complete: {stored_count} stored | "
        f"{noise_count} noise-filtered | "
        f"{roundup_count} roundup-filtered | "
        f"{id_dup_count} id-dups | "
        f"{title_dup_count} title-dups | "
        f"{no_summary_count} no-summary | "
        f"{norm_fail_count} norm-failed"
    )
    return stored_count


if __name__ == "__main__":
    ingest_daily_news()
    log.info("News ingestion for today completed.")
