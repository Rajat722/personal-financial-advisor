# Article Quality: Broad-Match Penalty + Speculative Filter + Institutional Disclosure Fix

Read `CLAUDE.md` first, then read this entire prompt before making any changes.

---

## Context

The pipeline produces a 40-article window for the LLM. Analysis of the March 11 digest shows roughly 12-15 of those 40 articles are useful; the rest are speculative opinion pieces, institutional fund disclosures, or generic market commentary that matched broad portfolio terms ("S&P 500", "large-cap tech", "Invesco QQQ Trust") rather than specific tickers.

Three fixes, in priority order. All three are independent — each one improves quality on its own.

---

## Fix 1: Broad-Term Similarity Penalty (highest impact)

**File:** `model/relevance_filter.py`

**Problem:** Articles matching broad portfolio terms ("S&P 500", "Nasdaq", "large-cap tech", "cloud computing", "ai", "semiconductors", "Pharmaceuticals", "Invesco QQQ Trust", "SPDR S&P 500 ETF Trust") score 0.75-0.78 similarity and fill 12 of 40 article slots with generic market commentary. An article titled "Billionaires Are Loading Up on Index Funds" at 0.762 matching "S&P 500" beats a DKNG earnings article at 0.758 matching "DraftKings".

**Fix:** After calculating `best_similarity`, apply a penalty when the `best_match` is a broad term rather than a specific ticker or company name. This makes broad-match articles need a higher raw similarity score to compete for the 40 slots.

The `best_match` field contains the raw `document` string stored in the portfolio ChromaDB collection. For tickers this is the ticker symbol (e.g., `"AAPL"`, `"COST"`). For company names it's the company string (e.g., `"Apple"`, `"Costco"`). For sectors it's the raw sector string (e.g., `"cloud computing"`, `"large-cap tech"`). For indices it's the raw index string (e.g., `"S&P 500"`, `"Nasdaq"`).

**Step 1a:** Define the set of broad terms that should be penalized. Add this constant near the top of the file, after `MAX_RELEVANT_ARTICLES`:

```python
# Broad portfolio terms that match too many articles. Articles whose best match
# is one of these get a similarity penalty so ticker-specific articles are preferred.
# Includes: all sector descriptions, all index descriptions, and ETF company names
# (QQQ and SPY match everything tech/market related).
_BROAD_MATCH_TERMS: set[str] = {
    # Sectors (from portfolio.json → _SECTOR_DESCRIPTIONS keys)
    "cloud computing", "ai", "semiconductors", "large-cap tech", "pharmaceuticals",
    # Indices (from portfolio.json → _INDEX_DESCRIPTIONS keys)
    "s&p 500", "nasdaq", "russell 2000",
    # ETF company names (stored as documents in portfolio collection)
    "invesco qqq trust", "spdr s&p 500 etf trust",
}

# Penalty applied to similarity score for broad-term matches.
# A broad-match article needs raw similarity of ~0.79+ to compete with
# a ticker-specific article at 0.75. Tuned to let major market events
# through (crash articles score 0.85+) while filtering generic commentary.
BROAD_MATCH_PENALTY: float = 0.04
```

**Step 1b:** Apply the penalty inside the scoring loop. In the `find_relevant_articles_from_context()` function, right after `best_match` is computed (after line 186) and BEFORE the threshold check (line 194), add:

```python
            # Penalize broad-term matches so ticker-specific articles are preferred
            is_broad = best_match.lower() in _BROAD_MATCH_TERMS
            effective_similarity = best_similarity - BROAD_MATCH_PENALTY if is_broad else best_similarity
```

Then change the threshold check and the appended data to use `effective_similarity`:

```python
            log.info(
                f"[{'PASS' if effective_similarity >= SIMILARITY_THRESHOLD else 'FAIL'}] "
                f"similarity={best_similarity:.3f}{' (broad:-' + str(BROAD_MATCH_PENALTY) + ')' if is_broad else ''} "
                f"match='{best_match}' | {title[:70]}"
            )

            if effective_similarity >= SIMILARITY_THRESHOLD:
                relevant_articles.append({
                    "doc_id": doc_id,
                    "text": text,
                    "metadata": metadata,
                    "scores": distances,
                    "best_match": best_match,
                    "best_similarity": effective_similarity,
                })
```

This way the log shows both the raw score AND the penalty, so you can verify it's working. Articles are sorted and capped by `effective_similarity`, meaning broad-match articles naturally fall to the bottom of the 40-slot window.

**Do NOT change anything else in this function** — the time-window filter, deduplication, noise check, and capping logic all stay the same.

---

## Fix 2: Speculative/Opinion Article Patterns (medium impact)

**File:** `news/noise_filter.py`

**Problem:** SEO articles with speculative headlines ("Can Nvidia Stock Reach $10 Trillion?", "Where Will Realty Income Be in 10 Years?", "If You Invested $1000 in Apple 20 Years Ago") contain historical stats and opinion but zero fresh news. They match portfolio tickers perfectly (high similarity scores) and waste LLM context.

**Fix:** Add a new `_SPECULATIVE_PATTERNS` list and a new `is_speculative_article()` function, following the same pattern as the existing `_ROUNDUP_PATTERNS` / `is_generic_roundup()`.

Add this after the existing `_ROUNDUP_PATTERNS` list and `is_generic_roundup()` function (after line 173):

```python
# ---------------------------------------------------------------------------
# Speculative / opinion / historical return article filter
# ---------------------------------------------------------------------------
# These are SEO articles built around a speculative question or a historical
# return calculation. They contain no fresh news — just projections, "what-if"
# scenarios, or backward-looking performance data. They match portfolio tickers
# with high similarity but generate zero actionable insights.

_SPECULATIVE_PATTERNS = [
    # "Can Nvidia Stock Reach a $10 Trillion Market Cap by 2030?"
    # "Can Tesla Reach $500 by Year-End?"
    re.compile(r"\bcan\s+.{1,40}\breach\b", re.IGNORECASE),

    # "Where Will Realty Income Be in 10 Years?"
    # "Where Will Apple Stock Be in 5 Years?"
    re.compile(r"\bwhere\s+will\s+.{1,40}\bbe\s+in\s+\d+\s+years?\b", re.IGNORECASE),

    # "Is Tesla Stock Going to $1,000?"
    # "Is NVDA Going to $200?"
    re.compile(r"\bis\s+.{1,30}\bgoing\s+to\s+\$", re.IGNORECASE),

    # "If You Invested $1000 In Apple 20 Years Ago"
    # "If You Had Invested $500 in Tesla Stock 5 Years Ago"
    re.compile(r"\bif\s+you\s+(?:had\s+)?invested\b", re.IGNORECASE),

    # "Here's How Much You Would Have Made Owning Microsoft Stock"
    # "How Much $1000 Invested In Apple Would Be Worth Today"
    re.compile(r"\bhow\s+much\s+.{0,30}\b(?:invested|made|worth)\b", re.IGNORECASE),

    # "Here's How Much $1000 Invested In Apple 20 Years Ago Would Be Worth Today"
    re.compile(r"\$\d+\s+invested\s+in\b", re.IGNORECASE),

    # "Forget QQQ: 3 Sector ETFs Quietly Outperforming Tech"
    # "Forget Tesla: Here's a Better EV Stock"
    re.compile(r"^forget\s+\w+\s*:", re.IGNORECASE),
]


def is_speculative_article(title: str) -> bool:
    """Return True if the article is a speculative opinion/projection piece with no fresh news.

    False positive guard: checked against known good articles —
    'Apple Just Unveiled the iPhone 17e. Should You Buy, Sell, or Hold AAPL Stock Now?' does NOT match
    because it lacks the speculative question patterns above.
    'Nvidia Stock Reaches All-Time High' does NOT match 'can .* reach' because it lacks 'can'.
    'Is Amazon Stock a Long-Term Buy?' does NOT match 'is .* going to $' because it lacks 'going to $'.
    """
    return any(p.search(title) for p in _SPECULATIVE_PATTERNS)
```

**Then wire it into the ingestion pipeline.** In `news/news_ingest_pipeline.py`, the speculative filter should be called right after the existing `is_generic_roundup()` check. Find the block (around lines 201-206):

```python
        # Roundup filter: generic SEO stock-list articles ("Best Tech Stocks To Watch Today")
        if _is_generic_roundup(article.title):
            log.debug(f"Filtering roundup: {article.title}")
            roundup_count += 1
            continue
```

Add a new block immediately after it:

```python
        # Speculative filter: opinion/projection/historical return articles
        if _is_speculative_article(article.title):
            log.debug(f"Filtering speculative: {article.title}")
            speculative_count += 1
            continue
```

Add the import at the top of `news_ingest_pipeline.py` — update the existing import line:
```python
from news.noise_filter import is_noise_article as _is_noise_article, is_generic_roundup as _is_generic_roundup, is_speculative_article as _is_speculative_article
```

Add `speculative_count = 0` near the other counter initializations (around line 163).

Add the speculative count to the final log summary (around line 245):
```python
    log.info(
        f"Ingestion complete: {stored_count} stored | "
        f"{noise_count} noise-filtered | "
        f"{roundup_count} roundup-filtered | "
        f"{speculative_count} speculative-filtered | "
        f"{id_dup_count} id-dups | "
        f"{title_dup_count} title-dups | "
        f"{no_summary_count} no-summary | "
        f"{norm_fail_count} norm-failed"
    )
```

**Also wire it into the query-time noise check** in `model/relevance_filter.py`. Find the noise check block (around lines 169-174):

```python
        if is_noise_article(title):
            log.debug(f"[NOISE] {title[:70]}")
            noise_skipped += 1
            continue
```

Add an import at the top of `relevance_filter.py` — update the existing import:
```python
from news.noise_filter import is_noise_article, is_speculative_article
```

Add a speculative check right after the noise check:
```python
        if is_speculative_article(title):
            log.debug(f"[SPECULATIVE] {title[:70]}")
            noise_skipped += 1
            continue
```

This uses the same `noise_skipped` counter — no need for a separate counter at query time.

---

## Fix 3: Expand Institutional Disclosure Entity Indicators (low-medium impact)

**File:** `news/noise_filter.py`

**Problem:** Fund-anchored noise patterns on lines 86, 94, and 102 use entity indicators `LLC|Ltd\.?|L\.P\.|LP|management|capital|advisors?|wealth|asset|partners?|associates?`. International fund names use suffixes not in this list: "SPX Gestao de Recursos **Ltda**", "Gordian Capital Singapore **Pte** Ltd", "Headwater Capital **Co** Ltd". These pass the noise filter and generate useless insights like "Kepler Cheuvreux bought 83,324 shares of JNJ."

**Fix:** Expand the entity indicator list in all three fund-anchored patterns (lines 86, 94, 102). Replace the entity keyword group in each of these three patterns:

**Current** (appears identically in all 3 patterns):
```
\b(?:LLC|Ltd\.?|L\.P\.|LP|management|capital|advisors?|wealth|asset|partners?|associates?)\b
```

**New** (add to all 3 patterns):
```
\b(?:LLC|Ltd\.?|Ltda\.?|L\.P\.|LP|Co\.?|Corp\.?|Inc\.?|Pte\.?|GmbH|SA|AG|NV|BV|Pty\.?|management|capital|advisors?|wealth|asset|partners?|associates?|group|fund|trust|holdings?)\b
```

The additions are: `Ltda\.?` (Portuguese/Spanish), `Co\.?` (common prefix), `Corp\.?`, `Inc\.?`, `Pte\.?` (Singapore), `GmbH` (German), `SA` (French/Spanish), `AG` (German/Swiss), `NV` (Dutch), `BV` (Dutch), `Pty\.?` (Australian), `group`, `fund`, `trust`, `holdings?`.

**Also add one new pattern** to the `_PATTERNS` list for the "Buys Shares of [number]" format where the specific share count in the title is the distinguishing signal. Real corporate news never says "Buys Shares of 10,810 Alphabet":

```python
    # "Gordian Capital Buys Shares of 10,810 Alphabet" / "Firm Purchases 2,800 Shares of JPMorgan"
    # The specific share count after "of" distinguishes fund disclosures from corporate M&A.
    # "Apple Buys Stake in AI Startup" does NOT match (no digit after "of").
    re.compile(
        r"\b(?:buys?|purchases?|acquires?)\s+(?:shares?|stake)\s+of\s+[\d,]+\s",
        re.IGNORECASE,
    ),
```

Add this pattern at the end of the `_PATTERNS` list, before the closing `]`.

---

## What NOT to Change

- **Do NOT modify `pipeline/html_renderer.py`**
- **Do NOT modify `model/model.py`** — no LLM prompt changes in this session
- **Do NOT modify `pipeline/run_test_pipeline.py`** — no pipeline flow changes
- **Do NOT modify `storage/vector_store.py`**
- **Do NOT modify `model/embedder.py`**
- **Do NOT modify the existing patterns** in `_PATTERNS` list beyond expanding the entity indicators in the three fund-anchored patterns (lines 86, 94, 102). Do not remove, reorder, or restructure any existing pattern.
- **Do NOT modify `_ROUNDUP_PATTERNS`** — those are working correctly.
- **Do NOT add a "Should You Buy" pattern** — articles like "Apple Just Unveiled the iPhone 17e. Should You Buy, Sell, or Hold AAPL Stock Now?" are legitimate news articles with a clickbait suffix.

---

## Validation

**Step 1:** Clear ChromaDB and re-ingest:
```bash
rm -rf chroma_store/
python news/news_ingest_pipeline.py
```

Check the ingestion log for:
- `speculative-filtered` count in the final summary — should be 3-8 articles per run
- Verify known speculative titles are caught: "Can Nvidia Stock Reach $10 Trillion..." should appear as "Filtering speculative:"
- Verify legitimate titles are NOT caught: "Apple Just Unveiled the iPhone 17e..." should NOT appear in any filter log

**Step 2:** Run the pipeline:
```bash
python pipeline/run_test_pipeline.py
```

Check `logs/pipeline_runs/` for the latest run log. Verify:
1. **Broad-match penalties appear in logs:** Lines like `[FAIL] similarity=0.764 (broad:-0.04) match='S&P 500'` should show articles that previously passed now failing due to the penalty.
2. **Fewer than 40 articles pass relevance** on typical days — the combination of time filter (from previous session) + broad penalty + speculative filter should reduce the passing count to 25-35, all higher quality.
3. **No speculative articles in the article list:** Titles containing "Can X Reach", "Where Will X Be", "If You Invested" should appear as `[SPECULATIVE]` skips, not `[PASS]`.
4. **No fund disclosure articles:** "SPX Gestao de Recursos Ltda" and "Gordian Capital Singapore Pte Ltd" titles should appear as `[NOISE]` skips.
5. **Key Insights quality improved:** No more "QQQ holds approximately 100 stocks" type insights. Each bullet should contain specific, actionable, recent facts.

**Step 3:** Open the HTML email in `logs/digests/html/` and read it as if you were the user. Every Key Insight should be a fact you'd want to know about your holdings. Every News story should be genuinely newsworthy. If you see generic commentary or speculative projections, check which article produced it and whether it should have been filtered.

---

## Summary of Changes

| File | Action | Details |
|------|--------|---------|
| `model/relevance_filter.py` | Add broad-match penalty | Define `_BROAD_MATCH_TERMS` set and `BROAD_MATCH_PENALTY` constant. Apply penalty to `best_similarity` before threshold check. Log the penalty. Import `is_speculative_article` and add query-time speculative filter. |
| `news/noise_filter.py` | Add speculative patterns | New `_SPECULATIVE_PATTERNS` list + `is_speculative_article()` function. Expand entity indicators in 3 fund-anchored patterns. Add "Buys Shares of [number]" pattern. |
| `news/news_ingest_pipeline.py` | Wire speculative filter | Import `is_speculative_article`, add filter check after roundup check, add counter, update summary log. |