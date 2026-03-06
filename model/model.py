# model.py
from dotenv import load_dotenv
from google import genai

from core.config import settings
from utils.retry import gemini_retry

load_dotenv()

_client = genai.Client(api_key=settings.GEMINI_API_KEY)

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
    response = _client.models.generate_content(model=settings.GEMINI_SUMMARY_MODEL, contents=prompt)
    return response.text

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
    response = _client.models.generate_content(model=settings.GEMINI_SUMMARY_MODEL, contents=prompt)
    return response.text

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
    response = _client.models.generate_content(model=settings.GEMINI_SUMMARY_MODEL, contents=prompt)
    return response.text

def build_eod_summary_prompt(insights_json: str, summarized_articles: str) -> str:
    """Build a Gemini prompt to generate a narrative end-of-day market summary."""
    return f"""
You are a financial news assistant writing a personalized end-of-day digest for a retail investor.

STRICT RULES:
- Only discuss companies, tickers, sectors, or events explicitly present in the insights and article summaries below.
- Do NOT mention any ticker not referenced in the inputs.
- Do NOT invent price targets, analyst ratings, or events not stated in the source material.
- Every claim must trace directly to an article or insight provided to you.
- If the inputs contain no relevant information for a section, write "No relevant updates today."

Write a concise, professional summary using this structure:

---
Key Market Insights
- [Insight 1 — grounded in provided data]
- [Insight 2 — grounded in provided data]

News That Mattered Today
- "[Article Title]" — [1-sentence summary based only on article content]
- "[Article Title]" — [1-sentence summary based only on article content]
---

Insights provided:
{insights_json}

Article summaries provided:
{summarized_articles}
"""


@gemini_retry(max_attempts=settings.GEMINI_RETRY_ATTEMPTS, base_delay=settings.GEMINI_RETRY_DELAY)
def get_end_of_day_summary(insights_json: str, summarized_articles: str) -> str:
    """Generate and return a personalized end-of-day market digest via Gemini."""
    prompt = build_eod_summary_prompt(insights_json, summarized_articles)
    response = _client.models.generate_content(model=settings.GEMINI_SUMMARY_MODEL, contents=prompt)
    return response.text
