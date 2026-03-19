# CLAUDE.md — Portfolio Pulse

Read this fully before making any changes.

---

## Project Status

The core pipeline is **fully functional**: shared ingestion → per-user article filtering → per-user Call 1 + Call 2 → HTML digest. Two test users (rajat: 25 holdings, tester1: 10 holdings) generating correct, personalized digests with no cross-user contamination.

**What's working:**
- [x] Multi-user infrastructure (shared ingestion, per-user everything else)
- [x] Per-user article filtering via `allowed_terms` in `find_relevant_articles_from_context()`
- [x] Ticker-grouped article blocks to prevent LLM cross-contamination
- [x] Doc ID deduplication (prevents same article in multiple ticker groups)
- [x] 4-layer noise filter (institutional, roundup, speculative, price-alert) — 10 pattern fixes/additions as of March 16
- [x] HTML renderer with bold-tolerance regex fix
- [x] Per-user output directories (`logs/digests/{user_id}/`, `logs/digests/html/{user_id}/`)

**Priorities (in order):**
1. **Staleness elimination** — Human-readable article ages, temporal marker scan on insights, stale-content tagging at ingest. See `claude_next_steps.md` for execution plan.
2. **Secondary news source** — Add a second API (Finnhub/Marketaux TBD) for better mid/small-cap coverage.
3. **RKLB-type hallucination guard** — Title keyword guard in `relevance_filter.py` to prevent semantic-similarity false matches.
4. **FastAPI layer** — POST /users/signup, GET /users/{id}/newsletter, POST /newsletter/send.

**Completed:**
- [x] Scheduled ingestion — 3x/day via Windows Task Scheduler
- [x] Gmail SMTP email delivery (commented out for test runs)
- [x] Tiered time windows (tier-1=24h, tier-2=36h, tier-3=48h)
- [x] Source penalty system (fool.com, zacks.com, etc.)
- [x] Noise filter expansion (7 new patterns as of March 18)
- [x] Compact price summary for Call 1 (96% token reduction)
- [x] Per-ticker insight cap (Python enforcement)

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
| Email | Gmail SMTP (App Password) | ✅ (disabled for test runs) |

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
| `model/relevance_filter.py` | Article filtering — tiered time windows (24/36/48h), similarity threshold 0.75, broad-match + source penalties, dedup, per-user `allowed_terms` |
| `pipeline/html_renderer.py` | Markdown → HTML email with styled template |
| `news/noise_filter.py` | Regex patterns: institutional, speculative, price-alert, roundup (17+ patterns as of March 18) |
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
- **Data freshness:** Tiered time windows (tier-1=24h, tier-2=36h, tier-3=48h), 7-day cleanup, publication dates in article blocks
- **Article cap:** 40 articles max per user (sorted by similarity score descending)
- **Source penalty:** 0.03 penalty for low-signal sources (fool.com, zacks.com, investorplace.com, 247wallst.com, insidermonkey.com)
- **Article text:** Capped at 1500 chars per article (`body[:1500]`)

---

## Session Rules

1. **One fix at a time** — change, test, verify, then move on
2. **Provide test commands** — after every change, show how to verify
3. **Do NOT modify `noise_filter.py`** unless patterns are explicitly specified
4. **Do NOT modify `html_renderer.py`** unless explicitly asked
5. **Do NOT modify `model/model.py`** — prompts are stable (unless adding temporal/freshness rules)
6. **Never mix embedding models** — gemini-embedding-001 only
7. **Python-level enforcement** — LLMs ignore numeric limits, enforce in code