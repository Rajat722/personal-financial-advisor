from dotenv import load_dotenv
import google.generativeai as genai
import os
load_dotenv()
# === SETUP ===
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

model = genai.GenerativeModel("models/gemini-1.5-pro")

# === CREATE PROMPT ===
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

# === CALL GEMINI ===
def summarize_article(article_text):
    prompt = build_prompt(article_text)
    response = model.generate_content(prompt)
    return response.text
