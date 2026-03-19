# Next Steps — Digest Quality: Staleness & Signal Optimization

**Date:** March 18, 2026
**Branch:** dev_phase_1
**Goal:** Eliminate stale insights (old earnings, old events) from digests and improve signal quality of data flowing into Gemini calls.

---

## Problem Statement

~50% of digest insights reference events >1 week old (some 1-2 months old). Root cause: articles published recently but containing old content (e.g., Motley Fool article from March 17 discussing Tesla Q4 Dec 2025 earnings). The pipeline's time window filter checks `published_ts` (when the article was published), NOT when the event actually occurred.

---

## Implementation Plan (in execution order)

### Step 1: Add today's date to Call 1 prompt [3d]
**File:** `model/model.py` — `build_insight_prompt()`
**What:** Add `Today's date: {today}` at the top of the prompt, before STRICT RULES.
**Why:** Flash-lite currently has no anchor for "today." It sees `Published: 2026-03-17T15:30:00` but doesn't know what today is, so it can't judge freshness. Explicitly stating today's date makes the existing TEMPORAL AWARENESS rule enforceable.
**Risk:** None.

### Step 2: Human-readable article age in article blocks [3a]
**File:** `pipeline/run_test_pipeline.py` — `format_article_blocks()`
**What:** Replace `Published: 2026-03-17T15:30:00+00:00` with `Published: 3 hours ago (reuters.com)`.
- Parse `published_iso` → compute delta from now → format as "X hours ago" / "yesterday" / "X days ago"
- Append source domain in parentheses (covers step 3b too)
**Why:** Flash-lite understands "2 days ago" far better than ISO timestamp arithmetic. Also gives the LLM source credibility context.
**Risk:** None. The ISO date is still in metadata for Python-level checks.

### Step 3: Source domain in article blocks [3b]
**Covered by Step 2** — source domain appended to the Published line.

### Step 4: Temporal marker scan on insight text (post-Call 1) [4b]
**File:** `pipeline/run_test_pipeline.py` — new function `_filter_stale_insights()`
**What:** After Call 1, scan each insight's text for temporal markers indicating old events:
- Quarter references: `Q[1-4] YYYY` → map to quarter-end date → stale if >45 days ago
- Month references: `in January`, `in February` → stale if >30 days in the past
- Fiscal year: `fiscal year YYYY` → stale if FY ended >45 days ago
- Drop stale insights, log what was dropped and why.
**Why:** Catches the core problem — articles with fresh publication dates but stale content.
**Risk:** MEDIUM — could drop valid insights during earnings season. Mitigations:
- 45-day tolerance for quarter references (covers full earnings season)
- Only flag months that are clearly in the past
- Add explicit comment in code documenting the risk
- Log all dropped insights so we can audit and tune

### Step 5: Tag stale content at ingest [1a]
**File:** `news/news_ingest_pipeline.py`
**What:** Before storing an article, scan its summary for temporal markers (same regex patterns as Step 4). If the event is >2 weeks old, add `"content_stale": true` to article metadata. Article is STILL stored — not blocked.
**File:** `model/relevance_filter.py`
**What:** When `content_stale` is true, apply an additional similarity penalty (0.03) so stale-content articles need higher relevance to compete.
**Why:** Defense in depth — catches staleness earlier in the pipeline without blocking anything.
**Risk:** Low. Articles are never blocked, just penalized. If the tagging is wrong, the article still has a chance to pass with high enough similarity.

### Step 6: Source-aware text cap for low-signal sources [1b]
**File:** `pipeline/run_test_pipeline.py` — `_enrich_articles_with_full_text()`
**What:** For articles from `_LOW_SIGNAL_SOURCES` (fool.com, zacks.com, etc.), cap scraped body at 500 chars instead of 1500. Still scrape — just less boilerplate.
**Why:** Motley Fool body text is ~800 chars of disclaimers + recycled data. 500 chars captures the lead fact without the noise. We still scrape (not skip) to avoid hallucination risk from title-only input.
**Risk:** Low. The article summary is always present. 500 chars of body is enough for the key fact.

---

## NOT Doing (and why)

| Idea | Why skipped |
|------|-------------|
| Skip scraping entirely for low-signal sources | Would cause flash-lite to hallucinate from title-only input |
| Post-filter insights by article publication date (4a) | Redundant — tier-based time windows already filter articles by pub date before Call 1 |
| Relevance filter optimizations (Stage 2) | Already well-tuned — source penalty, broad-match penalty, tier windows all working |
| 3rd Gemini call (validation pass) | Try Python-level enforcement first — cheaper, faster, deterministic |
| Secondary news source | User researching options; implement later |
| Flash for Call 1 (tested, reverted) | Flash over-consolidates — produces fewer, vaguer insights. Flash-lite's granular extraction style suits Call 1 better |

---

## Verification

After implementing all steps, run:
```bash
python news/news_ingest_pipeline.py
python pipeline/run_test_pipeline.py
```

Check:
1. Pipeline log shows `[STALE-INSIGHT]` entries for old-event insights being dropped
2. Article blocks show "Published: X hours ago (source.com)" format
3. Call 1 prompt starts with today's date
4. Digest has fewer stale insights vs. March 17 baseline
5. No reduction in fresh, high-quality insights
