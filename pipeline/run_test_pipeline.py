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
from utils.stock_details import get_stock_OHLCV_data, format_summary_json, format_time_series_table, get_upcoming_earnings
from model.model import get_insights_from_news_and_prices, generate_editorial_digest
from storage.vector_store import get_portfolio_collection
from pipeline.html_renderer import parse_digest_markdown, render_digest_html

logger = get_logger("pipeline")

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
_EST = pytz.timezone("US/Eastern")

# Log subdirectories
_DIR_RUNS      = LOG_DIR / "pipeline_runs"
_DIR_INSIGHTS  = LOG_DIR / "insights"
_DIR_SUMMARIES = LOG_DIR / "summaries"
_DIR_DIGESTS   = LOG_DIR / "digests"
_DIR_HTML      = LOG_DIR / "digests" / "html"

for _d in (_DIR_RUNS, _DIR_INSIGHTS, _DIR_SUMMARIES, _DIR_DIGESTS, _DIR_HTML):
    _d.mkdir(parents=True, exist_ok=True)


def _log_ts() -> str:
    """Return current EST timestamp string for log filenames."""
    return datetime.now(_EST).strftime("%Y-%m-%dT%H-%M-%S-EST")


def _attach_run_log() -> Path:
    """Attach an INFO-level file handler to the root logger so all module output is saved.

    Third-party libraries (httpcore, httpx, chromadb, google) emit DEBUG logs that flood
    the file. Suppress them at WARNING so only application-level INFO logs are written.
    """
    log_path = _DIR_RUNS / f"pipeline_run_{_log_ts()}.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s"))
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)

    # Suppress noisy third-party library loggers
    for noisy in ("httpcore", "httpx", "chromadb", "google", "urllib3", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

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
            # Remove consecutive duplicate lines — scraping artifacts from pagination/disclaimers
            raw_lines = body.strip().splitlines()
            deduped: list[str] = [raw_lines[0]] if raw_lines else []
            for line in raw_lines[1:]:
                if line.strip() != deduped[-1].strip():
                    deduped.append(line)
            body = "\n".join(deduped)
            article['text'] = article['text'] + "\n\nFull article text:\n" + body[:3000]
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


def _build_portfolio_summary(stock_data: dict, portfolio: dict) -> str:
    """Compute portfolio value, day P&L, and top mover from OHLCV data + portfolio holdings."""
    shares_map = {e["ticker"]: (e["shares"], e["avg_cost_basis"]) for e in portfolio["equities"]}
    summary = format_summary_json(stock_data)

    total_value = 0.0
    total_cost = 0.0
    day_pnl = 0.0
    movers: list[tuple[str, float]] = []  # (ticker, day_change_pct)

    for ticker, data in summary.items():
        if ticker not in shares_map:
            continue
        shares, avg_cost = shares_map[ticker]
        close = data["close"]
        open_ = data["open"]
        market_value = shares * close
        total_value += market_value
        total_cost += shares * avg_cost
        day_pnl += shares * (close - open_)
        movers.append((ticker, data["change_percent"]))

    if not movers:
        return ""

    movers.sort(key=lambda x: x[1], reverse=True)
    top_gainer = movers[0]
    top_loser = movers[-1]
    total_gain = total_value - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost else 0.0
    day_sign = "+" if day_pnl >= 0 else ""
    gain_sign = "+" if total_gain >= 0 else ""

    lines = [
        "## Portfolio Snapshot",
        f"**Est. Value:** ${total_value:,.0f}  |  "
        f"**Today's P&L:** {day_sign}${day_pnl:,.0f}  |  "
        f"**Total Gain:** {gain_sign}${total_gain:,.0f} ({gain_sign}{total_gain_pct:.1f}%)",
        f"**Top Gainer:** {top_gainer[0]} ({'+' if top_gainer[1] >= 0 else ''}{top_gainer[1]:.1f}%)  |  "
        f"**Top Loser:** {top_loser[0]} ({top_loser[1]:.1f}%)",
        f"_(Based on {len(movers)} of {len(portfolio['equities'])} holdings with today's data)_",
    ]
    return "\n".join(lines)


def _cap_key_insights(eod_text: str, limit: int = 15) -> str:
    """Post-process the LLM EOD summary to enforce the Key Market Insights bullet cap.

    The LLM is instructed to write ≤15 bullets but sometimes ignores the limit.
    This finds the Key Market Insights block, slices it to `limit` bullets, and
    reinserts it — leaving all other sections untouched.
    """
    # Match the section header and all bullet lines that follow it
    pattern = re.compile(
        r"(Key Market Insights\s*\n)((?:\s*-[^\n]+\n?)+)",
        re.IGNORECASE,
    )
    match = pattern.search(eod_text)
    if not match:
        return eod_text

    bullets_block = match.group(2)
    bullets = [line for line in bullets_block.splitlines() if line.strip().startswith("-")]

    if len(bullets) <= limit:
        return eod_text  # already within limit, nothing to do

    capped = "\n".join(bullets[:limit]) + "\n"
    logger.info(f"Key Market Insights capped: {len(bullets)} → {limit} bullets.")
    return eod_text[: match.start(2)] + capped + eod_text[match.end(2):]


def _truncate_at_sentence(text: str, limit: int = 200) -> str:
    """Truncate text at the last complete sentence within limit chars.

    Finds the last period followed by whitespace or end-of-string within limit.
    Falls back to hard truncation with ellipsis if no sentence boundary is found.
    """
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    # Find last period+space or period at end within the truncated region
    last_period = max(truncated.rfind(". "), truncated.rfind(".\t"))
    if last_period > limit // 2:
        return truncated[:last_period + 1]
    # No sentence boundary found — hard truncate
    return truncated.rstrip() + "…"


def _parse_insights_safe(raw: str) -> list[dict]:
    """Parse Call 1 insights JSON; on full-parse failure, extract valid items individually.

    LLMs occasionally generate one malformed entry (e.g. dropping the 'insight' key name),
    which causes json.loads() to fail for the entire array. This fallback uses a regex to
    recover all well-formed ticker+insight pairs, skipping the corrupt entry.
    """
    if raw.startswith("```"):
        raw = re.sub(r"^```[^\n]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

    try:
        return json.loads(raw).get("insights", [])
    except json.JSONDecodeError as e:
        logger.warning(f"Insights JSON failed full parse ({e}). Falling back to per-item extraction.")

    # Regex fallback: match "ticker": "TICKER" ... "insight": "text" pairs within each object.
    # Handles escaped quotes and newlines inside string values.
    pattern = re.compile(
        r'"ticker"\s*:\s*"([^"]+)".*?"insight"\s*:\s*"((?:[^"\\]|\\.)*)"',
        re.DOTALL,
    )
    items = [
        {"ticker": m.group(1), "insight": m.group(2).replace('\\"', '"').replace('\\n', '\n')}
        for m in pattern.finditer(raw)
        if m.group(1) and m.group(2)
    ]
    logger.warning(f"Per-item extraction recovered {len(items)} insight(s) from malformed JSON.")
    return items


def _build_movers_section(stock_data: dict, insights_response: str) -> str:
    """Build a Movers & Drivers table from OHLCV data and the Gemini insights JSON."""
    summary = format_summary_json(stock_data)
    if not summary:
        return ""

    # Parse insights JSON → best driver string per ticker (first insight = highest quality)
    ticker_drivers: dict[str, str] = {}
    for item in _parse_insights_safe(insights_response):
        t = item.get("ticker", "")
        if t and t not in ticker_drivers and item.get("insight"):
            ticker_drivers[t] = _truncate_at_sentence(item["insight"], limit=200)

    if ticker_drivers:
        logger.info(f"Movers: {len(ticker_drivers)} driver(s) extracted — {sorted(ticker_drivers)}")
    else:
        logger.warning("Movers: no drivers extracted from insights JSON — all rows will show fallback text.")

    rows = sorted(
        [(t, d["change_percent"]) for t, d in summary.items()],
        key=lambda x: abs(x[1]),
        reverse=True,
    )

    lines = ["## Movers & Drivers", "| Ticker | Change | Driver |", "|--------|--------|--------|"]
    for ticker, pct in rows:
        arrow = "▲" if pct >= 0 else "▼"
        sign = "+" if pct >= 0 else ""
        driver = ticker_drivers.get(ticker, "No specific driver identified today.")
        lines.append(f"| **{ticker}** | {arrow} {sign}{pct:.1f}% | {driver} |")
    return "\n".join(lines)


def _build_article_titles_urls(articles: list) -> str:
    """Format article titles and URLs as a simple reference list for the editorial prompt."""
    lines = []
    for i, article in enumerate(articles):
        title = article['metadata'].get('title', f'Untitled {i+1}')
        url = article['metadata'].get('url', '')
        lines.append(f"- \"{title}\" — {url}")
    return "\n".join(lines)


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
    stock_data = get_stock_OHLCV_data(tickers_to_fetch, interval="30m", period="5d")
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

    # === Step 8.5: Build computed sections (no LLM needed) ===
    portfolio_summary = _build_portfolio_summary(stock_data, portfolio)
    movers_section = _build_movers_section(stock_data, insights_response)

    # === Step 9: Generate editorial digest (Call 2: gemini-2.5-flash) ===
    article_titles_urls = _build_article_titles_urls(relevant_articles)
    logger.info(
        f"Editorial prompt inputs — insights: {len(insights_response)} chars, "
        f"article_titles: {len(article_titles_urls)} chars, "
        f"movers: {len(movers_section)} chars, "
        f"portfolio_snapshot: {len(portfolio_summary)} chars."
    )
    logger.info("Generating editorial digest via Gemini flash...")
    try:
        editorial_text = generate_editorial_digest(
            insights_json=insights_response,
            portfolio_snapshot=portfolio_summary,
            movers_table=movers_section,
            article_titles_urls=article_titles_urls,
            earnings_context=earnings_context,
        )
        logger.info(f"Editorial digest generated ({len(editorial_text)} chars).")
        editorial_text = _cap_key_insights(editorial_text, limit=15)
        prefix_parts = [p for p in [portfolio_summary, movers_section] if p]
        full_digest = "\n\n---\n\n".join(prefix_parts + [editorial_text])
        save_eod_digest(full_digest)
        logger.info("\n--- EOD DIGEST ---\n" + full_digest + "\n--- END DIGEST ---")
    except Exception as e:
        logger.error(f"Failed to generate editorial digest: {e}")
        editorial_text = ""

    # === Step 10: Render HTML email ===
    if editorial_text:
        logger.info("Rendering HTML email template...")
        try:
            parsed = parse_digest_markdown(portfolio_summary, movers_section, editorial_text)
            date_display = datetime.now(_EST).strftime("%B %d, %Y")
            html_output = render_digest_html(
                portfolio_snapshot=parsed["portfolio_snapshot"],
                movers=parsed["movers"],
                key_insights=parsed["key_insights"],
                earnings_text=parsed["earnings_text"],
                news_stories=parsed["news_stories"],
                date_str=date_display,
                article_count=len(relevant_articles),
                holdings_count=len(portfolio["equities"]),
            )
            html_path = _DIR_HTML / f"digest_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_{_log_ts()}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_output)
            logger.info(f"HTML email saved: {html_path}")
        except Exception as e:
            logger.error(f"Failed to render HTML email: {e}")

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    run_pipeline()
