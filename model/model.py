# model.py
from dotenv import load_dotenv
from google import genai

from core.config import settings
from core.logging import get_logger
from utils.retry import gemini_retry

try:
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    ResourceExhausted = Exception  # type: ignore

load_dotenv()

log = get_logger("model")

_primary_client = genai.Client(api_key=settings.GEMINI_API_KEY)
_fallback_client = (
    genai.Client(api_key=settings.GEMINI_FALLBACK_API_KEY)
    if settings.GEMINI_FALLBACK_API_KEY
    else None
)

# Session flag: once primary quota is exhausted, skip straight to fallback.
_primary_exhausted: bool = False


def _generate(contents: str, model: str | None = None) -> str:
    """Call generate_content with primary key; fall back to secondary on quota exhaustion."""
    global _primary_exhausted
    model = model or settings.GEMINI_EXTRACT_MODEL

    if not _primary_exhausted:
        try:
            return _primary_client.models.generate_content(
                model=model, contents=contents
            ).text
        except ResourceExhausted:
            if _fallback_client is None:
                raise RuntimeError(
                    "Primary Gemini key quota exhausted and GEMINI_FALLBACK_API_KEY is not set."
                )
            log.warning("Primary Gemini key quota exhausted — switching to fallback key.")
            _primary_exhausted = True

    if _fallback_client is None:
        raise RuntimeError(
            "Primary Gemini key quota exhausted and GEMINI_FALLBACK_API_KEY is not set."
        )
    try:
        return _fallback_client.models.generate_content(
            model=model, contents=contents
        ).text
    except ResourceExhausted as e:
        raise RuntimeError("Both Gemini API keys have exhausted their quota.") from e

def build_insight_prompt(article_blocks: str, time_series_json: str) -> str:
    """Build a Gemini prompt extracting actionable facts from news articles for portfolio holdings."""
    from datetime import datetime
    import pytz
    today_str = datetime.now(pytz.timezone("US/Eastern")).strftime("%B %d, %Y")
    return f"""
You are a financial analyst extracting actionable facts from news articles for a portfolio of stocks. You are given today's price summary (open, close, change %) and news articles grouped by ticker.

Today's date: {today_str}

STRICT RULES — you must follow these exactly:
- Only reference tickers that are explicitly named in the news articles provided.
- Do NOT claim a ticker is affected unless the article directly names that company or its ticker.
- Do NOT speculate. If an article is about Company X, do not imply it affects Company Y unless the article states so.
- Each insight must cite a specific article by title.
- If no article supports an insight for a ticker, omit that ticker entirely.
- "correlation_type" must be "direct" (article names the ticker) or "indirect" (article names a competitor/supplier/customer that the article explicitly links to this ticker).
- QUALITY THRESHOLD: Only generate an insight if it contains a CONCRETE, SPECIFIC fact useful to an investor — earnings or revenue numbers, an analyst rating or price target change, a product launch, M&A activity, or a management change. DO NOT generate insights where the ticker is merely mentioned in passing, listed in a group of companies, named as an ETF holding, or cited as a general example. If an article about Company A lists Company B in a sidebar or comparison table, do not generate an insight for Company B. Quality over quantity — fewer precise insights is better than many vague ones.
- PRICE-ONLY ARTICLES: Articles whose entire content is the price movement itself ("Company X Trading 1.3% Higher — Time to Buy?", "Shares Down 1.7% — Here's What Happened", "Stock Price Down X% After Insider Selling") are price alerts, not news. Do NOT generate an insight whose "insight" field merely restates the price movement. The insight must cite a specific NEWS-DRIVEN cause — an earnings number, analyst action, product announcement, or corporate event. If the only available article for a ticker is a price alert with no underlying cause, omit that ticker entirely.
- TEMPORAL AWARENESS: Each article includes a "Published:" date. When correlating articles with today's price data, strongly prefer articles published within the last 24 hours. If an article is older than 2 days, note the publish date in the "support" field and mark the insight as potentially stale. Do NOT attribute price movements today to articles published 3+ days ago — the market has already priced in that information.
- DRIVER ORDERING: For each ticker, output the most important and most recent insight FIRST. This is critical because the first insight per ticker is used as the headline driver for today's price movement. Rank by: breaking news today > earnings/revenue numbers > analyst upgrades/downgrades > product launches > general commentary. Historical earnings (published weeks ago) must be listed last.
- CONSOLIDATION: If multiple articles report the same fact for a ticker (e.g., the same earnings number, the same CEO quote), produce ONE insight with the most complete version. Do not repeat the same fact from different sources.
- ANALYST RATINGS: If an article lists multiple analyst ratings or price targets for one ticker, consolidate into ONE insight summarizing the range and consensus (e.g., "Multiple analysts raised NVDA price targets to $235-$300; consensus is bullish with most firms rating Buy or Outperform"). Do NOT create a separate insight for each individual analyst.
- PER-TICKER CAP: Maximum 3 insights per ticker. Keep the 3 most material: earnings/revenue data > analyst consensus > product/M&A news > general commentary. If a ticker has only low-value information (passing mentions, ETF holdings), emit 0 insights for it.

Return a JSON object:
{{
  "insights": [
    {{
      "ticker": "NVDA",
      "insight": "Nvidia's data center revenue beat expectations per Q3 earnings report",
      "support": "Article: 'Nvidia Q3 Earnings Beat' — states data center revenue up 122% YoY",
      "correlation_type": "direct"
    }},
    ...
  ]
}}

Today's price summary:
\"\"\"
{time_series_json}
\"\"\"

News articles:
\"\"\"
{article_blocks}
\"\"\"
"""


@gemini_retry(max_attempts=settings.GEMINI_RETRY_ATTEMPTS, base_delay=settings.GEMINI_RETRY_DELAY)
def get_insights_from_news_and_prices(article_blocks: str, time_series_json: str) -> str:
    """Return Gemini-generated JSON insights linking news events to portfolio price movements."""
    prompt = build_insight_prompt(article_blocks, time_series_json)
    return _generate(prompt, model=settings.GEMINI_EXTRACT_MODEL)


def build_editorial_prompt(
    insights_json: str,
    portfolio_snapshot: str,
    movers_table: str,
    article_titles_urls: str,
    earnings_context: str = "",
    portfolio_tickers: str = "",
) -> str:
    """Build the Call 2 editorial prompt: takes analyst data and writes a polished newsletter."""
    earnings_section = earnings_context.strip() if earnings_context.strip() else "No portfolio earnings events in the next 14 days."
    return f"""You are the editor-in-chief of Portfolio Pulse, a personalized daily finance newsletter for retail investors aged 25-35 who hold 5-20 stocks. You write like a sharp, concise financial journalist — not a robot, not a textbook.

You are given pre-extracted analyst data (structured JSON), a computed portfolio snapshot, a computed movers table, article titles with URLs, and an earnings calendar. The analyst already extracted the facts. Your job is to WRITE the newsletter — add editorial judgment, condense redundant information, and explain why things matter to someone who checks Robinhood but doesn't read the WSJ.

=== SECTION 1: KEY MARKET INSIGHTS ===

Write a bullet list of the most important facts for the reader's holdings.

RULES:
- HARD LIMIT: Maximum 15 bullets. If there are more than 15 tickers with news, pick the 15 most significant.
- ONE bullet per ticker — consolidate all facts for a ticker into a single, information-dense bullet. If COST has an earnings beat AND a price target raise, combine them: "COST: Earnings beat ($4.58 vs $4.55 est.) and BMO raised PT to $1,315 from $1,175."
- Rank by importance: earnings beats/misses with numbers > analyst upgrades/price targets > product launches > management changes > general commentary.
- Do NOT repeat any fact that already appears as a driver in the Movers & Drivers table below. Key Insights should add DIFFERENT or ADDITIONAL facts for each ticker. If the Movers driver already says "Costco EPS of $4.58 beat estimates," then Key Insights for COST should cover the PT raise or tariff refund news instead.
- INSIDER TRANSACTIONS: Do NOT mention insider stock sales or purchases under $1,000,000 total value. Only include insider transactions above $1M.
- Each bullet starts with the ticker symbol followed by a colon.
- Every fact must come from the analyst insights JSON below. Do not invent numbers, price targets, or events.

=== SECTION 2: UPCOMING EARNINGS ===

Reproduce this exactly as provided:
{earnings_section}

=== SECTION 3: NEWS THAT MATTERED TODAY — "The Stories Behind the Moves" ===

Select the TOP 8 most impactful stories. For each story:
- Write a SHORT, punchy headline (rewrite the original title to be cleaner — drop exchange tags like "NASDAQ:COST", drop clickbait phrasing like "Here's Why")
- Write 1-2 sentences summarizing the key fact from the article
- Write a "Why it matters:" analysis sentence that connects the fact to what it means for the reader's portfolio. This is the editorial value-add. Use your financial knowledge to explain implications — what does an earnings beat signal? What does an insider sale pattern suggest? Why should a Robinhood investor care?

RULES FOR "Why it matters:":
- Your ANALYSIS can draw on general financial knowledge (e.g., "beating EPS by 13% while the stock falls is a classic buy-the-rumor-sell-the-news pattern")
- But every FACT you cite must come from the analyst insights JSON. Never invent specific numbers, price targets, analyst names, or events not in the data.
- If two articles cover the same event (e.g., two COST earnings articles), merge them into ONE story with the combined facts. Do not list both.
- A story CAN appear in both Key Market Insights AND News That Mattered — they serve different purposes. Key Insights gives the compressed fact; News That Mattered gives narrative context and the "Why it matters" analysis. Do NOT skip a story from News just because its numbers also appear in Key Insights. Only skip a story from News if it has zero additional narrative value beyond what Key Insights already said — e.g., a bare price movement with no underlying event.
- Tone: confident, direct, occasional wit. Write for a smart 28-year-old, not a finance professor.

=== OUTPUT FORMAT ===

Write in this exact markdown structure:

Key Market Insights
- TICKER: [condensed, information-dense bullet with the single most important NEW fact]
- TICKER: [condensed bullet]

Upcoming Earnings (your portfolio)
[earnings data as provided]

News That Mattered Today
**[Clean Headline]**
[1-2 sentence summary of key fact.] **Why it matters:** [Editorial analysis connecting the fact to the reader's portfolio — what does this mean, why should they care, what's the implication.]

**[Clean Headline]**
[1-2 sentence summary.] **Why it matters:** [Editorial analysis.]

=== STRICT RULES ===
- Every factual claim must trace to the analyst insights JSON or article titles provided. Do NOT hallucinate.
- Do NOT mention any ticker not present in the insights data.
- PORTFOLIO TICKER ALLOWLIST: You may ONLY mention the following tickers. Any ticker not in this list must be completely excluded from Key Insights, News That Mattered, and all other sections — even if it appears in the analyst insights JSON. Non-portfolio tickers sometimes leak into insights via cross-article contamination.
  ALLOWED TICKERS: {portfolio_tickers}
- Do NOT invent price targets, analyst ratings, revenue numbers, or events.
- DEDUPLICATION: If the same fact appears in the insights JSON multiple times (same event from different articles), mention it ONCE in its most complete form.
- The Movers & Drivers table is already written and will appear above your output. Do NOT regenerate it. Do NOT write a Portfolio Snapshot section — that's also already computed.

=== INPUT DATA ===

PORTFOLIO SNAPSHOT (already rendered — for your context only, do not reproduce):
\"\"\"
{portfolio_snapshot}
\"\"\"

MOVERS & DRIVERS TABLE (already rendered — for your context only, do not repeat these driver facts in Key Insights):
\"\"\"
{movers_table}
\"\"\"

ANALYST INSIGHTS JSON (source of truth for all facts):
\"\"\"
{insights_json}
\"\"\"

ARTICLE TITLES AND URLS (for attribution in News section):
\"\"\"
{article_titles_urls}
\"\"\"
"""


@gemini_retry(max_attempts=settings.GEMINI_RETRY_ATTEMPTS, base_delay=settings.GEMINI_RETRY_DELAY)
def generate_editorial_digest(
    insights_json: str,
    portfolio_snapshot: str,
    movers_table: str,
    article_titles_urls: str,
    earnings_context: str = "",
    portfolio_tickers: str = "",
) -> str:
    """Generate the editorial newsletter via Gemini flash (Call 2)."""
    prompt = build_editorial_prompt(
        insights_json, portfolio_snapshot, movers_table, article_titles_urls,
        earnings_context, portfolio_tickers,
    )
    return _generate(prompt, model=settings.GEMINI_EDITORIAL_MODEL)
