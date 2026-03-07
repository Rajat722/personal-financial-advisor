# run_test_pipeline.py

import re
import sys
import json
import logging
import pytz
import concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is on sys.path when this file is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logging import get_logger
from model.relevance_filter import find_relevant_articles_from_context, index_portfolio_terms
from utils.stock_details import get_stock_OHLCV_data, format_time_series_table, get_upcoming_earnings
from model.model import summarize_multiple_articles, get_insights_from_news_and_prices, get_end_of_day_summary
from storage.vector_store import get_portfolio_collection

logger = get_logger("pipeline")

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
_EST = pytz.timezone("US/Eastern")

# Log subdirectories
_DIR_RUNS      = LOG_DIR / "pipeline_runs"
_DIR_INSIGHTS  = LOG_DIR / "insights"
_DIR_SUMMARIES = LOG_DIR / "summaries"
_DIR_DIGESTS   = LOG_DIR / "digests"

for _d in (_DIR_RUNS, _DIR_INSIGHTS, _DIR_SUMMARIES, _DIR_DIGESTS):
    _d.mkdir(parents=True, exist_ok=True)


def _log_ts() -> str:
    """Return current EST timestamp string for log filenames."""
    return datetime.now(_EST).strftime("%Y-%m-%dT%H-%M-%S-EST")


def _attach_run_log() -> Path:
    """Attach an INFO-level file handler to the root logger so all module output is saved."""
    log_path = _DIR_RUNS / f"pipeline_run_{_log_ts()}.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s"))
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    return log_path


def save_log(filename: str, subdir: Path, content: dict) -> None:
    """Write content as a timestamped JSON file to the given log subdirectory."""
    path = subdir / f"{filename}_{_log_ts()}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
    logger.info(f"Log saved: {path}")


def save_eod_digest(digest_text: str) -> None:
    """Write the EOD digest as a human-readable markdown file."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = _DIR_DIGESTS / f"digest_{date_str}_{_log_ts()}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Daily Digest — {date_str}\n\n")
        f.write(digest_text)
    logger.info(f"EOD digest saved: {path}")


def _format_earnings_context(earnings: list[dict]) -> str:
    """Format upcoming/recent earnings events into a readable string for the LLM prompt."""
    if not earnings:
        return ""

    def _fmt_rev(val: float | None) -> str:
        if val is None:
            return "N/A"
        if val >= 1e9:
            return f"${val / 1e9:.1f}B"
        if val >= 1e6:
            return f"${val / 1e6:.0f}M"
        return f"${val:,.0f}"

    lines = []
    for e in earnings:
        days = e["days_until"]
        if days < 0:
            when = f"Reported {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
        elif days == 0:
            when = "Reports TODAY"
        else:
            when = f"Reports in {days} day{'s' if days != 1 else ''} ({e['date']})"

        eps = f"${e['eps_avg']:.2f}" if e["eps_avg"] is not None else "N/A"
        eps_range = (
            f" (${e['eps_low']:.2f}–${e['eps_high']:.2f})"
            if e["eps_low"] is not None and e["eps_high"] is not None
            else ""
        )
        lines.append(
            f"- {e['ticker']} ({e['company']}) — {when} | "
            f"EPS est: {eps}{eps_range} | Rev est: {_fmt_rev(e['rev_avg'])}"
        )

    return "\n".join(lines)


def format_article_blocks(articles: list) -> str:
    """Format a list of article dicts into numbered text blocks for LLM prompts."""
    blocks = []
    for i, article in enumerate(articles):
        title = article['metadata'].get("title", f"Untitled Article {i+1}")
        text = article['text']
        blocks.append(f"--- Article {i+1} ---\nTitle: {title}\nText: {text}\n")
    return "\n".join(blocks)


def _fetch_article_body(url: str, timeout: float = 8.0) -> str | None:
    """Attempt to scrape full article text; returns None on failure or timeout.

    Uses a thread so it works on Windows (no SIGALRM). Paywalled and slow
    sites simply return None — the pipeline degrades gracefully to title+description.
    """
    def _scrape() -> str:
        from news.extract_text_from_article import extract_article_text
        return extract_article_text(url)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_scrape)
            return future.result(timeout=timeout)
    except Exception:
        return None


def _enrich_articles_with_full_text(articles: list) -> int:
    """Best-effort: fetch full article body for each passing article and append to text field.

    Only articles where scraping returns >200 chars are enriched (paywalls return near-empty).
    This dramatically improves LLM output quality since it has actual article content,
    not just the 1-3 sentence NewsData.io description. Capped at 3000 chars per article
    to control prompt token usage. Returns count of successfully enriched articles.
    """
    enriched = 0
    for article in articles:
        url = article['metadata'].get('url', '')
        if not url:
            continue
        body = _fetch_article_body(url)
        if body and len(body.strip()) > 200:
            article['text'] = article['text'] + "\n\nFull article text:\n" + body.strip()[:3000]
            enriched += 1
    return enriched


def _extract_relevant_tickers(articles: list, portfolio: dict) -> list[str]:
    """Scan article titles and text to identify which portfolio tickers are covered.

    Uses regex word-boundary matching for ticker symbols (e.g. NVDA, AAPL) and
    first-word matching for company names (e.g. 'Nvidia', 'Apple', 'Microsoft').
    This is independent of article metadata, so it works correctly for both:
    - Old articles (which may have all 25 tickers as fallback in metadata)
    - New articles (which will have only matched tickers or empty)
    Falls back to full portfolio only if zero tickers are found.
    """
    all_tickers = [item["ticker"] for item in portfolio["equities"]]
    ticker_set = set(all_tickers)

    # Map first distinctive word of each company name → ticker.
    # Skip short words (<=4 chars) that produce false matches (e.g. "Meta" is fine, "AT" is not).
    company_to_ticker: dict[str, str] = {}
    for item in portfolio["equities"]:
        for word in item["company"].split():
            if len(word) > 4:
                company_to_ticker[word.lower()] = item["ticker"]
                break  # one key per company

    relevant_tickers: set[str] = set()
    for article in articles:
        title = article['metadata'].get('title', '')
        text_sample = article.get('text', '')[:500]
        combined_lower = (title + " " + text_sample).lower()
        combined_upper = (title + " " + text_sample).upper()

        for ticker in ticker_set:
            if re.search(r'\b' + re.escape(ticker) + r'\b', combined_upper):
                relevant_tickers.add(ticker)

        for company_word, ticker in company_to_ticker.items():
            if company_word in combined_lower:
                relevant_tickers.add(ticker)

    matched = sorted(relevant_tickers & ticker_set)
    return matched if matched else all_tickers


def run_pipeline() -> None:
    log_path = _attach_run_log()
    logger.info(f"Run log: {log_path}")

    # === Step 1: Index portfolio terms (skip if already indexed) ===
    portfolio_collection = get_portfolio_collection()
    if portfolio_collection.count() > 0:
        logger.info(f"Portfolio already indexed ({portfolio_collection.count()} terms). Skipping re-index.")
    else:
        logger.info("Indexing portfolio terms...")
        index_portfolio_terms()
        logger.info(f"Portfolio indexed: {portfolio_collection.count()} terms.")

    # === Step 2: Find relevant articles ===
    logger.info("Scanning articles for portfolio relevance...")
    relevant_articles = find_relevant_articles_from_context()
    logger.info(f"{len(relevant_articles)} relevant articles will be used for the digest.")

    if not relevant_articles:
        logger.error("No relevant articles found. Run news_ingest_pipeline.py first, or lower SIM_THRESHOLD.")
        return

    # === Step 3: Enrich passing articles with full text (best-effort scraping) ===
    # NewsData.io only provides 1-3 sentence descriptions. Full text dramatically
    # improves LLM output — actual analyst quotes, numbers, and event causality.
    # Paywalled articles (WSJ, Bloomberg, etc.) return None and are skipped gracefully.
    logger.info(f"Fetching full article text for {len(relevant_articles)} relevant articles...")
    enriched_count = _enrich_articles_with_full_text(relevant_articles)
    logger.info(f"Full text fetched for {enriched_count}/{len(relevant_articles)} articles.")

    # === Step 4: Format articles into prompt blocks ===
    article_blocks = format_article_blocks(relevant_articles)

    # === Step 5: Identify which portfolio tickers appear in relevant articles ===
    with open(ROOT / "user_portfolio" / "portfolio.json", "r") as f:
        portfolio = json.load(f)

    tickers_to_fetch = _extract_relevant_tickers(relevant_articles, portfolio)
    logger.info(f"Fetching OHLCV data for {len(tickers_to_fetch)} relevant tickers: {tickers_to_fetch}")

    # === Step 5.5: Fetch earnings calendar for all portfolio companies ===
    # Covers past 3 days (recently reported) + next 14 days (upcoming).
    # Injected into the EOD digest prompt as a structured "Upcoming Earnings" section.
    logger.info("Fetching earnings calendar for portfolio companies...")
    earnings = get_upcoming_earnings(portfolio["equities"])
    earnings_context = _format_earnings_context(earnings)
    if earnings:
        logger.info(f"Earnings calendar — {len(earnings)} event(s):\n{earnings_context}")
    else:
        logger.info("No portfolio earnings events in the 3-day lookback + 14-day lookahead window.")

    # === Step 6: Fetch intraday stock data (full 30-min time series for relevant tickers only) ===
    stock_data = get_stock_OHLCV_data(tickers_to_fetch, interval="30m", period="1d")
    logger.info(f"Stock data fetched for {len(stock_data)}/{len(tickers_to_fetch)} tickers.")
    stock_summary_json = json.dumps(format_time_series_table(stock_data), indent=2)

    # === Step 7: Generate insights (news + price correlation) ===
    logger.info("Generating news-price insights via Gemini...")
    try:
        insights_response = get_insights_from_news_and_prices(article_blocks, stock_summary_json)
        logger.info(f"Insights generated ({len(insights_response)} chars).")
        save_log("insights_response", _DIR_INSIGHTS, {"response": insights_response})
    except Exception as e:
        logger.error(f"Failed to get insights: {e}")
        insights_response = "{}"

    # === Step 8: Summarize relevant articles ===
    logger.info(f"Summarizing {len(relevant_articles)} articles via Gemini...")
    try:
        summarized_articles_json = summarize_multiple_articles(article_blocks)
        logger.info(f"Summaries generated ({len(summarized_articles_json)} chars).")
        save_log("summarized_articles", _DIR_SUMMARIES, {"response": summarized_articles_json})
    except Exception as e:
        logger.error(f"Failed to summarize articles: {e}")
        summarized_articles_json = "[]"

    # === Step 9: Generate end-of-day digest ===
    logger.info("Generating end-of-day digest via Gemini...")
    try:
        eod_summary = get_end_of_day_summary(insights_response, summarized_articles_json, earnings_context)
        logger.info(f"EOD digest generated ({len(eod_summary)} chars).")
        save_eod_digest(eod_summary)
        logger.info("\n--- EOD DIGEST ---\n" + eod_summary + "\n--- END DIGEST ---")
    except Exception as e:
        logger.error(f"Failed to generate EOD summary: {e}")

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    run_pipeline()
