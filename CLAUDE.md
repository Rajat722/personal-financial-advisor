# CLAUDE.md — Personal Finance Newsletter

Read this fully before making any changes.

---

## Current Priority

**Pipeline quality validation — one more clean run needed before Phase 1.**

**What was fixed in the last two sessions:**
- `news_ingest_pipeline.py` — tier-2/3 batch query bug, pagination hang, single-letter ticker contamination, expanded noise filter, granular counters
- `run_test_pipeline.py` — earnings calendar, pipeline run logs, log folder reorganization, relevance filter cap + noise second-pass
- ChromaDB cleared and re-ingested with clean noise filter (124 articles, 81 noise-filtered)

**Pipeline is "working" when:**
- [x] `news_ingest_pipeline.py` runs without errors (no None embeddings, no quota crashes, no duplicates)
- [x] `run_test_pipeline.py` runs end-to-end without errors
- [x] LLM outputs reference ONLY information in source articles (STRICT RULES in all prompts)
- [x] Filters OUT institutional holding disclosures (noise filter — 81 caught per run)
- [x] Digest capped at 40 most-relevant articles (no more 100+ item bloat)
- [ ] Validate post-fix digest quality — run pipeline with fresh 124-article store, confirm digest is clean and readable
- [ ] Investigate SIM_THRESHOLD — terminal logs show articles at 0.574 similarity passing a threshold supposedly set to 0.75. Verify `.env` value and ChromaDB distance metric (L2 vs cosine)

**Next action:** Run `python pipeline/run_test_pipeline.py`, read the saved digest in `logs/digests/`, confirm it's concise and relevant. Then begin Phase 1.

---

## What This Project Does

AI-powered finance newsletter: fetches news → filters by relevance to user's portfolio → generates personalized digest → emails it.

**Core insight:** Most financial news is noise. This surfaces only what matters to YOUR holdings.

---

## Tech Stack

| Layer | Tech | Status |
|-------|------|--------|
| AI Pipeline | Python | ✅ Working end-to-end |
| LLM | Gemini `gemini-2.0-flash` | ✅ Working |
| Embeddings | Gemini `models/gemini-embedding-001` (3072-dim) | ✅ Working |
| Vector DB | ChromaDB (local, `chroma_store/` at project root) | ✅ Working |
| News | NewsData.io | ✅ Working (~120 articles/run, 81 noise-filtered) |
| Stock Data | yfinance | ✅ Working (OHLCV + earnings calendar) |
| Email | MailerSend | ✅ Working |
| Backend API | FastAPI | 🔲 Phase 1 — next sprint |
| Frontend | React + Tailwind | 🔲 Phase 3 |

---

## Project Structure
```
├── core/
│   ├── config.py                 # All env vars + settings (pydantic-settings BaseSettings)
│   └── logging.py                # get_logger() — use this, never print()
├── model/
│   ├── embedder.py               # GeminiEmbedder — 3072-dim, google-genai SDK
│   ├── model.py                  # LLM prompts: summarize, insights, EOD digest
│   └── relevance_filter.py       # Portfolio indexing + similarity filtering + noise gate + top-40 cap
├── news/
│   ├── article_model_classes.py  # Article / DigestItem / Digest Pydantic models
│   ├── newsdata.py               # NewsData.io client (api.latest_api(), 12s timeout)
│   ├── news_ingest_pipeline.py   # Fetch → normalize → embed → store
│   ├── noise_filter.py           # Shared noise regex — imported by ingest + relevance filter
│   └── normalize.py              # Article cleaning + SHA256 ID generation
├── storage/
│   └── vector_store.py           # ChromaDB — TWO collections: portfolio, articles
├── pipeline/
│   └── run_test_pipeline.py      # Main daily pipeline entry point
├── utils/
│   ├── retry.py                  # @gemini_retry() decorator — exponential backoff
│   ├── stock_details.py          # yfinance OHLCV fetcher + earnings calendar
│   └── json_utils.py             # JSON helpers
├── user_portfolio/
│   ├── portfolio.json            # Canonical portfolio: 25 equities, sectors, indices
│   └── basic_portfolio.json      # Simple reference portfolio
├── tests/
│   ├── conftest.py               # pytest fixtures + global google.genai.Client mock
│   ├── test_article_models.py
│   └── test_relevance_filter.py
├── logs/
│   ├── pipeline_runs/            # pipeline_run_*-EST.log — full INFO run output
│   ├── insights/                 # insights_response_*-EST.json
│   ├── summaries/                # summarized_articles_*-EST.json
│   ├── digests/                  # digest_*-EST.md — final EOD digest
│   └── dev_logs/                 # dev_log_YYYY-MM-DD.md — daily session notes
├── archive/
│   └── news_ingest_pipeline_v1.py
├── chroma_store/                 # ChromaDB persistence (project root — NOT storage/)
├── main.py                       # CLI entry point for single-article testing
└── requirements.txt
```

---

## Known Issues — ALL RESOLVED

| # | File(s) | Issue | Status |
|---|---------|-------|--------|
| 1 | `news_ingest_pipeline.py`, `relevance_filter.py` | Collection mismatch: ingestion → `"articles"`, filter read → `"context"` | ✅ Fixed |
| 2 | `embedder.py` | Dimension mismatch: Gemini (768) + MiniLM fallback (384) mixed in store | ✅ Fixed: single model, 3072-dim |
| 3 | `embedder.py`, `vector_store.py` | None embeddings passed to ChromaDB | ✅ Fixed: None guard + embedder raises |
| 4 | `embedder.py`, `model.py` | No rate limiting → quota crashes | ✅ Fixed: retry delay + `@gemini_retry` |
| 5 | `relevance_filter.py` | Generic terms embed to generic vectors → false positives | ✅ Fixed: `_TICKER_DESCRIPTIONS` rich text |
| 6 | `news_ingest_pipeline.py` | No deduplication | ✅ Fixed: ID + title dedup against ChromaDB |
| 7 | `model.py` | LLM hallucinations | ✅ Fixed: STRICT RULES block in every prompt |
| SDK | `embedder.py`, `model.py` | Deprecated `google-generativeai` 0.3.2 | ✅ Fixed: migrated to `google-genai` 1.12.1 |
| Newsdata | `newsdata.py` | `api.news_api()` wrong; return inside loop → NoneType | ✅ Fixed |
| ChromaDB path | `vector_store.py` | CHROMA_DIR pointed to `storage/chroma_store/` (empty) | ✅ Fixed |
| sys.path | pipeline scripts | `ModuleNotFoundError: No module named 'core'` | ✅ Fixed |
| Batch queries | `news_ingest_pipeline.py` | Tier-2/3 returning 0 articles — free plan rejects >2 terms | ✅ Fixed: individual queries per company |
| Pagination hang | `newsdata.py` | While loop triggered second API call that hung on Amazon | ✅ Fixed: single call + 12s timeout |
| Single-letter ticker | `news_ingest_pipeline.py` | `"AT&T,T"` matched unrelated articles | ✅ Fixed: `_make_query()` omits 1-char tickers |
| Noise filter gaps | `news/noise_filter.py` | Institutional disclosures slipping through | ✅ Fixed: 5 new patterns; shared module |
| Digest bloat | `relevance_filter.py` | 100+ articles fed to LLM → unreadable digest | ✅ Fixed: top-40 cap sorted by similarity |

## Known Issues — OPEN

| # | File(s) | Issue | Status |
|---|---------|-------|--------|
| A | `relevance_filter.py`, `.env` | Articles at similarity ~0.57 passing threshold supposedly set to 0.75 — may be wrong `.env` value or L2 vs cosine mismatch | 🔲 Investigate |
| B | `news_ingest_pipeline.py` | Non-portfolio company spillover: "Realty Income" query returns IRT/FBRT/ACR; "AT&T" returns SMSI/OOMA — these mostly fail relevance filter but waste embed credits | 🔲 Low priority |

---

## Commands
```bash
# Run full pipeline (primary entry point)
python pipeline/run_test_pipeline.py

# Run news ingestion only
python news/news_ingest_pipeline.py

# Check ChromaDB state (run from project root)
python -c "import chromadb; c = chromadb.PersistentClient(path='chroma_store'); print([(col.name, col.count()) for col in c.list_collections()])"

# Clear ChromaDB (fresh start — use when switching embedding models or noise filter changes)
rm -rf chroma_store/

# Verify embedding dimensions
python -c "from model.embedder import GeminiEmbedder; print(len(GeminiEmbedder().embed_text('test')))"

# Run tests
"/c/Users/rajat/anaconda3/envs/finAdvisor/python.exe" -m pytest tests/ -v
```

---

## Environment Variables

All via `core/config.py` — never use `os.environ` directly.
```env
GEMINI_API_KEY=...
NEWSDATA_API_KEY=...
MAILERSEND_API_KEY=...         # Optional
SIM_THRESHOLD=0.75             # Cosine similarity cutoff for article relevance (verify vs actual .env)
GEMINI_RETRY_DELAY=2.0         # Seconds between Gemini embedding calls
GEMINI_RETRY_ATTEMPTS=3        # Max retry attempts
GEMINI_SUMMARY_MODEL=gemini-2.0-flash
GEMINI_EMBED_MODEL=gemini-embedding-001
```

---

## Coding Standards

**Logging:** Never `print()`. Use `from core.logging import get_logger`. File handlers use INFO level — never DEBUG on root logger (causes httpcore/httpx spam).

**Embeddings:**
- Model: `models/gemini-embedding-001` — 3072 dims, google-genai SDK only
- No MiniLM fallback — eliminated entirely
- Always null-check before storing; embedder raises ValueError on empty result

**Noise Filter:**
- Lives in `news/noise_filter.py` — shared between ingest pipeline and relevance filter
- Applied at ingest time AND at relevance-filter time (two-pass defense)
- When adding new patterns, test against known false positives (e.g. "Apple is largest in market cap" must NOT match)

**ChromaDB:**
- Only TWO collections: `portfolio`, `articles`
- `chroma_store/` lives at project root (not inside `storage/`)
- Always deduplicate by ID + title before upsert
- Metadata values must be scalar (no lists) — join lists to comma strings
- Clear and re-ingest if noise filter patterns change significantly

**Relevance Filter:**
- `MAX_RELEVANT_ARTICLES = 40` — hard cap, sorted by similarity descending
- `SIMILARITY_THRESHOLD` — verify actual `.env` value before tuning

**LLM Prompts:** Every prompt includes STRICT RULES block:
```
STRICT RULES:
- Only reference information explicitly in the provided articles
- Do not infer connections not directly stated
- Do not hallucinate price targets, ratings, or analyst opinions
- If insufficient information, say so explicitly
```

**Error handling:** Wrap all external API calls in try/except. Gemini calls use `@gemini_retry()` from `utils/retry.py`.

**File paths:** Always use `pathlib.Path`. Never hardcode absolute paths.

**Log timestamps:** EST on all log filenames (for readability). Internal datetime logic stays UTC.

---

## Development Phases

| Phase | Goal | Status |
|-------|------|--------|
| 0 | Fix AI pipeline | ✅ Complete — functional, quality validated |
| 0.5 | Digest quality tuning | 🔲 One more validation run needed |
| 1 | FastAPI endpoints (`POST /users/signup`, `GET /users/{id}/newsletter`, `POST /newsletter/send`) | 🔲 Next after 0.5 |
| 2 | Supabase (users + portfolios tables, replace portfolio.json) | 🔲 Blocked on Phase 1 |
| 3 | React landing page | 🔲 Blocked on Phase 2 |
| 4 | Scheduler + email delivery polish | 🔲 Blocked on Phase 3 |

---

## Rules

1. **Pipeline quality first** — validate digest before building Phase 1
2. **One fix at a time** — change, test, verify, then move on
3. **Ask before multi-file changes** — propose a plan if touching 3+ files
4. **Never mix embedding models** — Gemini `gemini-embedding-001` only
5. **Always null-check embeddings**
6. **Always deduplicate articles** (ID + title)
7. **Constrain LLM prompts** — anti-hallucination STRICT RULES in every prompt
8. **Never commit `.env`** — rotate keys if accidentally committed
9. **Clear ChromaDB when noise filter changes significantly** — stale noise articles contaminate digest
