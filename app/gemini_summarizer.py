import os
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def build_prompt(article_text):
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

async def generate_news_summary(articles):
    text = "\n".join([f"{a['title']}: {a['content']}" for a in articles])
    prompt = build_prompt(text)
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt)
    return response.text