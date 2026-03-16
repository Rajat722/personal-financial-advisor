# CLAUDE.md — Portfolio Pulse

Read this fully before making any changes.

---

## Current Priority

**Per-user article filtering + Call 1 to restore digest quality.**

The multi-user infrastructure is working (shared ingestion, stock data, earnings, per-user Call 2 + HTML). But digest quality degraded because article filtering and Call 1 run against the master portfolio (union of all users) instead of per-user. Articles for non-user tickers dilute the 40-article window and cause LLM cross-contamination.

**Current task:**
- [ ] Move article filtering, scraping, and Call 1 from shared section to per-user loop
- [ ] Add `allowed_terms` parameter to `find_relevant_articles_from_context()` for per-user filtering
- [ ] Each user gets their own 40 articles + their own Call 1

**Validation:** `python pipeline/run_test_pipeline.py --force` → verify different article counts per user, separate insight logs, no cross-user ticker contamination.

---

## What This Project Does

AI-powered personalized finance newsletter: fetches news → filters by relevance to user's portfolio → generates per-user digest → renders HTML email.

**Target user:** Retail investor (25-35) who holds 5-20 stocks and wants curated, portfolio-specific news.

---

## Tech Stack

| Layer | Tech | Status |
|-------|------|--------|
| LLM (extraction) | Gemini `gemini-2.5-flash-lite` | ✅ Call 1 (per-user) |
| LLM (editorial)  | Gemini `gemini-2.5-flash` | ✅ Call 2 (per-user) |
| Embeddings | Gemini `gemini-embedding-001` (3072-dim) | ✅ |
| Vector DB | ChromaDB (local) | ✅ |
| News API | NewsData.io | ✅ |
| Stock Data | yfinance (`period=5d`) | ✅ |
| HTML Renderer | `pipeline/html_renderer.py` | ✅ |
| Multi-user | `user_portfolios/user_*.json` | ✅ |
| Email | MailerSend | 🔲 Next |

---

## Architecture

```
SHARED (runs once):
  1. Load all users → build master portfolio
  2. Index master portfolio terms in ChromaDB
  3. Fetch shared stock data + earnings for ALL tickers

PER-USER (loop):
  4. Find relevant articles (allowed_terms filter for THIS user)
  5. Scrape full article text
  6. Format article blocks (with publication dates)
  7. Call 1 — Analyst (flash-lite): user's articles + user's prices → insights JSON
  8. Build Portfolio Snapshot + Movers table (Python)
  9. Call 2 — Editor (flash): user's insights + snapshot + movers → editorial digest
  10. Render HTML email

News Ingestion (separate step, runs 1-3x daily):
  NewsData.io → noise/speculative/price-alert filters → embed → ChromaDB
  Uses master portfolio (union of all user tickers)
  7-day stale article cleanup
```

---

## Key Files

| File | Purpose |
|------|---------|
| `pipeline/run_test_pipeline.py` | Main orchestration — shared steps + per-user loop |
| `model/model.py` | LLM prompts — Call 1 (analyst) + Call 2 (editorial) |
| `model/relevance_filter.py` | Article filtering — 36h window, similarity, broad-match penalty, dedup |
| `pipeline/html_renderer.py` | Markdown → HTML email with styled template |
| `news/noise_filter.py` | Regex patterns: institutional, speculative, price-alert, roundup |
| `news/news_ingest_pipeline.py` | Fetch + filter + embed + store articles |
| `core/users.py` | Multi-user loader: `load_all_users()`, `build_master_portfolio()` |
| `pipeline/shared_data.py` | Shared stock data + earnings fetch |
| `core/config.py` | All settings (API keys, models, thresholds) |
| `user_portfolios/user_*.json` | Per-user portfolio files |

---

## Commands

```bash
# Daily workflow:
python news/news_ingest_pipeline.py      # Ingest articles (shared)
python pipeline/run_test_pipeline.py     # Generate digests (per-user)
python pipeline/run_test_pipeline.py --force  # Run on weekends

# Clear ChromaDB:
rm -rf chroma_store/
```

---

## Coding Standards

- **Logging:** `from core.logging import get_logger` — never `print()`
- **Embeddings:** `gemini-embedding-001` only, 3072-dim, always null-check
- **ChromaDB:** Two collections: `portfolio`, `articles`. Cosine metric.
- **LLM Prompts:** STRICT RULES anti-hallucination block in every prompt
- **Error handling:** try/except on all API calls, `@gemini_retry()`, `_parse_insights_safe()` with regex fallback
- **Python enforcement:** Hard caps on Key Insights (15) and News (8) via `_cap_key_insights()`
- **Data freshness:** 36h time window, 7-day cleanup, publication dates in article blocks
- **Article text:** Capped at 1500 chars per article (`body[:1500]`)

---

## Session Rules

1. **Current task first** — complete per-user Call 1 refactor before new features
2. **One fix at a time** — change, test, verify, then move on
3. **Provide test commands** — after every change, show how to verify
4. **Do NOT modify `noise_filter.py`** unless patterns are explicitly specified
5. **Do NOT modify `html_renderer.py`** unless explicitly asked
6. **Do NOT modify `model/model.py`** — prompts are stable
7. **Never mix embedding models** — gemini-embedding-001 only
8. **Python-level enforcement** — LLMs ignore numeric limits, enforce in code