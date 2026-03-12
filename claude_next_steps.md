# Fix: Movers Table JSON Parsing + HTML Email Template Generation

Read `CLAUDE.md` first. This prompt has two tasks:
1. Fix the Movers & Drivers table regression (all 20 tickers showing "No specific driver identified today")
2. Build an HTML email renderer that converts the pipeline's markdown digest into the `Portfolio Pulse` HTML email template

---

## Task 1: Fix Movers Table JSON Parse Failure

### The Problem

After the architecture refactor (3 calls → 2), the Movers & Drivers table shows "No specific driver identified today." for every ticker. The root cause: Call 1 (gemini-2.5-flash-lite) returns ~26K chars of insights JSON, and occasionally one entry has malformed JSON — e.g., a missing `"insight":` key name. When this happens, `json.loads()` fails on the entire response, the `except Exception: pass` in `_build_movers_section()` silently swallows the error, `ticker_drivers` stays empty, and all 20 tickers get the fallback text.

This is a **critical regression** — the Movers table is the first data section users see and it's completely empty.

### The Fix — `pipeline/run_test_pipeline.py`

Modify `_build_movers_section()` with two changes:

**Change 1: Add logging to the except block.** Replace `except Exception: pass` with:

```python
except Exception as e:
    logger.warning(f"Failed to parse insights JSON for movers table: {e}")
```

**Change 2: Add a regex fallback extractor.** When `json.loads()` fails, fall back to extracting ticker/insight pairs directly from the raw JSON text using regex. The insights JSON has a predictable structure where each insight object contains `"ticker": "XXX"` and `"insight": "YYY"` fields. Even when one entry is malformed, the other 19+ entries still have valid field patterns.

Here is the complete replacement for the JSON parsing block inside `_build_movers_section()`. Replace everything from `ticker_drivers: dict[str, str] = {}` through the end of the `except` block:

```python
    # Parse insights JSON → best driver string per ticker (first insight = highest quality)
    ticker_drivers: dict[str, str] = {}
    raw = insights_response.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[^\n]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

    # Primary path: parse full JSON
    try:
        for item in json.loads(raw).get("insights", []):
            t = item.get("ticker", "")
            if t and t not in ticker_drivers and item.get("insight"):
                ticker_drivers[t] = _truncate_at_sentence(item["insight"], limit=200)
    except Exception as e:
        logger.warning(f"JSON parse failed for movers drivers ({e}). Falling back to regex extraction.")
        # Fallback: extract "ticker"/"insight" pairs via regex from the raw text.
        # This recovers valid entries even when one malformed entry breaks json.loads().
        pattern = re.compile(
            r'"ticker"\s*:\s*"([^"]+)"'    # capture ticker value
            r'.*?'                           # non-greedy skip
            r'"insight"\s*:\s*"([^"]+)"',   # capture insight value
            re.DOTALL,
        )
        for match in pattern.finditer(raw):
            t, insight = match.group(1).strip(), match.group(2).strip()
            if t and insight and t not in ticker_drivers:
                ticker_drivers[t] = _truncate_at_sentence(insight, limit=200)
        logger.info(f"Regex fallback recovered drivers for {len(ticker_drivers)} tickers.")
```

**Do NOT change anything else in `_build_movers_section()`** — the sorting logic, arrow rendering, and table formatting are all correct.

### Validation for Task 1

Run the pipeline:
```bash
python pipeline/run_test_pipeline.py
```

Check the digest output in `logs/digests/`. The Movers & Drivers table should have real driver text for most or all tickers — not "No specific driver identified today." everywhere.

If you want to test the fallback specifically, you can temporarily corrupt one entry in the insights JSON before it reaches `_build_movers_section()` — but this isn't required. The primary path (`json.loads()`) will work on most runs. The fallback is insurance for the ~10-20% of runs where flash-lite produces one malformed entry.

---

## Task 2: HTML Email Template Renderer

### What We're Building

A Python function that takes the pipeline's markdown digest output and renders it into the `Portfolio Pulse` HTML email template. The template design already exists in `sample_templates/digest_2026-03-08.html` — the goal is to programmatically generate that same HTML from pipeline data.

### Where It Goes

Create a new file: `pipeline/html_renderer.py`

This file exports one function:

```python
def render_digest_html(
    portfolio_snapshot: dict,
    movers: list[dict],
    key_insights: list[dict],
    earnings_text: str,
    news_stories: list[dict],
    date_str: str,
    article_count: int,
    holdings_count: int,
) -> str:
```

It returns a complete HTML string (the full `<!DOCTYPE html>` to `</html>`) ready to be saved as a `.html` file or sent via email.

### The HTML Structure

Use the **exact CSS and HTML structure** from `sample_templates/digest_2026-03-08.html`. Copy the entire `<style>` block verbatim — do not modify any CSS. The HTML structure is:

```
1. <div class="meta"> — "Published on: {date}"
2. <div class="header"> — Brand + tagline (static)
3. <div class="intro"> — Greeting + 2-sentence summary (skip for now — hardcode a generic greeting)
4. Divider (🤝)
5. Portfolio Snapshot section — stats grid + top gainer/loser
6. Divider (📈)
7. Movers & Drivers section — table rows
8. Divider (💡)
9. Key Market Insights section — <ul> list with ticker tags
10. Divider (📅)
11. Upcoming Earnings section
12. Divider (📰)
13. News That Mattered section — headline + body + "Why it matters" spans
14. Footer (static)
```

### Input Data Format

The renderer receives pre-parsed structured data, NOT raw markdown. The pipeline (`run_test_pipeline.py`) will parse the markdown digest into these structures before calling the renderer.

**`portfolio_snapshot: dict`** — Parsed from the `## Portfolio Snapshot` section:
```python
{
    "est_value": "$143,664",
    "day_pnl": "+$2,929",
    "day_pnl_positive": True,
    "total_gain": "+$69,285",
    "total_gain_positive": True,
    "total_return": "+93.2%",
    "total_return_positive": True,
    "top_gainer": "NET (+5.7%)",
    "top_loser": "T (-1.4%)",
    "holdings_with_data": 20,
    "total_holdings": 25,
}
```

**`movers: list[dict]`** — Parsed from the `## Movers & Drivers` table:
```python
[
    {"ticker": "NET", "change": "▲ +5.7%", "positive": True, "driver": "Cloudflare's revenue climbed..."},
    {"ticker": "T", "change": "▼ -1.4%", "positive": False, "driver": "AT&T reported Q4 EPS..."},
    ...
]
```

**`key_insights: list[dict]`** — Parsed from the `Key Market Insights` section:
```python
[
    {"ticker": "T", "text": "Q4 2025 adjusted EPS of $0.52 beat $0.47 estimate..."},
    {"ticker": "TSLA", "text": "Reported Q4 EPS of $0.50 and revenue of $24.90B..."},
    ...
]
```

**`earnings_text: str`** — The raw earnings text (either event list or "No portfolio earnings events in the next 14 days.")

**`news_stories: list[dict]`** — Parsed from the `News That Mattered Today` section:
```python
[
    {
        "headline": "Costco Delivers Strong Earnings Beat",
        "body": "Costco's Q2 EPS of $4.58 beat estimates of $4.55...",
        "why_it_matters": "Beating both top and bottom lines signals robust consumer demand..."
    },
    ...
]
```

**`date_str: str`** — e.g., "March 10, 2026"

**`article_count: int`** — Number of relevant articles used (for intro text)

**`holdings_count: int`** — Total portfolio holdings (for intro text)

### HTML Rendering Rules

For each section, generate the HTML using the same class names and structure as the sample template:

**Portfolio Snapshot:** Use the `stats-grid` with 4 `stat-box` divs. Apply `class="pos"` or `class="neg"` to the `stat-value` based on the `_positive` boolean fields. Render the top gainer/loser in the `stat-note` paragraph.

**Movers Table:** Render as `<table class="movers-table">` with `<tr>` rows. Apply `class="col-change pos"` or `class="col-change neg"` based on the `positive` field. Use `html.escape()` on all text content (driver text may contain `&`, `<`, etc.).

**Key Insights:** Render as `<ul class="insights-list">` with `<li>` items. Wrap the ticker prefix in `<span class="ticker-tag">TICKER:</span>`.

**Earnings:** If the text is "No portfolio earnings..." render it in `<p class="earnings-empty">`. Otherwise, render the events (this can be a simple `<p>` for now since earnings are rarely in the window).

**News Stories:** Render each as a `<div class="news-item">` containing:
- `<p class="news-headline">{headline}</p>`
- `<p class="news-body">{body} <span class="why">Why it matters:</span> {why_it_matters}</p>`

**Intro paragraph:** For now, hardcode a generic greeting:
```
Good Evening! Here's your personalized portfolio digest for {date_str} — curated from {article_count} relevant articles across your {holdings_count} holdings.
```

**Footer:** Static HTML — copy verbatim from the sample template.

**Dividers:** Use the same divider HTML between sections (blue lines with circle emoji). Copy the exact HTML from the template.

**Important:** Use `html.escape()` from the `html` module on ALL dynamic text content before inserting into the HTML. This prevents broken rendering when article text contains `&`, `<`, `>`, or quotes. Do NOT escape the static HTML structure itself.

### Parsing the Markdown Digest

Add a parser function in the same file that extracts structured data from the pipeline's markdown output:

```python
def parse_digest_markdown(
    portfolio_summary_md: str,
    movers_md: str,
    editorial_md: str,
) -> dict:
```

This takes the three sections that `run_test_pipeline.py` already computes separately (portfolio_summary, movers_section, editorial_text) and parses them into the structured dicts described above.

**Parsing the Portfolio Snapshot (`portfolio_summary_md`):**
The format is predictable because `_build_portfolio_summary()` generates it:
```
## Portfolio Snapshot
**Est. Value:** $143,664  |  **Today's P&L:** +$2,929  |  **Total Gain:** +$69,285 (+93.2%)
**Top Gainer:** NET (+5.7%)  |  **Top Loser:** T (-1.4%)
_(Based on 20 of 25 holdings with today's data)_
```
Use regex to extract each value. The `+` or `-` prefix determines positive/negative styling.

**Parsing the Movers table (`movers_md`):**
The format is a markdown table generated by `_build_movers_section()`:
```
| **COST** | ▲ +3.1% | Costco Wholesale shares rose... |
```
Parse each row. `▲` means positive, `▼` means negative.

**Parsing the editorial text (`editorial_md`):**
This is the output from Call 2 (the editorial model). It has three sections:

1. `Key Market Insights` — bullet list starting with `- TICKER:`. Parse each line into `{"ticker": ..., "text": ...}`.

2. `Upcoming Earnings (your portfolio)` — capture everything between this header and the next section. Store as raw text.

3. `News That Mattered Today` — each story has a `**Bold Headline**` line, followed by body text, followed by `**Why it matters:**` text. Parse each story into `{"headline": ..., "body": ..., "why_it_matters": ...}`.

The editorial output format may vary slightly between runs (the LLM sometimes uses slightly different formatting). Make the parsers tolerant — use `re.DOTALL` and `re.IGNORECASE` where appropriate, and handle missing fields gracefully (e.g., if a news story has no "Why it matters" line, use an empty string).

### Wiring Into the Pipeline — `pipeline/run_test_pipeline.py`

At the end of the pipeline (after `save_eod_digest(full_digest)`), add a call to render and save the HTML:

```python
from pipeline.html_renderer import parse_digest_markdown, render_digest_html

# ... after save_eod_digest(full_digest) ...

# === Step 10: Render HTML email ===
logger.info("Rendering HTML email template...")
try:
    parsed = parse_digest_markdown(portfolio_summary, movers_section, editorial_text)
    date_display = datetime.now(_EST).strftime("%B %d, %Y")  # e.g., "March 10, 2026"
    html_output = render_digest_html(
        portfolio_snapshot=parsed["portfolio_snapshot"],
        movers=parsed["movers"],
        key_insights=parsed["key_insights"],
        earnings_text=parsed["earnings_text"],
        news_stories=parsed["news_stories"],
        date_str=date_display,
        article_count=len(relevant_articles),
        holdings_count=len(portfolio["equities"]),
    )
    html_path = _DIR_DIGESTS / f"digest_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_{_log_ts()}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_output)
    logger.info(f"HTML email saved: {html_path}")
except Exception as e:
    logger.error(f"Failed to render HTML email: {e}")
```

### What NOT to Change

- **Do NOT modify the CSS** in the template. Copy it exactly as-is from `sample_templates/digest_2026-03-08.html`.
- **Do NOT modify any existing pipeline functions** (except `_build_movers_section()` for the JSON fix in Task 1).
- **Do NOT modify `model/model.py`** — the LLM calls are not changing.
- **Do NOT modify any noise filter patterns.**
- **Do NOT modify `model/relevance_filter.py`.**
- **Do NOT add new LLM calls.** The intro paragraph is hardcoded for now, not LLM-generated.

---

## Validation

After both tasks, run:
```bash
python pipeline/run_test_pipeline.py
```

Check `logs/digests/` for the latest output. You should see both:
1. A `.md` file (existing markdown digest) — Movers table should now have real drivers
2. A `.html` file (new) — open in a browser and verify:
   - Portfolio Snapshot stats grid renders with green/red coloring
   - Movers table has all tickers with drivers and correct ▲/▼ coloring
   - Key Insights has blue ticker tags
   - News stories have bold headlines and "Why it matters:" in bold
   - Footer renders correctly
   - Mobile responsive (shrink browser to 400px width)

If the HTML output has broken formatting, check:
- Are you using `html.escape()` on all dynamic text? Articles with `&` in company names (AT&T, Johnson & Johnson) will break HTML if not escaped.
- Is the CSS being copied exactly from the sample template? Don't modify spacing or class names.
- Are the section dividers present between every section?

---

## Summary

| File | Action |
|------|--------|
| `pipeline/run_test_pipeline.py` | Fix `_build_movers_section()` JSON parsing: add logging + regex fallback. Add Step 10: HTML rendering call at end of pipeline. Add import for `html_renderer`. |
| `pipeline/html_renderer.py` | **New file.** Contains `parse_digest_markdown()` and `render_digest_html()`. Copies CSS from sample template. Renders all 6 sections into a complete HTML email. |