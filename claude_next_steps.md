# Data Freshness Fix: Time-Window Articles + Portfolio Ticker Allowlist

Read `CLAUDE.md` first, then read this entire prompt before making any changes.

---

## Why This Change

The pipeline has a fundamental data quality problem: `find_relevant_articles_from_context()` in `model/relevance_filter.py` calls `article_collection.get()` which returns **every article ever stored in ChromaDB** — no date filter, no recency preference. Articles from 5 days ago and articles from today are treated identically, ranked only by embedding similarity.

This causes three concrete bugs visible in recent digests:

1. **Stale facts presented as today's news.** The March 11 digest attributed "Elon Musk predicted 10 billion humanoid robots by 2040" to NVDA — this was from an old Tesla/AI article that matched NVDA by embedding similarity. It's days-old, and the attribution is wrong.

2. **The LLM correlates old news with today's prices.** Call 1 receives 40 articles (many from prior days) plus today's OHLCV data and is asked to correlate them. RKLB was top gainer (+2.8%) but its Movers driver said "shares dropped 3.6%" — from a days-old article about a different day's price action. The model is being asked to do something logically impossible.

3. **Article slots wasted on old content.** The 40-article cap means stale articles with high similarity scores crowd out today's fresh articles.

Every article already has `published_ts` (integer Unix timestamp) stored in its ChromaDB metadata. The fix is straightforward.

---

## Task 1: Time-Window the Relevance Filter

**File:** `model/relevance_filter.py`

**Change:** Modify `find_relevant_articles_from_context()` to only consider articles published within the last 36 hours. 36 hours (not 24) gives buffer for articles published late evening that are still market-relevant the next morning.

Add `max_age_hours` as a parameter with default 36. Add the needed imports at the top of the file.

**Current code (line 147-148):**
```python
article_collection = get_article_collection()
all_articles = article_collection.get(include=["documents", "embeddings", "metadatas"])
```

**New code:**
```python
article_collection = get_article_collection()

# Time-window: only consider articles published within max_age_hours.
# Every article has published_ts (int Unix timestamp) in metadata.
cutoff_ts = int((datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).timestamp())
all_articles = article_collection.get(
    where={"published_ts": {"$gte": cutoff_ts}},
    include=["documents", "embeddings", "metadatas"],
)
```

Update the function signature to accept the time window:
```python
def find_relevant_articles_from_context(max_age_hours: int = 36) -> list:
```

Add the imports at the top of `relevance_filter.py` (add to existing imports):
```python
from datetime import datetime, timezone, timedelta
```

**Also add logging** so you can see how the time filter affects article count:
```python
total_in_store = article_collection.count()
log.info(f"Time filter: {len(article_ids)} articles within last {max_age_hours}h (of {total_in_store} total in store)")
```

Place this log line right after the `article_ids = all_articles.get("ids", [])` line.

**Important:** The `where` clause on `.get()` is a ChromaDB feature — it filters by metadata fields before returning results. This is different from `.query()` (which searches by embedding). We want `.get()` with `where` because we still need to do our own similarity comparison against the portfolio embeddings afterwards.

---

## Task 2: Include Publication Date in Article Blocks Sent to LLM

**File:** `pipeline/run_test_pipeline.py`

**Change:** Modify `format_article_blocks()` to include the article's publication date. This lets Call 1 distinguish between a March 7 COST earnings article and a March 11 COST tariff article, and prevents the LLM from treating all articles as "today's news."

**Current code (lines 119-126):**
```python
def format_article_blocks(articles: list) -> str:
    """Format a list of article dicts into numbered text blocks for LLM prompts."""
    blocks = []
    for i, article in enumerate(articles):
        title = article['metadata'].get("title", f"Untitled Article {i+1}")
        text = article['text']
        blocks.append(f"--- Article {i+1} ---\nTitle: {title}\nText: {text}\n")
    return "\n".join(blocks)
```

**New code:**
```python
def format_article_blocks(articles: list) -> str:
    """Format a list of article dicts into numbered text blocks for LLM prompts.

    Includes publication date so the LLM can distinguish fresh vs. older articles
    and avoid attributing stale facts to today's price movements.
    """
    blocks = []
    for i, article in enumerate(articles):
        title = article['metadata'].get("title", f"Untitled Article {i+1}")
        published = article['metadata'].get("published_iso", "unknown")
        text = article['text']
        blocks.append(
            f"--- Article {i+1} ---\n"
            f"Title: {title}\n"
            f"Published: {published}\n"
            f"Text: {text}\n"
        )
    return "\n".join(blocks)
```

---

## Task 3: Add Portfolio Ticker Allowlist to Editorial Prompt

**File:** `model/model.py`

**Problem (P1 from dev log):** Non-portfolio tickers (MU, AMAT) appeared in Key Insights because Call 1 extracted insights for tickers mentioned in articles that passed relevance filtering (e.g., an "AI trade" article mentioning MU and AMAT passed because it matched QQQ embeddings). The editorial prompt says "Do NOT mention tickers not in insights data" — but the insights data itself now contains non-portfolio tickers.

**Fix:** Pass the portfolio ticker list to the editorial prompt and add a hard allowlist rule.

**Step 3a:** Update `build_editorial_prompt()` signature to accept a ticker list. Add a new parameter:

```python
def build_editorial_prompt(
    insights_json: str,
    portfolio_snapshot: str,
    movers_table: str,
    article_titles_urls: str,
    earnings_context: str = "",
    portfolio_tickers: str = "",
) -> str:
```

**Step 3b:** Add this rule to the `=== STRICT RULES ===` section of the editorial prompt, right after the existing "Do NOT mention any ticker not present in the insights data" line:

```
- PORTFOLIO TICKER ALLOWLIST: You may ONLY mention the following tickers. Any ticker not in this list must be completely excluded from Key Insights, News That Mattered, and all other sections — even if it appears in the analyst insights JSON. Non-portfolio tickers sometimes leak into insights via cross-article contamination.
  ALLOWED TICKERS: {portfolio_tickers}
```

**Step 3c:** Update `generate_editorial_digest()` to accept and pass through the ticker list:

```python
@gemini_retry(max_attempts=settings.GEMINI_RETRY_ATTEMPTS, base_delay=settings.GEMINI_RETRY_DELAY)
def generate_editorial_digest(
    insights_json: str,
    portfolio_snapshot: str,
    movers_table: str,
    article_titles_urls: str,
    earnings_context: str = "",
    portfolio_tickers: str = "",
) -> str:
    """Generate the editorial newsletter via Gemini flash (Call 2)."""
    prompt = build_editorial_prompt(
        insights_json, portfolio_snapshot, movers_table, article_titles_urls,
        earnings_context, portfolio_tickers,
    )
    return _generate(prompt, model=settings.GEMINI_EDITORIAL_MODEL)
```

**Step 3d:** Update the call site in `pipeline/run_test_pipeline.py` (around line 458) to pass the ticker list:

```python
    # Build portfolio ticker allowlist for editorial prompt
    portfolio_ticker_list = ", ".join(e["ticker"] for e in portfolio["equities"])

    editorial_text = generate_editorial_digest(
        insights_json=insights_response,
        portfolio_snapshot=portfolio_summary,
        movers_table=movers_section,
        article_titles_urls=article_titles_urls,
        earnings_context=earnings_context,
        portfolio_tickers=portfolio_ticker_list,
    )
```

---

## Task 4: Add ChromaDB Stale Article Cleanup to Ingestion Pipeline

**File:** `news/news_ingest_pipeline.py`

**Change:** Add a cleanup step at the start of `ingest_daily_news()` that deletes articles older than 7 days. This prevents the ever-growing archive problem and keeps ChromaDB fast.

Add this right after the `portfolio = _load_portfolio()` line (around line 126), before the query building:

```python
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
```

This is defensive — if it fails, ingestion continues normally. The `$lt` operator is the opposite of the `$gte` used in the relevance filter.

---

## Task 5: Update `build_insight_prompt()` with Date Awareness

**File:** `model/model.py`

**Change:** Now that article blocks include a `Published:` date, update the insight prompt's STRICT RULES to tell Call 1 to be aware of article dates. Add this rule to the existing `build_insight_prompt()` STRICT RULES block:

```
- TEMPORAL AWARENESS: Each article includes a "Published:" date. When correlating articles with today's price data, strongly prefer articles published within the last 24 hours. If an article is older than 2 days, note the publish date in the "support" field and mark the insight as potentially stale. Do NOT attribute price movements today to articles published 3+ days ago — the market has already priced in that information.
```

Add this as a new bullet in the existing STRICT RULES list, right after the QUALITY THRESHOLD rule. Do NOT remove or modify any existing rules.

---

## What NOT to Change

- **Do NOT modify `news/noise_filter.py`** — no regex pattern changes.
- **Do NOT modify `pipeline/html_renderer.py`** — HTML rendering is working.
- **Do NOT modify `model/embedder.py`** — embeddings are working.
- **Do NOT modify `storage/vector_store.py`** — ChromaDB wrapper is fine.
- **Do NOT modify `_build_portfolio_summary()`** — working.
- **Do NOT modify `_build_movers_section()`** — working (has JSON fallback already).
- **Do NOT modify `_parse_insights_safe()`** — working.
- **Do NOT modify `_cap_key_insights()`** — working.
- **Do NOT modify `_enrich_articles_with_full_text()`** — working.
- **Do NOT add any new LLM calls or pipeline steps.**
- **Do NOT change the editorial prompt structure** beyond adding the ticker allowlist rule.
- **Do NOT change the insight prompt structure** beyond adding the temporal awareness rule.

---

## Validation

After all changes:

**Step 1:** Clear ChromaDB and re-ingest to test cleanup:
```bash
python news/news_ingest_pipeline.py
```
Check logs for "Cleanup: removed N articles older than 7 days" or "no stale articles to remove."

**Step 2:** Run the full pipeline:
```bash
python pipeline/run_test_pipeline.py
```

**Step 3:** Check `logs/pipeline_runs/` for the latest run log. Verify:
1. **Time filter log line appears:** "Time filter: X articles within last 36h (of Y total in store)" — X should be ≤ Y, and the difference represents old articles excluded.
2. **Article blocks include dates:** In the insights log (`logs/insights/`), article blocks should now show `Published: 2026-03-11T...` dates.
3. **No non-portfolio tickers in Key Insights:** Check the digest output in `logs/digests/`. MU, AMAT, and any other non-portfolio tickers should be absent from Key Insights and News That Mattered.
4. **Movers drivers match today's context:** RKLB's driver should reference today-relevant information, not "shares dropped 3.6% during mid-day trading" from a different day.
5. **Digest is shorter and higher quality:** With only ~36h of articles instead of the full archive, you should see fewer articles passing relevance (likely 20-30 instead of 40), leading to a tighter, more focused digest.

---

## Summary of Changes

| File | Action | Details |
|------|--------|---------|
| `model/relevance_filter.py` | Modify `find_relevant_articles_from_context()` | Add `max_age_hours` param, time-window `.get()` with `where` clause on `published_ts`, add datetime imports, add log line showing filtered vs total count |
| `pipeline/run_test_pipeline.py` | Modify `format_article_blocks()` | Add `Published: {published_iso}` line to each article block |
| `pipeline/run_test_pipeline.py` | Modify editorial call site | Build `portfolio_ticker_list` string from portfolio, pass as new param to `generate_editorial_digest()` |
| `model/model.py` | Modify `build_editorial_prompt()` | Add `portfolio_tickers` param, add PORTFOLIO TICKER ALLOWLIST rule to STRICT RULES |
| `model/model.py` | Modify `generate_editorial_digest()` | Add `portfolio_tickers` param, pass through to prompt builder |
| `model/model.py` | Modify `build_insight_prompt()` | Add TEMPORAL AWARENESS rule to existing STRICT RULES block |
| `news/news_ingest_pipeline.py` | Modify `ingest_daily_news()` | Add 7-day stale article cleanup at start of function |
| `CLAUDE.md` | Update | Add time-window filter and ticker allowlist to completed items |