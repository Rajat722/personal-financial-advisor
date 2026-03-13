# CLAUDE.md — Personal Finance Newsletter

Read this fully before making any changes.

---

## Current Priority

**Data freshness + pipeline reliability before first users.**

The pipeline runs end-to-end and produces a polished HTML email digest. The focus is now on ensuring the data feeding the LLM is fresh and accurate, and preventing non-portfolio tickers from leaking into the output.

**Completed (March 8-13):**
- [x] ... (all existing items)
- [x] 36-hour time-window filter on article relevance
- [x] Publication date included in article blocks sent to LLM
- [x] Portfolio ticker allowlist in editorial prompt
- [x] ChromaDB stale article cleanup (>7 days) in ingestion pipeline
- [x] Temporal awareness rule in analyst prompt
- [x] Broad-term similarity penalty (S&P 500, Nasdaq, QQQ matches deprioritized)
- [x] Speculative/opinion article filter (Can X Reach, Where Will X Be, If You Invested)
- [x] Expanded institutional disclosure entity indicators (Ltda, Pte, GmbH, etc.)
- [x] URL slug noise pattern (hyphen-separated lowercase titles)
- [x] Dollar-amount position noise pattern (Takes/Builds $X Million Position in)
- [x] Price-alert article filter ("— Time to Buy?" / "— Time to Sell?" opinion hooks)
- [x] PRICE-ONLY ARTICLES rule in analyst prompt (no circular price-movement insights)
- [x] DRIVER ORDERING rule in analyst prompt (most recent event first per ticker)
- [x] News That Mattered dedup rule fixed (stories can appear in both sections)

**Current tasks:**
- [ ] (none — Phase 0.7 data freshness tasks complete)

**Validation:** `python pipeline/run_test_pipeline.py` → check `logs/digests/` and `logs/digests/html/` for latest output.

---

## What This Project Does

AI-powered finance newsletter: fetches news → filters by relevance and recency → generates personalized digest → renders HTML email.

**Target user:** Beginner-to-intermediate retail investor (25-35, Gen Z/millennial) who holds 5-20 stocks and wants curated, portfolio-specific news without the noise.

**Core insight:** Most financial news is irrelevant. This surfaces only what matters to YOUR holdings, from the last 36 hours.

---

## Tech Stack

| Layer | Tech | Status |
|-------|------|--------|
| AI Pipeline | Python | ✅ Working |
| LLM (extraction) | Gemini `gemini-2.5-flash-lite` | ✅ Call 1 |
| LLM (editorial)  | Gemini `gemini-2.5-flash`      | ✅ Call 2 |
| Embeddings | Gemini `gemini-embedding-001` (3072-dim) | ✅ Working |
| Vector DB | ChromaDB (local, `chroma_store/`) | ✅ Working |
| News | NewsData.io (~120 articles/run) | ✅ Working |
| Stock Data | yfinance (OHLCV + earnings, `period=5d`) | ✅ Working |
| HTML Renderer | `pipeline/html_renderer.py` | ✅ Working |
| Email | MailerSend | 🔲 Not started |
| Backend API | FastAPI | 🔲 Phase 1 |
| Frontend | No-code (Framer/Carrd) | 🔲 Phase 3 |

---

## Project Structure

```
├── model/
│   ├── model.py              # LLM prompts — Call 1 (analyst) + Call 2 (editorial)
│   ├── relevance_filter.py   # Article filtering + time-window + deduplication
│   └── embedder.py           # Gemini embeddings (3072-dim)
├── pipeline/
│   ├── run_test_pipeline.py  # Main orchestration (Steps 1-10)
│   └── html_renderer.py      # Markdown → HTML email renderer
├── news/
│   ├── news_ingest_pipeline.py  # Fetch + embed + store articles
│   ├── noise_filter.py          # Noise patterns (institutional disclosures, roundups)
│   ├── newsdata.py              # NewsData.io API wrapper
│   └── normalize.py             # Raw article → Article dataclass
├── storage/
│   └── vector_store.py       # ChromaDB wrapper
├── user_portfolio/
│   └── portfolio.json        # Test portfolio (25 equities, 3 tiers)
├── logs/
│   ├── digests/              # Final EOD digests (.md)
│   ├── digests/html/         # HTML email outputs
│   ├── pipeline_runs/        # Full run logs
│   ├── insights/             # Call 1 JSON responses
│   └── dev_logs/             # Session dev logs
└── chroma_store/             # ChromaDB persistence
```

---

## Commands

```bash
# Daily workflow (run in order):
python news/news_ingest_pipeline.py    # Step 1: Fetch and store today's articles
python pipeline/run_test_pipeline.py   # Step 2: Generate digest from recent articles

# Clear ChromaDB (when noise filter changes or data is stale)
rm -rf chroma_store/

# Check ChromaDB state
python -c "import chromadb; c = chromadb.PersistentClient(path='chroma_store'); print([(col.name, col.count()) for col in c.list_collections()])"

# Run tests
python -m pytest tests/ -v
```

---

## Environment Variables

All via `core/config.py` — never use `os.environ` directly.

```env
GEMINI_API_KEY=...
GEMINI_FALLBACK_API_KEY=...          # optional secondary key
NEWSDATA_API_KEY=...
NEWSDATA_FALLBACK_API_KEY=...        # optional secondary key
SIM_THRESHOLD=0.75                   # Cosine similarity cutoff
GEMINI_EXTRACT_MODEL=gemini-2.5-flash-lite   # Call 1
GEMINI_EDITORIAL_MODEL=gemini-2.5-flash      # Call 2
```

---

## Coding Standards

**Logging:** Never `print()`. Use `from core.logging import get_logger`.

**Embeddings:** Gemini `gemini-embedding-001` only, 3072-dim. Always null-check.

**ChromaDB:** Two collections only: `portfolio`, `articles`. Cosine metric. Articles have `published_ts` (int Unix timestamp) in metadata for time-window filtering.

**LLM Prompts:** Every prompt includes STRICT RULES anti-hallucination block. Call 1 (analyst) is strict/factual. Call 2 (editor) adds editorial voice but facts must trace to Call 1 output.

**Error handling:** Wrap external API calls in try/except. Use `@gemini_retry()`. JSON parsing uses `_parse_insights_safe()` with regex fallback.

**Data freshness:** Relevance filter only considers articles from the last 36 hours. Ingestion pipeline cleans up articles older than 7 days. Article blocks sent to LLM include publication dates.

---

## Pipeline Architecture (2-Call)

```
News Ingestion (separate step):
  NewsData.io → noise filter → embed → ChromaDB

Pipeline (single run):
  Step 1:  Index portfolio terms (skip if exists)
  Step 2:  Find relevant articles (36h window + similarity ≥ 0.75 + dedup)
  Step 3:  Scrape full article text (best-effort, 8s timeout per URL)
  Step 4:  Format article blocks (with publication dates)
  Step 5:  Extract relevant tickers + fetch OHLCV data (period=5d)
  Step 5.5: Fetch earnings calendar
  Step 6:  Fetch stock data
  Step 7:  Call 1 — Analyst (flash-lite): articles + prices → insights JSON
  Step 8.5: Build Portfolio Snapshot + Movers table (Python, no LLM)
  Step 9:  Call 2 — Editor (flash): insights + snapshot + movers → editorial digest
  Step 10: Render HTML email from markdown digest
```

---

## Digest Quality — Current State

**Grade: A-** — 2-call architecture, editorial voice, time-windowed data, HTML output.

| Issue | Status | Notes |
|-------|--------|-------|
| News capped at 8 | ✅ Fixed | Editorial prompt selects top 8 stories |
| Key Insights capped at 15 | ✅ Fixed | `_cap_key_insights()` Python-level enforcement |
| Portfolio summary | ✅ Fixed | Est. value, P&L, gain, top movers |
| Movers table | ✅ Fixed | ▲/▼ arrows, JSON fallback, sentence truncation |
| Insider sales <$1M | ✅ Fixed | Filtered at ingest + editorial prompt rule |
| Per-ticker dedup | ✅ Fixed | Editorial prompt enforces 1 bullet per ticker |
| Cross-section dedup | ✅ Fixed | Role separation: analyst extracts, editor writes |
| "Why it matters" | ✅ Fixed | Call 2 adds editorial analysis per story |
| HTML email output | ✅ Fixed | `pipeline/html_renderer.py` renders full template |
| Stale article hallucinations | ✅ Fixed | 36h time-window + temporal awareness rule |
| Non-portfolio tickers | ✅ Fixed | Portfolio ticker allowlist in editorial prompt |
| Broad-term article pollution | ✅ Fixed | Similarity penalty for index/sector/ETF matches |
| Speculative/opinion articles | ✅ Fixed | `is_speculative_article()` filter at ingest + query time |
| Circular mover drivers | ✅ Fixed | PRICE-ONLY ARTICLES + DRIVER ORDERING rules in analyst prompt |
| Price-alert opinion hooks | ✅ Fixed | `is_price_alert_article()` filter at ingest + query time |

**Target structure:**
1. Portfolio Snapshot (Python-computed)
2. Movers & Drivers table (Python-computed from Call 1 insights)
3. Key Market Insights (≤15 bullets, 1 per ticker — from Call 2)
4. Upcoming Earnings
5. News That Mattered (≤8 stories with "Why it matters" — from Call 2)

---

## Key Files

| File | Purpose | Edit for |
|------|---------|----------|
| `model/model.py` | LLM prompts — Call 1 analyst + Call 2 editorial | Changing digest format, adding prompt rules |
| `model/relevance_filter.py` | Article filtering — time window, similarity, dedup | Changing what articles reach the LLM |
| `pipeline/run_test_pipeline.py` | Orchestration — Steps 1-10 | Adding pipeline steps, changing data flow |
| `pipeline/html_renderer.py` | Markdown → HTML email | Changing email template design |
| `news/noise_filter.py` | Regex noise patterns | Adding new noise article patterns |
| `news/news_ingest_pipeline.py` | Fetch + store articles | Changing ingestion logic or cleanup |
| `core/config.py` | All settings | Adding new config fields |
| `user_portfolio/portfolio.json` | Test portfolio (25 equities) | Changing test holdings |

---

## Development Phases

| Phase | Goal | Status |
|-------|------|--------|
| 0 | Fix AI pipeline | ✅ Complete |
| 0.5 | Digest quality polish | ✅ Complete |
| 0.7 | Data freshness + reliability | 🔴 Current |
| 1 | FastAPI endpoints | 🔲 Next |
| 2 | Supabase (users table) | 🔲 Blocked |
| 3 | Landing page (no-code) | 🔲 Blocked |
| 4 | Plaid integration | 🔲 Blocked |
| 5 | Scheduler + MailerSend email | 🔲 Blocked |

---

## Session Rules

1. **Current tasks first** — complete data freshness fixes before new features
2. **One fix at a time** — change, test, verify, then move on
3. **Provide test commands** — after every change, show how to verify
4. **Ask before multi-file changes** — propose a plan if touching 3+ files
5. **Never mix embedding models** — Gemini gemini-embedding-001 only
6. **Always null-check embeddings**
7. **Constrain LLM prompts** — STRICT RULES in every prompt
8. **Python-level enforcement** — LLMs ignore numeric limits, enforce in code
9. **noise_filter.py changes require explicit patterns** — only add patterns specified in the prompt, never remove or restructure existing patterns
10. **Do NOT modify html_renderer.py** unless explicitly asked