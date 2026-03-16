# Per-User Article Filtering + Call 1: Restore Digest Quality

Read `CLAUDE.md` first, then read this entire prompt before making any changes.

---

## Why This Change

After the multi-user refactor, digest quality degraded. The root cause: article relevance filtering and Call 1 (analyst insights) run against the **master portfolio** (union of all users' tickers) instead of each user's individual portfolio.

This causes three problems:
1. **Article dilution:** Articles about tester1-only holdings (PLTR, COIN) compete for the shared 40-article cap, displacing articles about rajat-only holdings (DKNG, CELH, RKLB, etc.).
2. **LLM cross-contamination:** Call 1 processes 27 tickers' worth of articles in one prompt, increasing attention spread and causing data leakage between tickers (e.g., AXON's consensus PT appearing in CRWD's entry).
3. **Wasted insight slots:** Insights about non-user tickers are generated and then discarded by the editorial prompt's ticker allowlist.

**The fix:** Move article filtering, scraping, and Call 1 from the shared section into the per-user loop. Each user gets their own 40 articles filtered against their own portfolio, and their own Call 1 — exactly like the single-user pipeline worked before.

Stock data and earnings fetching remain shared (expensive, API-bound). News ingestion remains shared (NewsData API credits).

---

## Architecture After This Change

```
SHARED (runs once):
  1. Load all users → build master portfolio
  2. Index master portfolio terms in ChromaDB
  3. Fetch shared stock data for ALL tickers
  4. Fetch shared earnings for ALL tickers

PER-USER (loops over each user):
  5. Find relevant articles (THIS user's allowed terms only)
  6. Scrape full article text
  7. Format article blocks
  8. Call 1 — Analyst (flash-lite): THIS user's articles + THIS user's prices
  9. Build Portfolio Snapshot + Movers table
  10. Call 2 — Editor (flash): THIS user's insights + snapshot + movers
  11. Render HTML email
```

---

## Task 1: Add Per-User Portfolio Filtering to `find_relevant_articles_from_context()`

**File:** `model/relevance_filter.py`

The function currently queries the `portfolio` ChromaDB collection which contains all users' tickers. We need it to only consider matches against terms belonging to the specific user.

**Step 1a:** Add a helper function to build a user's allowed terms set. Place this right before `find_relevant_articles_from_context()`:

```python
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
```

**Step 1b:** Update the function signature to accept `allowed_terms`:

```python
def find_relevant_articles_from_context(
    max_age_hours: int = 36,
    allowed_terms: set[str] | None = None,
) -> list:
```

**Step 1c:** Change `top_k=3` to `top_k=5` on the `find_similar_in_portfolio` call (currently line 243). With the filter removing non-user matches, we need more candidates.

**Step 1d:** Add the allowed_terms filter inside the scoring loop. Place this block right after `if not distances: continue` and right before `best_distance = min(distances)`:

```python
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
```

**Do NOT change** the time window, noise/speculative/price-alert checks, broad-match penalty, sorting, capping, or dedup logic.

---

## Task 2: Restructure `run_pipeline()` and `_generate_user_digest()`

**File:** `pipeline/run_test_pipeline.py`

**Step 2a:** Update imports — add `build_user_allowed_terms`:

```python
from model.relevance_filter import find_relevant_articles_from_context, index_portfolio_terms, build_user_allowed_terms
```

**Step 2b:** Replace the entire `run_pipeline()` function. The shared section shrinks — only user loading, portfolio indexing, stock data, and earnings remain shared:

```python
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
```

**Step 2c:** Replace the entire `_generate_user_digest()` function with the version below. It now handles everything from article filtering through HTML rendering. The function signature changes — it no longer receives `insights_response`, `article_titles_urls`, or `relevant_article_count` because those are now generated per-user inside the function:

```python
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

    # === Format article blocks ===
    article_blocks = format_article_blocks(relevant_articles)
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
```

**Step 2d:** Remove `save_eod_digest()` if it still exists — replaced by per-user save logic.

**Step 2e:** Make sure the `__main__` block has argparse (it already does — verify it's unchanged):

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the Portfolio Pulse digest pipeline.")
    parser.add_argument("--force", action="store_true", help="Run even on weekends/holidays (market closed).")
    args = parser.parse_args()
    run_pipeline(force=args.force)
```

---

## What NOT to Change

- **Do NOT modify `model/model.py`**
- **Do NOT modify `pipeline/html_renderer.py`** — disclaimer already added
- **Do NOT modify `news/noise_filter.py`**
- **Do NOT modify `news/news_ingest_pipeline.py`**
- **Do NOT modify `core/users.py`**
- **Do NOT modify `pipeline/shared_data.py`**
- **Do NOT modify `storage/vector_store.py`**
- **Do NOT modify `model/embedder.py`**
- **Do NOT change master portfolio indexing** — all users' tickers stay in one ChromaDB collection. Per-user filtering is at query time via `allowed_terms`.
- **Do NOT remove** any helper functions (`_extract_relevant_tickers`, `_build_portfolio_summary`, `_cap_key_insights`, `_truncate_at_sentence`, `_parse_insights_safe`, `_build_movers_section`, `_build_article_titles_urls`, `format_article_blocks`, `_enrich_articles_with_full_text`, `_fetch_article_body`, `_format_earnings_context`, `save_log`) — all still used.

---

## Validation

Run (use `--force` on weekends):
```bash
python pipeline/run_test_pipeline.py --force
```

Verify in the pipeline log:

1. **Shared steps run ONCE** — stock data for 27 tickers fetched once before per-user section
2. **Different article counts per user** — rajat ~30-40, tester1 ~20-30. If both show exactly 40, the filter isn't working.
3. **Separate Call 1 per user** — `insights_rajat_*.json` and `insights_tester1_*.json` in `logs/insights/`
4. **No cross-user ticker contamination** — rajat's insights have no PLTR/COIN, tester1's have no DKNG/RKLB/CELH
5. **Both users complete** — "Pipeline complete. 2/2 digests generated."
6. **Per-user output dirs** — `logs/digests/rajat/`, `logs/digests/tester1/`, `logs/digests/html/rajat/`, `logs/digests/html/tester1/`

---

## Summary

| File | Action | Details |
|------|--------|---------|
| `model/relevance_filter.py` | Add `allowed_terms` + helper | `build_user_allowed_terms()`, `allowed_terms` param on `find_relevant_articles_from_context()`, `top_k` 3→5 |
| `pipeline/run_test_pipeline.py` | Restructure | Shared section shrinks to Steps 1-3. `_generate_user_digest()` handles article filtering, scraping, Call 1, Call 2, HTML. Per-user loop. |