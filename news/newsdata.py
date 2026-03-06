import os
from dotenv import load_dotenv
from core.config import settings

from newsdataapi import NewsDataApiClient
from newsdataapi import newsdataapi_exception
from core.logging import get_logger

load_dotenv()

log = get_logger("log")

BASE_URL = "https://newsdata.io/api/1/news"

# --- Fetch today's finance-related news articles ---
def fetch_finance_news_from_newsdataio(language: str = "en", country: str = "us", category: list = ["business"], max_results: int = 50, q: str = "") -> list:
    """Fetch paginated finance news from NewsData.io and return a flat list of article dicts."""
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
    api = NewsDataApiClient(apikey=settings.NEWSDATA_API_KEY)
# https://newsdata.io/api/1/archive?apikey=pub_859920ef3ed470aa546f31f244cb22283b09b&q=example&language=en&from_date=2023-01-19&to_date=2023-01-25
    
    articles = []
    # response={}
    while len(articles) < max_results:
        try:
            response = api.latest_api(**params)
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
        except newsdataapi_exception.NewsdataException as e:
            log.info(f"Article fetch request failed due to:{e}")
            raise e
        except Exception as e:
            log.info(f"Failed to fetch articles: {e}")
            raise e

    return articles[:max_results]

# --- Example Usage ---
if __name__ == "__main__":
    news = fetch_finance_news_from_newsdataio(q="NVDA,Nvidia,Semiconductors")
    for i, article in enumerate(news):
        print(f"[{i+1}] {article['title']}\n{article['link']}\n{article['pubDate']}")