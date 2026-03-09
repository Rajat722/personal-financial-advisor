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


def _generate(contents: str) -> str:
    """Call generate_content with primary key; fall back to secondary on quota exhaustion."""
    global _primary_exhausted

    if not _primary_exhausted:
        try:
            return _primary_client.models.generate_content(
                model=settings.GEMINI_SUMMARY_MODEL, contents=contents
            ).text
        except ResourceExhausted:
            if _fallback_client is None:
                raise RuntimeError(
                    "Primary Gemini key quota exhausted and GEMINI_FALLBACK_API_KEY is not set."
                )
            log.warning("Primary Gemini key quota exhausted — switching to fallback key.")
            _primary_exhausted = True
        # Fall through to fallback.

    if _fallback_client is None:
        raise RuntimeError(
            "Primary Gemini key quota exhausted and GEMINI_FALLBACK_API_KEY is not set."
        )
    try:
        return _fallback_client.models.generate_content(
            model=settings.GEMINI_SUMMARY_MODEL, contents=contents
        ).text
    except ResourceExhausted as e:
        raise RuntimeError("Both Gemini API keys have exhausted their quota.") from e

def build_article_summary_prompt(article_text: str) -> str:
    """Build a Gemini prompt to extract entity and top 5 insights from a single article."""
    return f"""
You are a financial analyst AI. Your job is to extract structured information from a news article.

STRICT RULES — you must follow these exactly:
- Only reference information explicitly stated in the article text below.
- Do NOT infer, speculate, or add context not present in the article.
- Do NOT mention any company, ticker, or event not directly named in the article.
- If a stock ticker is not mentioned by name in the article, do not reference it.
- Insights must quote or paraphrase the article directly.

Return a JSON object with this format:
{{
  "entity": "The single most important company, stock, or institution explicitly named in the article",
  "insights": [
    "Insight 1 — directly from article content",
    "Insight 2 — directly from article content",
    "Insight 3 — directly from article content",
    "Insight 4 — directly from article content",
    "Insight 5 — directly from article content"
  ]
}}

Article:
\"\"\"
{article_text}
\"\"\"
"""


@gemini_retry(max_attempts=settings.GEMINI_RETRY_ATTEMPTS, base_delay=settings.GEMINI_RETRY_DELAY)
def summarize_article(article_text: str) -> str:
    """Summarize a single article via Gemini and return JSON string with entity and insights."""
    prompt = build_article_summary_prompt(article_text)
    return _generate(prompt)

def build_multi_article_summary_prompt(article_blocks: str) -> str:
    """Build a Gemini prompt to summarize multiple articles in a single call."""
    return f"""
You are a financial analyst AI. Summarize each article below.

STRICT RULES — you must follow these exactly:
- Only use information explicitly stated in each article.
- Do NOT infer, speculate, or add context not in the article text.
- Do NOT reference any ticker or company not directly named in that article.
- Each insight must be grounded in the article it came from.

Return a JSON array where each element corresponds to one article (in order):
[
  {{
    "title": "exact article title",
    "entity": "single most important company or stock explicitly named in the article",
    "insights": [
      "Insight 1 — directly from article",
      "Insight 2 — directly from article",
      "Insight 3 — directly from article"
    ]
  }},
  ...
]

Articles:
\"\"\"
{article_blocks}
\"\"\"
"""

@gemini_retry(max_attempts=settings.GEMINI_RETRY_ATTEMPTS, base_delay=settings.GEMINI_RETRY_DELAY)
def summarize_multiple_articles(article_blocks: str) -> str:
    """Batch-summarize multiple articles via Gemini and return a JSON array string."""
    prompt = build_multi_article_summary_prompt(article_blocks)
    return _generate(prompt)

def build_insight_prompt(article_blocks: str, time_series_json: str) -> str:
    """Build a Gemini prompt correlating news articles with intraday price movements."""
    return f"""
You are a financial analyst correlating news events with intraday stock price movements.

STRICT RULES — you must follow these exactly:
- Only reference tickers that are explicitly named in the news articles provided.
- Do NOT claim a ticker is affected unless the article directly names that company or its ticker.
- Do NOT speculate. If an article is about Company X, do not imply it affects Company Y unless the article states so.
- Each insight must cite a specific article by title.
- If no article supports an insight for a ticker, omit that ticker entirely.
- "correlation_type" must be "direct" (article names the ticker) or "indirect" (article names a competitor/supplier/customer that the article explicitly links to this ticker).
- QUALITY THRESHOLD: Only generate an insight if it contains a CONCRETE, SPECIFIC fact useful to an investor — earnings or revenue numbers, a % price movement, an analyst rating or price target change, a product launch, M&A activity, or a management change. DO NOT generate insights where the ticker is merely mentioned in passing, listed in a group of companies, named as an ETF holding, or cited as a general example. If an article about Company A lists Company B in a sidebar or comparison table, do not generate an insight for Company B. Quality over quantity — fewer precise insights is better than many vague ones.

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

Time series data:
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
    return _generate(prompt)

def build_eod_summary_prompt(insights_json: str, summarized_articles: str, earnings_context: str = "") -> str:
    """Build a Gemini prompt to generate a narrative end-of-day market summary."""
    earnings_section = earnings_context.strip() if earnings_context.strip() else "No portfolio earnings events in the next 14 days."
    return f"""
You are a financial news assistant writing a personalized end-of-day digest for a retail investor.

STRICT RULES:
- Only discuss companies, tickers, sectors, or events explicitly present in the insights and article summaries below.
- Do NOT mention any ticker not referenced in the inputs.
- Do NOT invent price targets, analyst ratings, or events not stated in the source material.
- Every claim must trace directly to an article or insight provided to you.
- If the inputs contain no relevant information for a section, write "No relevant updates today."
- For the Earnings Calendar section, reproduce the data exactly as provided — do not invent estimates, dates, or results.
- DEDUPLICATION: If the same fact, statistic, or event appears in multiple articles, mention it EXACTLY ONCE in its most complete form. Do not repeat the same bullet point or restate the same number/event in different words.
- COMPLETENESS: Cover EVERY distinct company or ticker that has substantive news in the inputs. Do not drop any company. If a company has multiple articles, consolidate them into one or two bullet points — do not skip the company entirely.
- KEY MARKET INSIGHTS must prioritize: earnings/revenue results with numbers, analyst rating or price target changes with specific values, significant % price movements, product launches, M&A, and management changes. Do NOT include: ETF holdings mentions, companies merely listed in a group, or generic market observations with no specific data.
- KEY MARKET INSIGHTS LIMIT: Maximum 15 bullets total — this is a hard limit. Consolidate all insights for a single ticker into EXACTLY ONE bullet — the single most important fact for that ticker. Never write two bullets for the same ticker. If you have more than 15 tickers with news, pick the 15 most significant. Rank by: earnings beats/misses > analyst upgrades/price targets > product launches > general commentary.
- SECTION ROLES — avoid repeating the same fact across sections: The Movers & Drivers table already covers price movement and primary driver for each stock. Key Market Insights should add DIFFERENT facts not already stated as a Movers driver: additional earnings details, analyst upgrades, product launches, M&A. News That Mattered Today should cover articles whose key points were NOT already mentioned in Key Market Insights — do not restate the same earnings number or event that already appears above.
- INSIDER TRANSACTIONS: Do NOT mention insider stock sales or purchases under $1,000,000 (one million dollars total value). Only cite insider transactions exceeding $1M — these are material. Example to exclude: a COO selling 629 shares totaling $400K. Example to include: a CFO selling $36M worth of shares.
- NEWS THAT MATTERED TODAY: Include AT MOST 10 items — this is a hard limit, never exceed it. Rank by importance and pick the 10 most impactful articles. Each article must appear AT MOST ONCE. Do NOT create multiple entries for the same article title. For each article, write exactly one bullet with the single most important insight from that article in one sentence. If two articles cover the same story, pick the one with more detail and skip the other. Skip any article whose key point was already covered in Key Market Insights.

Write a concise, professional summary using this structure:

---
Key Market Insights
- [Company/Ticker]: [Specific fact — earnings number, % move, PT change, product launch, etc.]
- [Company/Ticker]: [Specific fact — grounded in provided data]

Upcoming Earnings (your portfolio)
{earnings_section}

News That Mattered Today
- "[Exact Article Title]" — [One sentence covering the article's single most important point]
- "[Exact Article Title]" — [One sentence covering the article's single most important point]
---

Insights provided:
{insights_json}

Article summaries provided:
{summarized_articles}
"""


@gemini_retry(max_attempts=settings.GEMINI_RETRY_ATTEMPTS, base_delay=settings.GEMINI_RETRY_DELAY)
def get_end_of_day_summary(insights_json: str, summarized_articles: str, earnings_context: str = "") -> str:
    """Generate and return a personalized end-of-day market digest via Gemini."""
    prompt = build_eod_summary_prompt(insights_json, summarized_articles, earnings_context)
    return _generate(prompt)
