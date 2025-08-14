# model.py
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# model = genai.GenerativeModel("gemini-1.5-pro")
model = genai.GenerativeModel(model_name="gemini-2.0-flash")

# === ORIGINAL: Summarize individual article ===
def build_article_summary_prompt(article_text):
    return f"""
You are a financial analyst AI.

Given a finance-related news article, return a JSON object with the following format:

{{
  "entity": "Most important financial stock, company, or institution in the article",
  "insights": [
    "Top 5 insights from the article, extracted exactly from the content",
    "Do not guess or invent any insight not in the article",
    "Ensure output is strictly valid JSON",
    "Keep insights focused on financial relevance"
  ]
}}

Here is the article:
\"\"\"
{article_text}
\"\"\"
"""


def summarize_article(article_text):
    prompt = build_article_summary_prompt(article_text)
    response = model.generate_content(prompt)
    return response.text

# === NEW: Summarize multiple articles in one Gemini call ===
def build_multi_article_summary_prompt(article_blocks):
    return f"""
You are a financial analyst AI.

Given multiple finance-related news articles, return a JSON array where each element corresponds to one article with the following format:

{{
  "title": "...",
  "entity": "Most important stock, company, or institution mentioned",
  "insights": [
    "Top 5 insights from the article",
    "Strictly based on content",
    "No guesses or fabrications"
  ]
}}

Here are the articles:
\"\"\"
{article_blocks}
\"\"\"
"""

def summarize_multiple_articles(article_blocks):
    prompt = build_multi_article_summary_prompt(article_blocks)
    response = model.generate_content(prompt)
    return response.text

# === NEW: Insight Generator from news + time-series ===
def build_insight_prompt(article_blocks, time_series_json):
    return f"""
You are a world-class financial analyst with access to intraday market data and live news feeds.

Your task is to analyze a user's investment portfolio based on two types of input:
1. A collection of relevant news articles that mention or impact their portfolio holdings
2. A time-series table showing intraday price movements of their portfolio stocks

Your job is to return the most important logical and evidence-based insights that explain the stock movements, market trends, or events relevant to this user.

Instructions:
- Rely only on factual content from the articles
- Make connections that are direct or indirect, but always logically sound
- If there's no evidence for an insight, say nothing
- Reference articles or stock tickers directly when making claims

Return your output as a JSON object with this format:

{{
  "insights": [
    {{
      "ticker": "AAPL",
      "insight": "Apple's stock rose 2.5% after positive earnings coverage in multiple articles",
      "support": "Article titled 'Apple Beats Expectations' published at 10:45AM discussed strong iPhone sales",
      "correlation_type": "direct"
    }},
    ...
  ]
}}

Here is the time series data:
\"\"\"
{time_series_json}
\"\"\"

Here are the news articles:
\"\"\"
{article_blocks}
\"\"\"
"""


def get_insights_from_news_and_prices(article_blocks, time_series_json):
    prompt = build_insight_prompt(article_blocks, time_series_json)
    response = model.generate_content(prompt)
    return response.text

# === NEW: End-of-Day Market Summary ===
def build_eod_summary_prompt(insights_json, summarized_articles):
    return f"""
You're a financial news assistant helping a retail investor understand what happened today.

The investor holds a diversified stock portfolio, and you've already identified a list of relevant news articles and insights for them.

Your job is to write an end-of-day summary that is:
- Engaging and professional in tone
- Focused only on the stocks, sectors, or macro factors relevant to the portfolio
- Factual, with no hallucinations
- Split into two clear sections:
    1. Key Market Insights (reasoned takeaways)
    2. Summary of News Articles (short bullet-point summaries of top stories)

Please DO NOT include raw numbers or data dumps unless contextually meaningful.
Use this structure:

---
Key Market Insights
- Insight 1...
- Insight 2...

News That Mattered Today
- "Title 1" — Summary
- "Title 2" — Summary
...

Here are the insights:
{insights_json}

Here are the article summaries:
{summarized_articles}
"""


def get_end_of_day_summary(insights_json, summarized_articles):
    prompt = build_eod_summary_prompt(insights_json, summarized_articles)
    response = model.generate_content(prompt)
    return response.text
