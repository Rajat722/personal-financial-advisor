# Dev Log — Personal Finance Newsletter

Concise daily record of what changed, why, and what was learned.

---

## 2025-08-XX — Session 1: Pipeline Repair Sprint

**Goal:** Get the AI pipeline running end-to-end without crashes or corrupt data.

**Starting state:** Pipeline was broken in multiple compounding ways — wrong ChromaDB path, mixed embedding dimensions (Gemini 768 + MiniLM 384 in same store), deprecated SDK throwing 404s, articles never connecting to the relevance filter, and LLM hallucinating freely. No articles had ever been successfully stored under the working code.

---

### What we fixed (in order worked)

**1. ChromaDB path mismatch**
`vector_store.py` pointed to `storage/chroma_store/` (always empty). The real data was in `chroma_store/` at project root. Fixed: updated `CHROMA_DIR` to `ROOT / "chroma_store"`. Deleted both old directories for a clean slate since they contained corrupt 384-dim MiniLM embeddings incompatible with anything else.

**2. sys.path fix for direct script execution**
Running `python news/news_ingest_pipeline.py` added `news/` to sys.path, not the project root, so `from core.config import settings` failed with `ModuleNotFoundError`. Fixed: added `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` to both pipeline scripts.

**3. SDK migration: google-generativeai → google-genai**
`google-generativeai` 0.3.2 is fully deprecated — it locked to v1beta API and only resolved `models/embedding-001` (404 now). Migrated everything to `google-genai` 1.12.1 (the new official SDK). Model is now `models/gemini-embedding-001` (3072-dim). Removed `sentence-transformers`, `torch`, `transformers` from requirements — no more MiniLM fallback. Single embedding model, single dimension, no mixing.

**Key decision:** We evaluated text-embedding-004 (768-dim, better quality) vs gemini-embedding-001 (3072-dim, what the free tier actually has). Our API key only has access to gemini-embedding-001. Went with what works.

**4. Collection mismatch (Bug #1 in CLAUDE.md)**
`news_ingest_pipeline.py` stored articles in `"articles"` collection. `relevance_filter.py` read from `"context"` collection — completely disconnected. Fixed: `relevance_filter.py` now calls `get_article_collection()` which returns the `"articles"` collection.

**5. None embeddings crash (Bug #3)**
Gemini returning empty list → embedder returned None → ChromaDB silently corrupted or crashed. Fixed: embedder now raises `ValueError` on empty result; `vector_store.upsert_to_collection()` raises if any embedding is None. Fail fast, never silently corrupt the store.

**6. Rate limiting (Bug #4)**
No delays between Gemini calls → quota exhaustion mid-pipeline. Fixed: `time.sleep(settings.GEMINI_RETRY_DELAY)` between every Gemini embedding call, plus tenacity retry with exponential backoff on the embedder method.

**7. NewsData bugs**
- `api.news_api()` deprecated → changed to `api.latest_api()`
- `return articles[:max_results]` was inside the while loop's `try` block — when `len(batch) < 10` triggered `break`, function returned `None`. Fixed: moved return outside the loop.
- Query bug: `fetch_finance_news_from_newsdataio(q)` passed `q` as the `language` positional arg (so actual query was empty string). NewsData returned a misleading "API Key missing" auth error. Fixed: always pass as keyword arg `q=q`.

**8. normalize_article signature fix**
Pipeline was calling `normalize_article(article)` but the function signature is `normalize_article(raw, context_tickers, context_sectors)`. Fixed: pipeline now loads `portfolio.json`, matches article's `keywords` field against portfolio tickers, and passes both context args.

**9. ChromaDB metadata must be scalar**
`article.tickers` is a Python list. ChromaDB metadata values must be strings/ints/floats. Fixed: `"tickers": ",".join(article.tickers)`.

**10. Better portfolio embeddings (Bug #5)**
Embedding bare ticker symbols ("AAPL", "T") or generic terms ("AI") produces generic vectors that match everything or nothing. Fixed: `_TICKER_DESCRIPTIONS` dict in `relevance_filter.py` maps each ticker to a rich text description, e.g. `"NVDA Nvidia GPU graphics semiconductor AI chips data center machine learning"`. Each portfolio term gets a semantically rich embedding.

**11. Deduplication (Bug #6)**
No dedup → same article stored multiple times across runs. Fixed: pre-load all existing IDs from ChromaDB before the loop; skip any article whose SHA256 ID already exists. Also added cross-group dedup within a single fetch run (articles can appear in multiple query group results).

**12. Ticker group queries**
Initial query was only "NVDA" — returned 6 articles. Ticker symbols don't appear in article text, so NewsData found nothing for most. Fixed: 6 query groups using company names (space-separated = OR search in NewsData), covering the full portfolio breadth. Result: 75-80 articles per run.

**13. LLM anti-hallucination (Bug #7)**
All 4 Gemini generation functions (summarize, insights, EOD digest, etc.) now include a STRICT RULES block that explicitly prohibits inferring connections not in the source text, fabricating price targets, or inventing analyst ratings.

**14. Test suite update**
`conftest.py` patched the old `google.generativeai` SDK. Updated to patch `google.genai.Client` at module level. All 28 tests pass.

---

### End state

- 75-80 articles ingested per run across 6 query groups
- Single embedding model (gemini-embedding-001, 3072-dim), no mixing
- Deduplication working across runs and within a run
- `portfolio` + `articles` collections both populated correctly
- 28 tests passing
- Full end-to-end pipeline (`run_test_pipeline.py`) not yet run — that's the next validation step

---

### Next session priorities

1. Run `python pipeline/run_test_pipeline.py` end-to-end
2. Review debug logs: which articles pass the 0.75 similarity threshold, which fail
3. Tune threshold if needed — 0.75 was calibrated for 768-dim; 3072-dim cosine distances may behave differently
4. Consider source domain blocklist for article spam (e.g. sites that syndicate unrelated legal settlement news)
5. Begin Phase 1: FastAPI layer

---
