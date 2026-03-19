# relevance_filter.py

import json
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from storage.vector_store import get_article_collection, find_similar_in_portfolio, add_to_collection
from model.embedder import GeminiEmbedder
from core.config import settings
from core.logging import get_logger
from news.noise_filter import is_noise_article, is_speculative_article, is_price_alert_article

log = get_logger("relevance_filter")

# Configurable via SIMILARITY_THRESHOLD env var (defaults to settings.SIM_THRESHOLD = 0.75)
SIMILARITY_THRESHOLD: float = settings.SIM_THRESHOLD

# Maximum articles passed to the LLM — keeps prompt size manageable and digest readable.
# Articles are sorted by similarity score descending; only the top N are used.
# Increased from 30 to 40 after tiered time windows (48h max) expanded the candidate pool.
MAX_RELEVANT_ARTICLES: int = 40

# Penalty applied to similarity score for broad-term matches.
# A broad-match article needs raw similarity of ~0.79+ to compete with
# a ticker-specific article at 0.75. Tuned to let major market events
# through (crash articles score 0.85+) while filtering generic commentary.
BROAD_MATCH_PENALTY: float = 0.04

# Penalty applied to articles from low-signal SEO-heavy sources.
# These sites frequently recycle old earnings data, publish templated
# comparison articles, and produce high-volume opinion pieces.
# A penalized article needs raw similarity of ~0.78+ to compete.
# Genuine breaking news from these sources still passes (scores 0.85+).
SOURCE_PENALTY: float = 0.03
_LOW_SIGNAL_SOURCES: set[str] = {
    "fool.com",           # Motley Fool — heavy on "Is X a Buy?" recycled content
    "zacks.com",          # Zacks — templated performance comparisons, recycled earnings
    "investorplace.com",  # InvestorPlace — SEO listicles, opinion pieces
    "247wallst.com",      # 24/7 Wall St — "best stocks" listicles
    "insidermonkey.com",  # Insider Monkey — hedge fund holding roundups
}

# Penalty for articles tagged as containing stale content at ingest time.
# These articles have recent publication dates but reference old events
# (e.g., Q4 2025 earnings discussed in a March 2026 article).
STALE_CONTENT_PENALTY: float = 0.03

# ETF company names are hardcoded — they rarely change and aren't distinguishable
# from stocks in portfolio.json. Sectors and indices are loaded dynamically.
_BROAD_ETF_NAMES: set[str] = {"invesco qqq trust", "spdr s&p 500 etf trust"}

_PORTFOLIO_PATH = Path(__file__).resolve().parent.parent / "user_portfolio" / "portfolio.json"


def _build_broad_match_terms() -> set[str]:
    """Build the set of broad portfolio terms that should receive a similarity penalty.

    Loads sectors and indices from portfolio.json at startup so the set stays
    in sync with the portfolio without manual updates.
    """
    try:
        with open(_PORTFOLIO_PATH, "r") as f:
            data = json.load(f)
        sectors = {s.lower() for s in data.get("sectors", [])}
        indices = {i.lower() for i in data.get("indices", [])}
        return sectors | indices | _BROAD_ETF_NAMES
    except Exception:
        log.warning("Could not load portfolio.json for broad-match terms — using ETF names only.")
        return set(_BROAD_ETF_NAMES)


# Broad portfolio terms that match too many articles. Articles whose best match
# is one of these get a similarity penalty so ticker-specific articles are preferred.
_BROAD_MATCH_TERMS: set[str] = _build_broad_match_terms()

embedder = GeminiEmbedder()

# ---------------------------------------------------------------------------
# Rich description lookup for portfolio terms
# Short bare terms ("AI", "T", "AAPL") embed poorly — use full descriptions
# ---------------------------------------------------------------------------
_TICKER_DESCRIPTIONS: dict[str, str] = {
    "AAPL": "AAPL Apple Inc technology company iPhone Mac iPad App Store services consumer electronics",
    "MSFT": "MSFT Microsoft technology cloud Azure Office Windows enterprise software AI Copilot",
    "NVDA": "NVDA Nvidia GPU graphics semiconductor AI chips data center machine learning",
    "AMZN": "AMZN Amazon e-commerce cloud AWS marketplace logistics retail advertising",
    "GOOG": "GOOG Alphabet Google search advertising YouTube cloud AI Gemini Android",
    "TSLA": "TSLA Tesla electric vehicle EV battery autonomous driving energy storage",
    "META": "META Meta Platforms Facebook Instagram WhatsApp social media advertising VR",
    "BRK-A": "BRK-A Berkshire Hathaway Warren Buffett holding company insurance diversified investment",
    "JPM": "JPM JPMorgan Chase bank financial services investment banking retail lending",
    "COST": "COST Costco wholesale retail membership warehouse consumer staples",
    "CRWD": "CRWD CrowdStrike cybersecurity endpoint protection cloud security threat intelligence",
    "SHOP": "SHOP Shopify e-commerce platform merchant payments online retail software",
    "DKNG": "DKNG DraftKings sports betting online gambling fantasy sports gaming",
    "NET": "NET Cloudflare network security CDN cloud services DDoS protection zero trust",
    "RKLB": "RKLB Rocket Lab aerospace small satellite launch vehicle space defense",
    "CELH": "CELH Celsius Holdings energy drinks beverage consumer health fitness",
    "AXON": "AXON Axon Enterprise law enforcement Taser body camera public safety",
    "JNJ": "JNJ Johnson Johnson healthcare pharmaceutical medical devices consumer health",
    "PG": "PG Procter Gamble consumer goods household products personal care brands",
    "KO": "KO Coca-Cola beverages soft drinks consumer staples brand global",
    "VZ": "VZ Verizon telecommunications wireless 5G broadband internet phone carrier",
    "O": "O Realty Income REIT real estate investment trust retail properties monthly dividend",
    "T": "T AT&T telecommunications wireless 5G broadband TV DirecTV phone carrier",
    "SPY": "SPY SPDR S&P 500 ETF index fund large-cap US equities market benchmark",
    "QQQ": "QQQ Invesco Nasdaq-100 ETF technology index fund growth stocks",
    "PLTR": "PLTR Palantir Technologies data analytics software government defense AI big data",
    "COIN": "COIN Coinbase cryptocurrency exchange bitcoin ethereum crypto trading digital assets",
}

_SECTOR_DESCRIPTIONS: dict[str, str] = {
    "cloud computing": "cloud computing SaaS PaaS IaaS AWS Azure Google Cloud infrastructure software services",
    "ai": "artificial intelligence machine learning neural networks generative AI LLM deep learning GPT",
    "semiconductors": "semiconductor chip manufacturing NVIDIA AMD Intel TSMC GPU CPU wafer fab integrated circuit",
    "large-cap tech": "large-cap technology stocks mega-cap FAANG growth equities tech sector",
    "pharmaceuticals": "pharmaceutical biotech drug development FDA clinical trials medicine healthcare",
}

_INDEX_DESCRIPTIONS: dict[str, str] = {
    "s&p 500": "S&P 500 US stock market large-cap equities benchmark index SPY performance",
    "nasdaq": "Nasdaq technology stock exchange growth companies QQQ composite index",
    "russell 2000": "Russell 2000 small-cap US equities index IWM diversified",
}


def _enrich_term(term: str, term_type: str) -> str:
    """Return a rich description for a portfolio term, falling back to the raw term."""
    key = term.lower()
    if term_type == "ticker":
        return _TICKER_DESCRIPTIONS.get(term.upper(), term)
    if term_type == "sector":
        return _SECTOR_DESCRIPTIONS.get(key, term)
    if term_type == "index":
        return _INDEX_DESCRIPTIONS.get(key, term)
    return term


# --- Load and index portfolio terms from JSON ---
def index_portfolio_terms(path: str | None = None, portfolio_data: dict | None = None) -> None:
    """Load portfolio and upsert enriched descriptions for all tickers, sectors, and indices.

    Args:
        path: Path to a single portfolio JSON file (legacy mode).
        portfolio_data: Pre-built portfolio dict (multi-user mode). Takes precedence over path.
    """
    if portfolio_data is not None:
        data = portfolio_data
    else:
        if path is None:
            path = Path(__file__).resolve().parent.parent / "user_portfolio" / "portfolio.json"
        with open(path, "r") as f:
            data = json.load(f)

    equities = data.get("equities", [])
    sectors = [s.lower() for s in data.get("sectors", [])]
    indices = data.get("indices", [])

    # Index sectors
    for sector in sectors:
        rich_text = _enrich_term(sector, "sector")
        embedding = embedder.embed_text(rich_text)
        add_to_collection("portfolio", f"portfolio-{sector}", sector, embedding, {"type": "portfolio_term"})

    # Index indices
    for idx in indices:
        rich_text = _enrich_term(idx, "index")
        embedding = embedder.embed_text(rich_text)
        add_to_collection("portfolio", f"portfolio-{idx}", idx, embedding, {"type": "portfolio_term"})

    # Index equities: ticker and company name as separate entries
    for item in equities:
        ticker = item.get("ticker", "").upper()
        company = item.get("company", "")

        if ticker:
            rich_ticker = _enrich_term(ticker, "ticker")
            embedding = embedder.embed_text(rich_ticker)
            add_to_collection("portfolio", f"portfolio-{ticker}", ticker, embedding, {"type": "portfolio_term"})

        if company:
            # Company name as a separate entry using the ticker description as context
            rich_company = _TICKER_DESCRIPTIONS.get(ticker, company)
            embedding = embedder.embed_text(rich_company)
            add_to_collection("portfolio", f"portfolio-company-{ticker}", company, embedding, {"type": "portfolio_term"})


def _dedupe_by_title_similarity(articles: list, threshold: float = 0.85) -> list:
    """Remove near-duplicate articles based on title similarity using SequenceMatcher."""
    kept = []
    for article in articles:
        title = article["metadata"].get("title", "").lower()
        is_dup = any(
            SequenceMatcher(None, title, k["metadata"].get("title", "").lower()).ratio() >= threshold
            for k in kept
        )
        if not is_dup:
            kept.append(article)
    dropped = len(articles) - len(kept)
    if dropped:
        log.info(f"Deduplication removed {dropped} near-duplicate articles by title.")
    return kept


def build_user_allowed_terms(user_portfolio: dict) -> set[str]:
    """Build the set of portfolio term strings for per-user article filtering.

    These match the document strings stored in ChromaDB's portfolio collection:
    ticker symbols (uppercase), company names (mixed case), sectors (lowercase),
    and index names (original case). Both original and lowercase versions are
    included for case-insensitive matching.
    """
    terms: set[str] = set()
    for eq in user_portfolio.get("equities", []):
        ticker = eq.get("ticker", "").upper()
        company = eq.get("company", "")
        if ticker:
            terms.add(ticker)
            terms.add(ticker.lower())
        if company:
            terms.add(company)
            terms.add(company.lower())
    for sector in user_portfolio.get("sectors", []):
        terms.add(sector)
        terms.add(sector.lower())
    for index in user_portfolio.get("indices", []):
        terms.add(index)
        terms.add(index.lower())
    return terms


# --- Retrieve relevant articles from the articles collection ---
def find_relevant_articles_from_context(
    max_age_hours: int = 48,
    allowed_terms: set[str] | None = None,
    tier_windows: dict[str, int] | None = None,
    max_articles: int | None = None,
) -> list:
    """Return all articles whose embeddings match the portfolio above the similarity threshold.

    Only considers articles published within the last max_age_hours.
    When tier_windows is provided, each article is further filtered by its matched
    ticker's tier-specific time window (e.g. tier-1=20h, tier-2=36h, tier-3=48h).
    Logs article title, best matching portfolio term, and similarity score for debugging.
    """
    article_collection = get_article_collection()

    # Time-window: fetch the widest window from ChromaDB, then apply per-ticker
    # tier windows after matching. This lets tier-3 articles from 40h ago through
    # while keeping tier-1 articles fresh.
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).timestamp())
    all_articles = article_collection.get(
        where={"published_ts": {"$gte": cutoff_ts}},
        include=["documents", "embeddings", "metadatas"],
    )

    relevant_articles = []

    article_ids = all_articles.get("ids", [])
    total_in_store = article_collection.count()
    log.info(f"Time filter: {len(article_ids)} articles within last {max_age_hours}h (of {total_in_store} total in store)")

    article_texts = all_articles.get("documents", [])
    article_metadatas = all_articles.get("metadatas", [])
    article_embeddings = all_articles.get("embeddings", [])

    log.info(f"Scanning {len(article_ids)} articles against portfolio (threshold={SIMILARITY_THRESHOLD})")

    noise_skipped = 0
    for doc_id, text, metadata, embedding in zip(
        article_ids, article_texts, article_metadatas, article_embeddings
    ):
        if embedding is None:
            log.warning(f"Skipping {doc_id} — embedding is None")
            continue

        title = metadata.get("title", doc_id)

        # Second-line noise filter: catches institutional disclosures that were
        # stored before the ingest-time noise filter was in place.
        if is_noise_article(title):
            log.debug(f"[NOISE] {title[:70]}")
            noise_skipped += 1
            continue

        if is_speculative_article(title):
            log.debug(f"[SPECULATIVE] {title[:70]}")
            noise_skipped += 1
            continue

        if is_price_alert_article(title):
            log.debug(f"[PRICE-ALERT] {title[:70]}")
            noise_skipped += 1
            continue

        try:
            results = find_similar_in_portfolio(embedding, top_k=5)
            distances = results.get("distances", [[]])[0]
            portfolio_docs = results.get("documents", [[]])[0]

            if not distances:
                continue

            # If allowed_terms is set, filter to only matches in this user's portfolio.
            if allowed_terms is not None:
                filtered = [
                    (d, doc) for d, doc in zip(distances, portfolio_docs)
                    if doc.lower() in allowed_terms or doc in allowed_terms
                ]
                if not filtered:
                    continue
                distances, portfolio_docs = zip(*filtered)
                distances = list(distances)
                portfolio_docs = list(portfolio_docs)

            best_distance = min(distances)
            best_similarity = 1.0 - best_distance
            best_match = portfolio_docs[distances.index(best_distance)] if portfolio_docs else "unknown"

            # Penalize broad-term matches so ticker-specific articles are preferred
            is_broad = best_match.lower() in _BROAD_MATCH_TERMS
            effective_similarity = best_similarity - BROAD_MATCH_PENALTY if is_broad else best_similarity

            # Penalize low-signal sources (Motley Fool, Zacks, etc.)
            source_domain = metadata.get("source", "")
            is_low_signal = any(s in source_domain for s in _LOW_SIGNAL_SOURCES)
            if is_low_signal:
                effective_similarity -= SOURCE_PENALTY

            # Penalize articles tagged as containing stale content at ingest
            is_stale_content = metadata.get("content_stale", False)
            if is_stale_content:
                effective_similarity -= STALE_CONTENT_PENALTY

            penalties = []
            if is_broad:
                penalties.append(f"broad:-{BROAD_MATCH_PENALTY}")
            if is_low_signal:
                penalties.append(f"source:-{SOURCE_PENALTY}")
            if is_stale_content:
                penalties.append(f"stale:-{STALE_CONTENT_PENALTY}")
            penalty_str = f" ({', '.join(penalties)})" if penalties else ""

            log.info(
                f"[{'PASS' if effective_similarity >= SIMILARITY_THRESHOLD else 'FAIL'}] "
                f"similarity={best_similarity:.3f}{penalty_str} "
                f"match='{best_match}' | {title[:70]}"
            )

            # ChromaDB returns cosine distances (0=identical). Convert to similarity.
            if effective_similarity >= SIMILARITY_THRESHOLD:
                # Tier-based time filtering: each ticker tier has its own freshness window.
                # Tier-1 (mega-cap) = 20h, tier-2 (mid-cap) = 36h, tier-3 (defensive) = 48h.
                if tier_windows:
                    term_max_hours = tier_windows.get(best_match.lower(), max_age_hours)
                    term_cutoff = int((datetime.now(timezone.utc) - timedelta(hours=term_max_hours)).timestamp())
                    pub_ts = metadata.get("published_ts", 0)
                    if pub_ts < term_cutoff:
                        log.info(
                            f"[STALE] match='{best_match}' window={term_max_hours}h | {title[:70]}"
                        )
                        continue

                relevant_articles.append({
                    "doc_id": doc_id,
                    "text": text,
                    "metadata": metadata,
                    "scores": distances,
                    "best_match": best_match,
                    "best_similarity": effective_similarity,
                })
        except Exception as e:
            log.warning(f"Skipping {doc_id} due to error: {e}")

    # Sort by relevance score descending; cap at max_articles (or default).
    # This keeps the LLM prompt size manageable and the digest readable.
    cap = max_articles if max_articles is not None else MAX_RELEVANT_ARTICLES
    relevant_articles.sort(key=lambda a: a["best_similarity"], reverse=True)
    if len(relevant_articles) > cap:
        log.info(f"Capping to top {cap} articles (dropped {len(relevant_articles) - cap} lower-scored).")
        relevant_articles = relevant_articles[:cap]

    relevant_articles = _dedupe_by_title_similarity(relevant_articles)

    log.info(
        f"Found {len(relevant_articles)} relevant articles out of {len(article_ids)} total "
        f"({noise_skipped} noise-skipped at query time)."
    )
    return relevant_articles


# --- Example usage ---
if __name__ == "__main__":
    matches = find_relevant_articles_from_context()
    print(f"\nFound {len(matches)} relevant articles:\n")
    for i, article in enumerate(matches):
        print(
            f"[{i+1}] {article['metadata'].get('title')}\n"
            f"    best_match={article['best_match']}  similarity={article['best_similarity']:.3f}\n"
            f"    {article['metadata'].get('url')}\n"
        )
