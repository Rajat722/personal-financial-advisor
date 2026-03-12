# Portfolio Pulse — AI-Powered Personal Finance Newsletter

An AI pipeline that fetches financial news, filters it to your specific stock holdings, and generates a personalized daily digest — delivered as a polished HTML email.

**What it does:** Most financial news is irrelevant to you. This surfaces only what matters to your holdings — with real price data, insider transaction filtering, analyst upgrades, and editorial "Why it matters" context written for a retail investor, not a finance professor.

---

## How It Works

```
News (NewsData.io) → Noise Filter → ChromaDB Vector Store
                                           ↓
Portfolio Holdings → Relevance Filter (cosine similarity ≥ 0.75)
                                           ↓
                              40 most relevant articles
                                           ↓
                    Call 1: Gemini flash-lite → Structured insights JSON
                                           ↓
              yfinance intraday data → Portfolio Snapshot + Movers table
                                           ↓
                    Call 2: Gemini flash → Editorial newsletter text
                                           ↓
                              Markdown digest + HTML email
```

**Output per run:**
- `logs/digests/digest_YYYY-MM-DD_*.md` — plain markdown digest
- `logs/digests/html/digest_YYYY-MM-DD_*.html` — styled HTML email (open in browser)

---

## Setup

### 1. Prerequisites

- Python 3.11+
- Conda (recommended) or virtualenv

### 2. Create environment and install dependencies

```bash
conda create -n finAdvisor python=3.11
conda activate finAdvisor
pip install -r requirements.txt
```

### 3. Configure API keys

Create a .env file if it doesn't exist.
Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=your_gemini_api_key        # Required — google.com/gemini
NEWSDATA_API_KEY=your_newsdata_api_key    # Required — newsdata.io
MAILERSEND_API_KEY=                       # Optional — not yet wired up
```

Optional fallback keys (used when primary quota is exhausted):
```env
GEMINI_FALLBACK_API_KEY=your_second_gemini_key
NEWSDATA_FALLBACK_API_KEY=your_second_newsdata_key
```

### 4. Configure your portfolio

Edit `user_portfolio/portfolio.json` with your holdings:

```json
{
  "equities": [
    { "ticker": "AAPL", "company": "Apple", "shares": 10, "avg_cost_basis": 150.00 },
    { "ticker": "NVDA", "company": "Nvidia", "shares": 5,  "avg_cost_basis": 220.00 }
  ]
}
```

> **Note:** Changing `portfolio.json` invalidates the ChromaDB embeddings. Delete `chroma_store/` after any portfolio change and re-run news ingestion.

---

## Running the Pipeline

### Full run (recommended daily workflow)

```bash
# Step 1: Fetch and store today's news
python news/news_ingest_pipeline.py

# Step 2: Generate the digest
python pipeline/run_test_pipeline.py
```

Check `logs/digests/html/` for the latest HTML email output.

### Run pipeline only (reuse existing news)

```bash
python pipeline/run_test_pipeline.py
```

Uses whatever articles are already in ChromaDB. Useful for re-running the digest without spending API credits on news ingestion.

### Best time to run

Run after US market close (4:30 PM ET or later) for accurate intraday price data. The pipeline gracefully falls back to the previous trading day's data when run before or during market hours.

---

## Project Structure

```
├── pipeline/
│   ├── run_test_pipeline.py    # Main orchestration — run this
│   └── html_renderer.py        # Converts markdown digest → HTML email
├── model/
│   ├── model.py                # Gemini prompts (Call 1: analyst, Call 2: editor)
│   ├── relevance_filter.py     # Cosine similarity filtering against portfolio
│   └── embedder.py             # Gemini embedding wrapper
├── news/
│   ├── news_ingest_pipeline.py # Fetches news, filters noise, stores in ChromaDB
│   └── noise_filter.py         # Regex patterns for junk articles
├── utils/
│   └── stock_details.py        # yfinance OHLCV + earnings calendar
├── storage/
│   └── vector_store.py         # ChromaDB wrapper
├── core/
│   ├── config.py               # Pydantic settings (reads from .env)
│   └── logging.py              # Structured logger
├── user_portfolio/
│   └── portfolio.json          # Your holdings — edit this
├── logs/
│   ├── digests/                # Markdown digests
│   │   └── html/               # HTML email outputs
│   ├── insights/               # Raw Gemini Call 1 JSON responses
│   └── pipeline_runs/          # Full run logs
├── chroma_store/               # ChromaDB local persistence (auto-created)
└── sample_templates/           # Reference HTML email designs
```

---

## Useful Commands

```bash
# Run tests
python -m pytest tests/ -v

# Check ChromaDB article count
python -c "import chromadb; c = chromadb.PersistentClient(path='chroma_store'); print([(col.name, col.count()) for col in c.list_collections()])"

# Clear ChromaDB (after portfolio changes or noise filter updates)
rm -rf chroma_store/
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM — extraction | Gemini `gemini-2.5-flash-lite` |
| LLM — editorial | Gemini `gemini-2.5-flash` |
| Embeddings | Gemini `gemini-embedding-001` (3072-dim) |
| Vector store | ChromaDB (local) |
| News source | NewsData.io |
| Stock data | yfinance (30-min OHLCV + earnings calendar) |
| Config | pydantic-settings |
