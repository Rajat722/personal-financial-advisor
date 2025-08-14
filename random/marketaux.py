import requests
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY")
BASE_URL = "https://api.marketaux.com/v1/news/all"

def fetch_finance_news_from_marketaux(language="en", country="us", symbols=["TSLA", "MSFT"], max_results=20):
        # "country": country,
        # "from_date": "2025-05-07",
        # "to_date": "2025-05-09",
    params = {
        "api_token": MARKETAUX_API_KEY,
        "language": language,
        "country": country,
        "symbols": symbols,
        "filter_entities": True,
        "limit": 20
    }
    articles = []
    while len(articles) < max_results:
        try:
            response = requests.get(BASE_URL, params=params)
            data = response.json()
            articles.extend(data)
            if data in article:
                break
        except Exception as e:
            logging.info(f"request failed to fetch article no: {len(articles)} due to error: \n {e}")
    return article

if __name__ == "__main__":
    news = fetch_finance_news_from_marketaux()
    for i, article in enumerate(news):
        print(f"[{i+1}] {article['title']}\n{article['link']}\n{article['pubDate']}")