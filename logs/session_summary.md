# Session Summary — Personal Finance Newsletter

Last Updated: March 8, 2026

---

## Project Overview

**Product:** A personalized finance newsletter that delivers AI-generated market summaries tailored to each user's specific stock portfolio.

**Core Value Proposition:** "Your portfolio. Explained."

**Target User:** 25-35 year old beginner-to-intermediate investor who holds 5-20 individual stocks + ETFs on Robinhood/Fidelity/Schwab, wants to understand what's happening to their portfolio without reading multiple news sources.

**Business Model:**
- **Free tier:** 5 tickers, weekly delivery
- **Paid tier ($5/month):** Unlimited tickers, daily option, Plaid sync

**Kill Criteria:** 2 months with < 20 users = kill or major pivot

---

## Current State: Phase 0.5 — Digest Quality Polish

The AI pipeline runs end-to-end. Focus is now on output quality before first users.

### What's Working ✅

| Component | Status | Notes |
|-----------|--------|-------|
| News ingestion | ✅ | ~120 articles/run via NewsData.io |
| Embedding | ✅ | Gemini gemini-embedding-001, 3072-dim |
| Vector store | ✅ | ChromaDB with cosine metric, `chroma_store/` |
| Relevance filter | ✅ | 0.75 threshold, top-40 cap, title dedup |
| Noise filter | ✅ | 17 patterns: institutional disclosures + SEO roundups + insider sales <$1M |
| LLM generation | ✅ | Gemini 2.5-flash-lite |
| Portfolio snapshot | ✅ | Est. value, day P&L, total gain, top movers |
| Movers & Drivers table | ✅ | 20 tickers with ▲/▼ arrows and driver text |
| Key Market Insights | ✅ | Capped at 15 bullets via Python post-processing |
| News That Mattered | ✅ | Capped at 10 items via prompt |
| Earnings calendar | ✅ | yfinance 3-day lookback + 14-day lookahead |
| Full article scraping | ✅ | Best-effort, 8s timeout, 3000 char cap |
| HTML email template | ✅ | Two versions: full editorial + simple |

### Digest Quality — Current Grade: B+

**Sample output (March 8, 2026 18:19 EST run):**
```
## Portfolio Snapshot
Est. Value: $142,224 | Today's P&L: +$1,114 | Total Gain: +$67,845 (+91.2%)
Top Gainer: COST (+3.1%) | Top Loser: NVDA (-1.5%)

## Movers & Drivers
| COST | ▲ +3.1% | Costco shares rose 1.6% following better-than-expected earnings, EPS $4.58. |
| NET  | ▲ +2.7% | Cloudflare's revenue climbed by 30% in 2025. |
| RKLB | ▲ +2.4% | Rocket Lab reported Q4 revenue of $180M, 36% growth YoY. |
... (20 tickers total)

## Key Market Insights (15 bullets — cap working)
## News That Mattered Today (10 items — cap working)
## Upcoming Earnings (none in window)
```

---

## March 8, 2026 Changes (Latest Sprint)

### 1. Prompt-Level Quality Rules — `model/model.py`

Updated `build_eod_summary_prompt()` with five new rules:

- **KEY MARKET INSIGHTS LIMIT:** Hard cap at 15 bullets, one per ticker. Ranking: earnings beats > analyst upgrades > product launches > general commentary.
- **SECTION ROLES:** Explicit deduplication guidance — Movers table owns price + driver; Key Insights covers additional facts; News covers articles not yet mentioned.
- **INSIDER TRANSACTIONS:** Do not mention insider sales/purchases under $1M. Examples given for clarity.
- **NEWS THAT MATTERED cap:** Hard cap at 10 items, skip articles already covered in Key Insights.
- **DEDUPLICATION:** Do not restate the same fact in different words.

### 2. Movers Table Fix — `pipeline/run_test_pipeline.py`

**Bug:** `arrow = "- "` combined with negative `{pct:.1f}%` rendered as `- -1.5%`.

**Fix:** Changed to `arrow = "▲" if pct >= 0 else "▼"` with separate `sign = "+"` prefix. Now renders `▲ +3.1%` / `▼ -1.5%`.

### 3. Scraping Deduplication — `pipeline/run_test_pipeline.py`

**Bug:** KO article body contained repeated sentences from pagination artifacts.

**Fix:** In `_enrich_articles_with_full_text()`, split scraped body on newlines and remove consecutive duplicate lines before appending.

### 4. Key Market Insights Hard Cap — `pipeline/run_test_pipeline.py`

**Problem:** LLM prompt said "maximum 15 bullets" but LLM wrote 19.

**Fix:** New `_cap_key_insights(eod_text, limit=15)` function. Regex-extracts the Key Market Insights section, slices to first 15 bullets, splices back. Logs how many were dropped.

### 5. Sentence-Boundary Truncation — `pipeline/run_test_pipeline.py`

**Bug:** Movers table driver text sliced at 120 chars mid-sentence.

**Fix:** New `_truncate_at_sentence(text, limit=200)` helper. Finds last `. ` within limit, cuts there. Falls back to hard truncation with `…` only if no sentence boundary exists.

### 6. Noise Filter: Insider Sales <$1M — `news/noise_filter.py`

Two new patterns added:

**Pattern 1 — "Insider Selling:" prefix with small dollar amount:**
Matches `"Insider Selling: DraftKings CAO Sells $70,806.48 in Stock"`. Dollar pattern `\$\d{1,3},\d{3}` covers $1,000–$999,999. Negative lookahead prevents matching mid-number.

**Pattern 2 — Role-based insider sale without "insider" keyword:**
Matches `"Verizon (NYSE:VZ) SVP Sells $428,450.00 in Stock"`. Anchored to executive role titles (CEO, CFO, COO, etc.). Does NOT match `buys` — insider buys kept regardless of size.

### 7. HTML Email Templates — `sample_templates/`

Created two versions:
- `digest_2026-03-08.html` — Full editorial version with "Why it matters:" blurbs
- `digest_2026-03-08-simple.html` — Raw pipeline output, no editorial layer

Design mirrors Market Briefs: blue `#2952cc` dividers, section icons, green/red color-coded changes.

---

## Open Issues — Next Session Priority

### P1 — Add insider transactions rule to `build_insight_prompt()` (model/model.py)
The `INSIDER TRANSACTIONS` rule only exists in `build_eod_summary_prompt()`. Movers drivers come from `get_insights_from_news_and_prices()` which uses `build_insight_prompt()`. That function has no materiality filter, so sub-$1M insider sales still appear as Movers drivers (META COO $400K). **Fix:** Add same rule to `build_insight_prompt()`.

### P2 — Per-ticker deduplication in `_cap_key_insights()` (run_test_pipeline.py)
Current cap slices to 15 bullets but doesn't deduplicate by ticker. COST gets 2 bullets, RKLB gets 3 — consuming 5 of 15 slots on 2 tickers. **Fix:** Before slicing to 15, deduplicate to first bullet per ticker.

### P3 — "Following Insider Selling" article titles (news/noise_filter.py)
`"Meta Platforms (NASDAQ:META) Stock Price Down 1.1% Following Insider Selling"` — no dollar amount in title, so noise filter doesn't catch it. **Fix:** Pattern for "Following Insider Selling" suffix when title contains no "million"/"billion".

### P4 — SHOP Movers driver temporal mismatch (run_test_pipeline.py)
SHOP was ▲ +0.1% today, but driver says "Shopify shares dropped 3.4% during mid-day trading on Friday." The insight came from a stale article. Low priority — partly a data quality issue.

### P5 — Phase 1: FastAPI layer
Deferred. Start once digest quality is stable over 2-3 consecutive runs. Endpoints: `POST /users/signup`, `GET /users/{id}/newsletter`, `POST /newsletter/send`.

---

## Tech Stack

| Layer | Technology | Status |
|-------|------------|--------|
| AI Pipeline | Python | ✅ Working |
| LLM | Gemini `gemini-2.5-flash-lite` | ✅ Working |
| Embeddings | Gemini `gemini-embedding-001` (3072-dim) | ✅ Working |
| Vector DB | ChromaDB (local, `chroma_store/`) | ✅ Working |
| News | NewsData.io (~120 articles/run) | ✅ Working |
| Stock Data | yfinance (OHLCV + earnings) | ✅ Working |
| Email | MailerSend | 🔲 Not started |
| Backend API | FastAPI | 🔲 Phase 1 |
| Frontend | No-code (Framer/Carrd) | 🔲 Phase 3 |
| Database | Supabase (Postgres + pgvector) | 🔲 Phase 2 |

---

## Project Structure

```
├── model/
│   ├── model.py              # LLM prompts — EOD summary, insights, article summaries
│   ├── relevance_filter.py   # Portfolio indexing + similarity filter + title dedup
│   └── embedder.py           # Gemini embeddings (3072-dim)
├── pipeline/
│   └── run_test_pipeline.py  # Main orchestration — portfolio snapshot, movers table, caps
├── news/
│   ├── news_ingest_pipeline.py   # Fetch → embed → store
│   ├── noise_filter.py           # 17 patterns: institutional + roundups + insider <$1M
│   ├── newsdata.py               # NewsData.io client
│   └── normalize.py              # Article normalization
├── storage/
│   └── vector_store.py       # ChromaDB wrapper — TWO collections: portfolio, articles
├── user_portfolio/
│   └── portfolio.json        # Test portfolio (25 equities)
├── sample_templates/
│   ├── sample-002.html       # Target digest format (reference)
│   ├── digest_2026-03-08.html      # Full editorial HTML template
│   └── digest_2026-03-08-simple.html  # Simple HTML template
├── logs/
│   ├── digests/              # Final EOD digests (.md)
│   ├── pipeline_runs/        # Full run logs
│   ├── insights/             # LLM insight responses
│   ├── summaries/            # LLM article summaries
│   └── dev_logs/             # Development session logs
├── core/
│   ├── config.py             # pydantic-settings — all env vars
│   └── logging.py            # get_logger()
├── utils/
│   ├── retry.py              # @gemini_retry decorator
│   └── stock_details.py      # yfinance OHLCV + earnings calendar
├── chroma_store/             # ChromaDB persistence (cosine metric)
└── CLAUDE.md                 # AI assistant context file
```

---

## Portfolio (portfolio.json)

25 equities with allocation, shares, avg_cost_basis, and news_tier (1/2/3):

**Tier 1 (high news volume):** AAPL, MSFT, NVDA, AMZN, GOOG, TSLA, META
**Tier 2 (moderate):** BRK-A, JPM, COST, CRWD, SHOP, DKNG, NET, RKLB, CELH, AXON
**Tier 3 (low):** JNJ, PG, KO, VZ, O, T
**Indices:** SPY, QQQ

---

## Commands

```bash
# Run full pipeline (main entry point)
python pipeline/run_test_pipeline.py

# Run news ingestion only
python news/news_ingest_pipeline.py

# Clear ChromaDB (when noise filter changes)
rm -rf chroma_store/

# Check ChromaDB state
python -c "import chromadb; c = chromadb.PersistentClient(path='chroma_store'); print([(col.name, col.count()) for col in c.list_collections()])"

# Run tests
python -m pytest tests/ -v
```

---

## Key Configuration

```env
GEMINI_API_KEY=...
NEWSDATA_API_KEY=...
SIM_THRESHOLD=0.75           # Cosine similarity cutoff
MAX_RELEVANT_ARTICLES=40     # Cap per run
GEMINI_SUMMARY_MODEL=gemini-2.5-flash-lite
```

---

## Development Phases

| Phase | Goal | Status |
|-------|------|--------|
| 0 | Fix AI pipeline | ✅ Complete |
| 0.5 | Digest quality polish | 🔴 Current (P1-P3 remaining) |
| 1 | FastAPI endpoints | 🔲 Next |
| 2 | Supabase (users + portfolios) | 🔲 Blocked |
| 3 | Landing page (no-code) | 🔲 Blocked |
| 4 | Plaid integration | 🔲 Blocked |
| 5 | Scheduler + email delivery | 🔲 Blocked |

---

## 8-Week Execution Plan

| Week | Goal | Status |
|------|------|--------|
| 1 | Fix pipeline bugs | ✅ Done |
| 2 | Digest polish + manual sends to 5 friends | 🔴 Current |
| 3 | Landing page (Framer/Carrd + Tally form) | 🔲 |
| 4 | Plaid integration + instant preview | 🔲 |
| 5-6 | Automation + polish (Supabase Edge Functions cron) | 🔲 |
| 7-8 | Growth + validate (Twitter/Reddit launch, metrics) | 🔲 |

---

## Claude Code Prompt for Next Session

```markdown
Read CLAUDE.md. Digest structure is now good. Three polish issues remain:

1. **P1:** Add INSIDER TRANSACTIONS rule to `build_insight_prompt()` in model/model.py
   - Same rule as in EOD prompt: exclude insider sales/purchases under $1M
   - This prevents sub-$1M insider sales appearing as Movers drivers

2. **P2:** Per-ticker deduplication in `_cap_key_insights()` in run_test_pipeline.py
   - Before slicing to 15, deduplicate to first bullet per ticker
   - Keep LLM's ordering, just enforce one-per-ticker

3. **P3:** Add noise filter pattern for "Following Insider Selling" in news/noise_filter.py
   - Catch titles like "META Stock Price Down 1.1% Following Insider Selling"
   - Match when title has "Following Insider Selling" AND no "million"/"billion"

Files to modify:
- model/model.py — build_insight_prompt()
- pipeline/run_test_pipeline.py — _cap_key_insights()
- news/noise_filter.py — add pattern

Validation: python pipeline/run_test_pipeline.py
Check logs/digests/ — verify: no sub-$1M insider sales in Movers drivers, one bullet per ticker in Key Insights.
```

---

## Key Decisions Log

- [DECISION] Single embedding model: gemini-embedding-001 (3072-dim), no fallback
- [DECISION] ChromaDB stays local for now; migrate to Supabase pgvector as Phase 2
- [DECISION] No Plaid for MVP v1; add in Phase 4
- [DECISION] No-code frontend (Framer + Tally), not React
- [DECISION] Weekly newsletter default, skip if no relevant news
- [DECISION] Free tier: 5 tickers; paid: $5/month unlimited + Plaid
- [DECISION] SIM_THRESHOLD = 0.75 (cosine), MAX_RELEVANT_ARTICLES = 40
- [DECISION] Insider transaction threshold: $1M (was $500K, raised for better signal)
- [DECISION] Qlib library evaluated and REJECTED — solves different problem (predictive trading vs explanatory newsletter)

---

## Files to Never Modify Without Discussion

- `core/config.py` — central configuration
- `storage/vector_store.py` — schema changes require full re-indexing
- `user_portfolio/portfolio.json` — changes invalidate stored embeddings