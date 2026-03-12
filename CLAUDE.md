# CLAUDE.md — Personal Finance Newsletter

Read this fully before making any changes.

---

## Current Priority

**Digest quality polish before first users.**

The pipeline runs end-to-end. Now make the output match the sample HTML design (`sample_templates/sample-002.html`).

**Remaining tasks:**
- [ ] Cap "News That Mattered" at 10 items (update prompt in `model/model.py`)
- [ ] Add title-based deduplication before LLM (in `relevance_filter.py`)
- [ ] Add portfolio value summary at top of digest
- [ ] Add Movers & Drivers section
- [ ] Filter insider transactions < $500k (optional)

**Validation:** `python pipeline/run_test_pipeline.py` → read `logs/digests/` → compare to sample HTML.

---

## What This Project Does

AI-powered finance newsletter: fetches news → filters by relevance to user's portfolio → generates personalized digest → emails it.

**Target user:** Beginner-to-intermediate retail investor (25-35, Gen Z/millennial) who holds 5-20 stocks and wants curated, portfolio-specific news without the noise.

**Core insight:** Most financial news is irrelevant. This surfaces only what matters to YOUR holdings.

---

## Tech Stack

| Layer | Tech | Status |
|-------|------|--------|
| AI Pipeline | Python | ✅ Working |
| LLM | Gemini `gemini-2.5-flash-lite` | ✅ Working |
| Embeddings | Gemini `gemini-embedding-001` (3072-dim) | ✅ Working |
| Vector DB | ChromaDB (local, `chroma_store/`) | ✅ Working |
| News | NewsData.io (~120 articles/run) | ✅ Working |
| Stock Data | yfinance (OHLCV + earnings) | ✅ Working |
| Email | MailerSend | 🔲 Not started |
| Backend API | FastAPI | 🔲 Phase 1 |
| Frontend | No-code (Framer/Carrd) | 🔲 Phase 3 |

---

## Project Structure

```
├── model/
│   ├── model.py              # LLM prompts — EDIT HERE to change digest format
│   ├── relevance_filter.py   # Article filtering — ADD deduplication here
│   └── embedder.py           # Gemini embeddings
├── pipeline/
│   └── run_test_pipeline.py  # Main orchestration — ADD new sections here
├── news/
│   ├── news_ingest_pipeline.py
│   └── noise_filter.py       # Noise patterns
├── storage/
│   └── vector_store.py       # ChromaDB wrapper
├── user_portfolio/
│   └── portfolio.json        # Test portfolio (25 equities)
├── sample_templates/
│   └── sample-002.html       # TARGET digest format
├── logs/
│   ├── digests/              # Final EOD digests (.md)
│   ├── pipeline_runs/        # Full run logs
│   └── insights/             # LLM responses
└── chroma_store/             # ChromaDB persistence
```

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

## Environment Variables

All via `core/config.py` — never use `os.environ` directly.

```env
GEMINI_API_KEY=...
NEWSDATA_API_KEY=...
SIM_THRESHOLD=0.75           # Cosine similarity cutoff
GEMINI_SUMMARY_MODEL=gemini-2.5-flash-lite
```

---

## Coding Standards

**Logging:** Never `print()`. Use `from core.logging import get_logger`.

**Embeddings:** Gemini `gemini-embedding-001` only, 3072-dim. Always null-check.

**ChromaDB:** Two collections only: `portfolio`, `articles`. Cosine metric.

**LLM Prompts:** Every prompt includes STRICT RULES anti-hallucination block:
```
STRICT RULES:
- Only reference information explicitly in the provided articles
- Do not infer connections not directly stated
- Do not hallucinate price targets, ratings, or events
```

**Error handling:** Wrap external API calls in try/except. Use `@gemini_retry()`.

---

## Digest Quality Issues to Fix

| Issue | Fix Location | Priority |
|-------|--------------|----------|
| 35+ news items (too long) | `model/model.py` EOD prompt | High |
| Duplicate headlines | `model/relevance_filter.py` | High |
| No portfolio summary | `pipeline/run_test_pipeline.py` | Medium |
| No movers table | `pipeline/run_test_pipeline.py` | Medium |
| Minor insider sales | `news/noise_filter.py` | Low |

**Target structure (from sample-002.html):**
1. Portfolio Summary (value + top movers)
2. Top 5-10 Headlines (TL;DR + Why it matters + Confidence)
3. Movers & Drivers table
4. Sector Snapshot
5. Upcoming Events
6. Education Corner (conditional)

---

## Development Phases

| Phase | Goal | Status |
|-------|------|--------|
| 0 | Fix AI pipeline | ✅ Complete |
| 0.5 | Digest quality polish | 🔴 Current |
| 1 | FastAPI endpoints | 🔲 Next |
| 2 | Supabase (users table) | 🔲 Blocked |
| 3 | Landing page (no-code) | 🔲 Blocked |
| 4 | Plaid integration | 🔲 Blocked |
| 5 | Scheduler + email polish | 🔲 Blocked |

---

## Session Rules

1. **Digest quality first** — match output to sample HTML before new features
2. **One fix at a time** — change, test, verify, then move on
3. **Provide test commands** — after every change, show how to verify
4. **Ask before multi-file changes** — propose a plan if touching 3+ files
5. **Never mix embedding models** — Gemini only
6. **Always null-check embeddings**
7. **Constrain LLM prompts** — STRICT RULES in every prompt