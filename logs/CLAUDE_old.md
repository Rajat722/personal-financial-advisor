# CLAUDE.md — Personal Finance Newsletter

Read this fully before making any changes.

---

## Current Priority

**Phase 0.5 complete — digest quality fixes applied. Clear ChromaDB, re-ingest, and run one validation pipeline before starting Phase 1.**

**What was fixed in the last session (2026-03-07):**
- `vector_store.py` — portfolio collection now uses cosine metric (was L2); `1-distance` is now correct cosine similarity
- `.env` — `SIM_THRESHOLD` corrected to `0.75` (was `0.57`)
- `model.py` — EOD digest prompt now deduplicates facts across articles
- `news/noise_filter.py` — converted VERBOSE regex to list of patterns; fixes Bouchey-style slipthrough
- `pipeline/run_test_pipeline.py` — suppressed httpcore/httpx/chromadb DEBUG spam in log files

**Pipeline is "working" when:**
- [x] `news_ingest_pipeline.py` runs without errors
- [x] `run_test_pipeline.py` runs end-to-end without errors
- [x] LLM outputs reference ONLY information in source articles (STRICT RULES in all prompts)
- [x] Filters OUT institutional holding disclosures (noise filter)
- [x] Digest capped at 40 most-relevant articles
- [x] SIM_THRESHOLD correctly uses cosine similarity at 0.75
- [x] Digest deduplicates repeated facts
- [ ] Run validation pipeline after ChromaDB clear + re-ingest — confirm digest is clean

**Next action:** `rm -rf chroma_store/` → `python news/news_ingest_pipeline.py` → `python pipeline/run_test_pipeline.py` → read digest. Then begin Phase 1.

---

## What This Project Does

AI-powered finance newsletter: fetches news → filters by relevance to user's portfolio → generates personalized digest → emails it.

**Core insight:** Most financial news is noise. This surfaces only what matters to YOUR holdings.

---

## Tech Stack

| Layer | Tech | Status |
|-------|------|--------|
| AI Pipeline | Python | ✅ Working end-to-end | But quality of response still not good. Check latest logs from logs folder (look at max 1 day prior)
| LLM | Gemini `gemini-2.5-flash-lite` | ✅ Working |
| Embeddings | Gemini `models/gemini-embedding-001` (3072-dim) | ✅ Working |
| Vector DB | ChromaDB (local, `chroma_store/` at project root) | ✅ Working |
| News | NewsData.io | ✅ Working (~120 articles/run, 81 noise-filtered) |
| Stock Data | yfinance | ✅ Working (OHLCV + earnings calendar) |
| Email | MailerSend | Have not started working on it|
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

## Known Issues — OPEN

| # | File(s) | Issue | Status |
|---|---------|-------|--------|
| E | `news_ingest_pipeline.py` | Non-portfolio company spillover: "Realty Income" query returns IRT/FBRT/ACR; "AT&T" returns SMSI/OOMA — mostly fail relevance filter but waste embed credits | 🔲 Low priority |

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
- `portfolio` collection uses **cosine** metric (`hnsw:space=cosine`) — distances are cosine distances, `1-distance = cosine_similarity`
- Always deduplicate by ID + title before upsert
- Metadata values must be scalar (no lists) — join lists to comma strings
- Clear and re-ingest if noise filter patterns change significantly or if metric changes

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
