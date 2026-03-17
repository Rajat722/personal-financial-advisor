# run_test_pipeline.py

import re
import sys
import json
import logging
import pytz
import concurrent.futures
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is on sys.path when this file is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logging import get_logger
from core.users import load_all_users, build_master_portfolio, get_all_tickers
from model.relevance_filter import find_relevant_articles_from_context, index_portfolio_terms, build_user_allowed_terms
from utils.stock_details import format_summary_json, format_time_series_table
from model.model import get_insights_from_news_and_prices, generate_editorial_digest
from storage.vector_store import get_portfolio_collection
from pipeline.html_renderer import parse_digest_markdown, render_digest_html
from pipeline.shared_data import fetch_shared_stock_data, fetch_shared_earnings

logger = get_logger("pipeline")

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
_EST = pytz.timezone("US/Eastern")

# Log subdirectories
_DIR_RUNS      = LOG_DIR / "pipeline_runs" / "run_test_pipeline"
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


def format_article_blocks(articles: list, user_portfolio: dict | None = None) -> str:
    """Format article dicts into ticker-grouped text blocks for LLM prompts.

    Articles are grouped by their matched portfolio term (best_match) so the analyst
    model sees all CRWD articles together, all AAPL articles together, etc. This
    dramatically reduces cross-ticker contamination in Call 1 outputs.

    Sectors and indices (broad terms) are grouped last so ticker-specific articles
    appear at the top of the prompt where the model pays closest attention.
    Includes publication date so the LLM can distinguish fresh vs. older articles.
    """
    # Build reverse map: company name (lowercase) -> ticker symbol
    company_to_ticker: dict[str, str] = {}
    if user_portfolio:
        for eq in user_portfolio.get("equities", []):
            ticker = eq.get("ticker", "").upper()
            company = eq.get("company", "")
            if company and ticker:
                company_to_ticker[company.lower()] = ticker

    _TICKER_RE = re.compile(r'^[A-Z][A-Z0-9\-]{0,5}$')

    def _normalize_match(best_match: str) -> str:
        """Map company names back to ticker symbols where possible."""
        if _TICKER_RE.match(best_match):
            return best_match
        return company_to_ticker.get(best_match.lower(), best_match)

    def _is_ticker(term: str) -> bool:
        return bool(_TICKER_RE.match(term))

    # Group articles by normalized term, preserving similarity-score order within each group.
    # Track seen doc_ids to prevent the same article appearing under multiple ticker groups.
    grouped: dict[str, list] = defaultdict(list)
    seen_ids: set[str] = set()
    for article in articles:
        doc_id = article.get("doc_id", "")
        if doc_id and doc_id in seen_ids:
            continue
        if doc_id:
            seen_ids.add(doc_id)
        term = _normalize_match(article.get("best_match", "Unknown"))
        grouped[term].append(article)

    # Order groups: tickers first (sorted), then broad terms (sectors/indices)
    ticker_groups = sorted(k for k in grouped if _is_ticker(k))
    broad_groups = [k for k in grouped if not _is_ticker(k)]
    ordered_groups = ticker_groups + broad_groups

    blocks = []
    article_num = 1
    for term in ordered_groups:
        blocks.append(f"\n=== {term} ===")
        for article in grouped[term]:
            title = article['metadata'].get("title", f"Untitled Article {article_num}")
            published = article['metadata'].get("published_iso", "unknown")
            text = article['text']
            blocks.append(
                f"--- Article {article_num} ---\n"
                f"Title: {title}\n"
                f"Published: {published}\n"
                f"Text: {text}\n"
            )
            article_num += 1
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


def _generate_user_digest(
    user: dict,
    shared_stock_data: dict,
    shared_earnings: list[dict],
) -> None:
    """Generate a complete personalized digest for one user.

    Per-user: article filtering, scraping, Call 1, Call 2, HTML render.
    Shared data (stock prices, earnings) passed in to avoid redundant fetches.
    """
    user_id = user["user_id"]
    user_portfolio = {
        "equities": user["equities"],
        "sectors": user.get("sectors", []),
        "indices": user.get("indices", []),
        "total_investment": user.get("total_investment", 0),
    }
    logger.info(f"[{user_id}] ── Starting digest ({len(user_portfolio['equities'])} holdings) ──")

    # === Find relevant articles for THIS user ===
    allowed_terms = build_user_allowed_terms(user_portfolio)
    logger.info(f"[{user_id}] Filtering articles ({len(allowed_terms)} allowed terms)...")
    relevant_articles = find_relevant_articles_from_context(allowed_terms=allowed_terms)
    logger.info(f"[{user_id}] {len(relevant_articles)} relevant articles found.")

    if not relevant_articles:
        logger.warning(f"[{user_id}] No relevant articles. Skipping.")
        return

    # === Scrape full article text ===
    logger.info(f"[{user_id}] Scraping full text for {len(relevant_articles)} articles...")
    enriched_count = _enrich_articles_with_full_text(relevant_articles)
    logger.info(f"[{user_id}] Scraped {enriched_count}/{len(relevant_articles)} articles.")

    # === Format article blocks (grouped by ticker to prevent cross-ticker contamination) ===
    article_blocks = format_article_blocks(relevant_articles, user_portfolio=user_portfolio)
    article_titles_urls = _build_article_titles_urls(relevant_articles)

    # === Filter shared data to this user's tickers ===
    user_tickers = {e["ticker"] for e in user_portfolio["equities"]}
    user_stock_data = {t: df for t, df in shared_stock_data.items() if t in user_tickers}
    stock_summary_json = json.dumps(format_time_series_table(user_stock_data), indent=2)

    user_earnings = [e for e in shared_earnings if e["ticker"] in user_tickers]
    earnings_context = _format_earnings_context(user_earnings)
    if user_earnings:
        logger.info(f"[{user_id}] Earnings: {len(user_earnings)} event(s)")
    else:
        logger.info(f"[{user_id}] No earnings events in window.")

    # === Call 1 — Analyst insights (per-user articles + per-user prices) ===
    logger.info(f"[{user_id}] Generating analyst insights via Gemini flash-lite...")
    try:
        insights_response = get_insights_from_news_and_prices(article_blocks, stock_summary_json)
        logger.info(f"[{user_id}] Insights generated ({len(insights_response)} chars).")
        save_log(f"insights_{user_id}", _DIR_INSIGHTS, {"response": insights_response})
    except Exception as e:
        logger.error(f"[{user_id}] Failed to get insights: {e}")
        insights_response = "{}"

    # === Build computed sections ===
    portfolio_summary = _build_portfolio_summary(user_stock_data, user_portfolio)
    movers_section = _build_movers_section(user_stock_data, insights_response)

    # === Call 2 — Editorial digest ===
    portfolio_ticker_list = ", ".join(e["ticker"] for e in user_portfolio["equities"])
    logger.info(
        f"[{user_id}] Editorial inputs — insights: {len(insights_response)} chars, "
        f"articles: {len(article_titles_urls)} chars, movers: {len(movers_section)} chars."
    )
    logger.info(f"[{user_id}] Generating editorial digest via Gemini flash...")
    editorial_text = ""
    try:
        editorial_text = generate_editorial_digest(
            insights_json=insights_response,
            portfolio_snapshot=portfolio_summary,
            movers_table=movers_section,
            article_titles_urls=article_titles_urls,
            earnings_context=earnings_context,
            portfolio_tickers=portfolio_ticker_list,
        )
        logger.info(f"[{user_id}] Editorial digest generated ({len(editorial_text)} chars).")
        editorial_text = _cap_key_insights(editorial_text, limit=15)
        prefix_parts = [p for p in [portfolio_summary, movers_section] if p]
        full_digest = "\n\n---\n\n".join(prefix_parts + [editorial_text])

        # Save markdown
        user_md_dir = _DIR_DIGESTS / user_id
        user_md_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        md_path = user_md_dir / f"digest_{user_id}_{date_str}_{_log_ts()}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Daily Digest — {date_str} — {user.get('name', user_id)}\n\n")
            f.write(full_digest)
        logger.info(f"[{user_id}] Markdown saved: {md_path}")

    except Exception as e:
        logger.error(f"[{user_id}] Failed to generate editorial digest: {e}")

    # === Render HTML email ===
    if editorial_text:
        user_html_dir = _DIR_HTML / user_id
        user_html_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[{user_id}] Rendering HTML email...")
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
                holdings_count=len(user_portfolio["equities"]),
            )
            html_path = user_html_dir / f"digest_{user_id}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_{_log_ts()}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_output)
            logger.info(f"[{user_id}] HTML saved: {html_path}")
        except Exception as e:
            logger.error(f"[{user_id}] Failed to render HTML: {e}")

    logger.info(f"[{user_id}] ── Digest complete ──")


def run_pipeline(force: bool = False) -> None:
    log_path = _attach_run_log()
    logger.info(f"Run log: {log_path}")

    # Weekend / market-closed detection
    now_et = datetime.now(_EST)
    day_of_week = now_et.weekday()
    if day_of_week >= 5:
        if not force:
            logger.warning(
                f"Today is {now_et.strftime('%A')} — markets are closed. "
                f"Skipping pipeline. Use --force to run anyway."
            )
            return
        else:
            logger.warning(
                f"Today is {now_et.strftime('%A')} — running anyway due to --force flag."
            )

    # ================================================================
    # SHARED STEPS (run once)
    # ================================================================

    users = load_all_users()
    if not users:
        logger.error("No users found in user_portfolios/. Create user_*.json files first.")
        return
    master_portfolio = build_master_portfolio(users)
    all_tickers = get_all_tickers(users)
    logger.info(f"Loaded {len(users)} user(s), {len(all_tickers)} unique tickers.")

    # Index master portfolio terms
    portfolio_collection = get_portfolio_collection()
    existing_count = portfolio_collection.count()
    expected_terms = len(master_portfolio["equities"]) * 2 + len(master_portfolio["sectors"]) + len(master_portfolio["indices"])
    if existing_count >= expected_terms:
        logger.info(f"Portfolio already indexed ({existing_count} terms). Skipping re-index.")
    else:
        logger.info(f"Indexing master portfolio terms ({existing_count} → ~{expected_terms} expected)...")
        index_portfolio_terms(portfolio_data=master_portfolio)
        logger.info(f"Portfolio indexed: {portfolio_collection.count()} terms.")

    # Fetch shared stock data + earnings
    shared_stock_data = fetch_shared_stock_data(all_tickers)
    shared_earnings = fetch_shared_earnings(master_portfolio["equities"])

    # ================================================================
    # PER-USER DIGEST GENERATION
    # ================================================================
    logger.info("=" * 60)
    logger.info(f"GENERATING DIGESTS FOR {len(users)} USER(S)")
    logger.info("=" * 60)

    successful = 0
    failed = 0
    for user in users:
        try:
            _generate_user_digest(
                user=user,
                shared_stock_data=shared_stock_data,
                shared_earnings=shared_earnings,
            )
            successful += 1
        except Exception as e:
            logger.error(f"[{user['user_id']}] Unhandled error: {e}")
            failed += 1

    logger.info(f"Pipeline complete. {successful}/{len(users)} digests generated"
                f"{f', {failed} failed' if failed else ''}.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the Portfolio Pulse digest pipeline.")
    parser.add_argument("--force", action="store_true", help="Run even on weekends/holidays (market closed).")
    args = parser.parse_args()
    run_pipeline(force=args.force)
