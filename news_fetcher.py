import requests
import os
from datetime import datetime

NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
BASE_URL = "https://newsdata.io/api/1/news"

# --- Fetch today's finance-related news articles ---
def fetch_finance_news(language="en", country="us", category=["business", "top"], max_results=50):
        # "country": country,
        # "from_date": "2025-05-07",
        # "to_date": "2025-05-09",
    params = {
        "apikey": NEWSDATA_API_KEY,
        "language": language,
        "country": country,
        "category": category
    }
# https://newsdata.io/api/1/archive?apikey=pub_859920ef3ed470aa546f31f244cb22283b09b&q=example&language=en&from_date=2023-01-19&to_date=2023-01-25
    articles = []
    while len(articles) < max_results:
        response = requests.get(BASE_URL, params=params)
        # print("Status:", response.status_code)
        # print("Response:", response.text)
        if response.status_code != 200:
            print(f"Failed to fetch articles: {response.status_code}")
            break

        data = response.json()
        # print("data: ", data)
        batch = data.get("results", [])
        if not batch:
            break

        articles.extend(batch)
        
        # Handle NewsData.io pagination using nextPage token
        next_page = data.get("nextPage")
        if not next_page:
            break  # no more pages available

        params["page"] = next_page

        if len(batch) < 10:  # Last page reached
            break
        # print("articles: ", articles)
    return articles[:max_results]

# --- Example Usage ---
if __name__ == "__main__":
    news = fetch_finance_news()
    for i, article in enumerate(news):
        print(f"[{i+1}] {article['title']}\n{article['link']}\n{article['pubDate']}")