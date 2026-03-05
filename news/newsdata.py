import requests
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from newsdataapi import NewsDataApiClient
from newsdataapi import newsdataapi_exception
from core.logging import get_logger

log = get_logger("log")

NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
BASE_URL = "https://newsdata.io/api/1/news"

# --- Fetch today's finance-related news articles ---
def fetch_finance_news_from_newsdataio(language="en", country="us", category=["business"], max_results=50, q: str=""):
        # from and to date not available in free plan, response = api.archive_api(**params)
        # "from_date": "2025-08-06",
        # "to_date": "2025-08-07"
    params = {
        "language": language,
        "country": country,
        "category": category,
        "max_result": max_results,
        "q":q
        }
    api = NewsDataApiClient(apikey=NEWSDATA_API_KEY)
# https://newsdata.io/api/1/archive?apikey=pub_859920ef3ed470aa546f31f244cb22283b09b&q=example&language=en&from_date=2023-01-19&to_date=2023-01-25
    
    articles = []
    # response={}
    while len(articles) < max_results:
        try:
            response = api.news_api(**params)
            data = response["results"]
            # information to collect from response: sourceUrl
            batch = data if data else []
            if not batch:
                break

            articles.extend(batch)
            
            # Handle NewsData.io pagination using nextPage token
            next_page = response["nextPage"]
            if not next_page:
                break  # no more pages available

            params["page"] = next_page

            if len(batch) < 10:  # Last page reached
                break
            # print("articles: ", articles)
            return articles[:max_results]
        except newsdataapi_exception.NewsdataException as e:
            log.info(f"Article fetch request failed due to:{e}")
            raise e
        except Exception as e:
            log.info(f"Failed to fetch articles: {e}")
            raise e

# --- Example Usage ---
if __name__ == "__main__":
    news = fetch_finance_news_from_newsdataio(q="NVDA,Nvidia,Semiconductors")
    for i, article in enumerate(news):
        print(f"[{i+1}] {article['title']}\n{article['link']}\n{article['pubDate']}")