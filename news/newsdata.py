import os
import concurrent.futures
from dotenv import load_dotenv
from core.config import settings

from newsdataapi import NewsDataApiClient
from newsdataapi import newsdataapi_exception
from core.logging import get_logger

load_dotenv()

log = get_logger("log")

BASE_URL = "https://newsdata.io/api/1/news"
_API_TIMEOUT: float = 12.0  # seconds; prevents indefinite hangs on slow/stuck API calls

# --- Fetch today's finance-related news articles ---
def fetch_finance_news_from_newsdataio(language: str = "en", country: str = "us", category: list = ["business"], max_results: int = 50, q: str = "") -> list:
    """Fetch finance news from NewsData.io and return a flat list of article dicts.

    Single call only — free plan max is 50 results/call so pagination is
    unnecessary. A 12-second timeout prevents indefinite hangs on slow requests.
    """
    params = {
        "language": language,
        "country": country,
        "category": category,
        "max_result": max_results,
        "q": q,
    }
    api = NewsDataApiClient(apikey=settings.NEWSDATA_API_KEY)

    def _call() -> list:
        response = api.latest_api(**params)
        return response.get("results") or []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            results = future.result(timeout=_API_TIMEOUT)
        return results[:max_results]
    except concurrent.futures.TimeoutError:
        log.warning(f"NewsData API timed out after {_API_TIMEOUT}s (q={q[:60]})")
        return []
    except newsdataapi_exception.NewsdataException as e:
        log.info(f"Article fetch request failed due to: {e}")
        raise e
    except Exception as e:
        log.info(f"Failed to fetch articles: {e}")
        raise e

# --- Example Usage ---
if __name__ == "__main__":
    news = fetch_finance_news_from_newsdataio(q="NVDA,Nvidia,Semiconductors")
    for i, article in enumerate(news):
        print(f"[{i+1}] {article['title']}\n{article['link']}\n{article['pubDate']}")