# CLAUDE.md — Personal Finance Newsletter

Read this fully before making any changes.

---

## Current Priority

**Pipeline is functional. Next: validate quality, then build Phase 1 (FastAPI).**

**Pipeline is "working" when:**
- [x] Runs without errors (no None embeddings, no quota crashes)
- [x] No duplicate articles in output
- [x] LLM outputs reference ONLY information in source articles (no hallucinations)
- [ ] Filters OUT irrelevant articles (recipes, gambling, unrelated local news)
- [ ] Filters IN relevant articles (portfolio tickers, sectors, market events)

Next action: run `python pipeline/run_test_pipeline.py` end-to-end, review which articles pass/fail 0.75 threshold, and tune if needed.

---

## What This Project Does

AI-powered finance newsletter: fetches news → filters by relevance to user's portfolio → generates personalized digest → emails it.

**Core insight:** Most financial news is noise. This surfaces only what matters to YOUR holdings.

---

## Tech Stack

| Layer | Tech | Status |
|-------|------|--------|
| AI Pipeline | Python | ✅ Fixed — functional end-to-end |
| LLM | Gemini `gemini-2.0-flash` | ✅ Working |
| Embeddings | Gemini `models/gemini-embedding-001` (3072-dim) | ✅ Fixed (migrated from deprecated SDK) |
| Vector DB | ChromaDB (local, `chroma_store/` at project root) | ✅ Fixed |
| News | NewsData.io | ✅ Working (~75-80 articles/run) |
| Stock Data | yfinance | ✅ Working |
| Email | MailerSend | ✅ Working |
| Backend API | FastAPI | 🔲 Phase 1 — next sprint |
| Frontend | React + Tailwind | 🔲 Phase 3 |

---

## Project Structure
```
├── core/
│   ├── config.py              # All env vars + settings (pydantic-settings BaseSettings)
│   └── logging.py             # get_logger() — use this, never print()
├── model/
│   ├── embedder.py            # GeminiEmbedder — 3072-dim, google-genai SDK
│   ├── model.py               # LLM prompts: summarize, insights, EOD digest
│   └── relevance_filter.py    # Portfolio indexing + similarity filtering (SIM_THRESHOLD)
├── news/
│   ├── article_model_classes.py  # Article / DigestItem / Digest Pydantic models
│   ├── newsdata.py            # NewsData.io client (api.latest_api())
│   ├── news_ingest_pipeline.py   # Fetch → normalize → embed → store
│   └── normalize.py           # Article cleaning + SHA256 ID generation
├── storage/
│   └── vector_store.py        # ChromaDB — TWO collections: portfolio, articles
├── pipeline/
│   └── run_test_pipeline.py   # Main daily pipeline entry point
├── utils/
│   ├── retry.py               # @gemini_retry() decorator — exponential backoff
│   └── stock_details.py       # yfinance OHLCV fetcher + formatters
├── user_portfolio/
│   ├── portfolio.json         # Canonical portfolio: 25 equities, sectors, indices
│   └── basic_portfolio.json   # Simple reference portfolio
├── tests/
│   ├── conftest.py            # pytest fixtures + global google.genai.Client mock
│   ├── test_article_models.py
│   └── test_relevance_filter.py
├── chroma_store/              # ChromaDB persistence (project root — NOT storage/)
├── dev_log.md                 # Daily progress log
├── main.py                    # CLI entry point for single-article testing
└── requirements.txt
```

---

## Known Issues — ALL RESOLVED

| # | File(s) | Issue | Status |
|---|---------|-------|--------|
| 1 | `news_ingest_pipeline.py`, `relevance_filter.py` | Collection mismatch: ingestion → `"articles"`, filter read → `"context"` | ✅ Fixed: filter now reads `get_article_collection()` |
| 2 | `embedder.py` | Dimension mismatch: Gemini (768) + MiniLM fallback (384) mixed in store | ✅ Fixed: single model, 3072-dim, no fallback |
| 3 | `embedder.py`, `vector_store.py` | None embeddings passed to ChromaDB | ✅ Fixed: None guard in upsert; embedder raises on empty result |
| 4 | `embedder.py`, `model.py` | No rate limiting → quota crashes | ✅ Fixed: `time.sleep(settings.GEMINI_RETRY_DELAY)` between all Gemini calls |
| 5 | `relevance_filter.py` | Generic terms ("AI", "T") embed to generic vectors → false positives | ✅ Fixed: rich ticker descriptions in `_TICKER_DESCRIPTIONS` dict |
| 6 | `news_ingest_pipeline.py` | No deduplication | ✅ Fixed: pre-load existing IDs from ChromaDB; skip duplicates |
| 7 | `model.py` | LLM hallucinations | ✅ Fixed: STRICT RULES block in every prompt |
| SDK | `embedder.py`, `model.py` | Using deprecated `google-generativeai` 0.3.2 | ✅ Fixed: migrated to `google-genai` 1.12.1 |
| Newsdata | `newsdata.py` | `api.news_api()` → wrong function; return inside loop → NoneType | ✅ Fixed: `api.latest_api()`; return moved outside loop |
| ChromaDB path | `vector_store.py` | CHROMA_DIR pointed to `storage/chroma_store/` (empty) | ✅ Fixed: points to `ROOT / "chroma_store"` |
| sys.path | pipeline scripts | `ModuleNotFoundError: No module named 'core'` when run directly | ✅ Fixed: `sys.path.insert(0, ...)` at top of both pipeline files |

---

## Commands
```bash
# Run full pipeline (primary entry point)
python pipeline/run_test_pipeline.py

# Run news ingestion only
python news/news_ingest_pipeline.py

# Check ChromaDB state (run from project root)
python -c "import chromadb; c = chromadb.PersistentClient(path='chroma_store'); print([(col.name, col.count()) for col in c.list_collections()])"

# Clear ChromaDB (fresh start — use when switching embedding models)
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
SIM_THRESHOLD=0.75             # Cosine similarity cutoff for article relevance
GEMINI_RETRY_DELAY=2.0         # Seconds between Gemini embedding calls
GEMINI_RETRY_ATTEMPTS=3        # Max retry attempts
GEMINI_SUMMARY_MODEL=gemini-2.0-flash
GEMINI_EMBED_MODEL=gemini-embedding-001
```

---

## Coding Standards

**Logging:** Never `print()`. Use `from core.logging import get_logger`.

**Embeddings:**
- Model: `models/gemini-embedding-001` — 3072 dims, google-genai SDK only
- No MiniLM fallback — eliminated entirely
- Always null-check before storing; embedder raises ValueError on empty result
- Dimension validated inside `GeminiEmbedder.embed_text()` — raises on mismatch

**ChromaDB:**
- Only TWO collections: `portfolio`, `articles`
- `chroma_store/` lives at project root (not inside `storage/`)
- Always deduplicate by ID before upsert
- Metadata values must be scalar (no lists) — join lists to comma strings

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

---

## Development Phases

| Phase | Goal | Status |
|-------|------|--------|
| 0 | Fix AI pipeline | ✅ Complete |
| 1 | FastAPI endpoints (`POST /users/signup`, `GET /users/{id}/newsletter`, `POST /newsletter/send`) | 🔲 Next |
| 2 | Supabase (users + portfolios tables, replace portfolio.json) | 🔲 Blocked on Phase 1 |
| 3 | React landing page | 🔲 Blocked on Phase 2 |
| 4 | Scheduler + email delivery polish | 🔲 Blocked on Phase 3 |

---

## Rules

1. **Pipeline quality first** — validate filtering before building Phase 1
2. **One fix at a time** — change, test, verify, then move on
3. **Ask before multi-file changes** — propose a plan if touching 3+ files
4. **Never mix embedding models** — Gemini `gemini-embedding-001` only
5. **Always null-check embeddings**
6. **Always deduplicate articles**
7. **Constrain LLM prompts** — anti-hallucination STRICT RULES in every prompt
8. **Never commit `.env`** — rotate keys if accidentally committed
