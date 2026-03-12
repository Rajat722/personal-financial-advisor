import concurrent.futures
from dotenv import load_dotenv
from core.config import settings

from newsdataapi import NewsDataApiClient
from newsdataapi import newsdataapi_exception
from core.logging import get_logger

load_dotenv()

log = get_logger("newsdata")

_API_TIMEOUT: float = 12.0  # seconds; prevents indefinite hangs on slow/stuck API calls

# Session-level flag: once primary key hits ApiLimitExceeded, all subsequent calls
# use the fallback key directly without retrying primary.
_primary_exhausted: bool = False


def _is_credit_exhausted(exc: Exception) -> bool:
    """Return True if the NewsData exception is a credit/quota exhaustion error."""
    return "ApiLimitExceeded" in str(exc) or "exceeded your assigned API credits" in str(exc)


def _fetch_with_key(api_key: str, params: dict) -> list:
    """Execute a single NewsData API call with the given key and return results."""
    api = NewsDataApiClient(apikey=api_key)

    def _call() -> list:
        response = api.latest_api(**params)
        return response.get("results") or []

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_call)
        return future.result(timeout=_API_TIMEOUT)


def fetch_finance_news_from_newsdataio(
    language: str = "en",
    country: str = "us",
    category: list = ["business"],
    max_results: int = 50,
    q: str = "",
) -> list:
    """Fetch finance news from NewsData.io and return a flat list of article dicts.

    Single call only — free plan max is 50 results/call so pagination is
    unnecessary. A 12-second timeout prevents indefinite hangs on slow requests.

    Falls back to NEWSDATA_FALLBACK_API_KEY when the primary key hits
    ApiLimitExceeded. Raises RuntimeError if both keys are exhausted.
    """
    global _primary_exhausted

    params = {
        "language": language,
        "country": country,
        "category": category,
        "max_result": max_results,
        "q": q,
    }

    # If primary already exhausted this session, go straight to fallback.
    if not _primary_exhausted:
        try:
            results = _fetch_with_key(settings.NEWSDATA_API_KEY, params)
            return results[:max_results]
        except concurrent.futures.TimeoutError:
            log.warning(f"NewsData API timed out after {_API_TIMEOUT}s (q={q[:60]})")
            return []
        except newsdataapi_exception.NewsdataException as e:
            if _is_credit_exhausted(e):
                log.warning("Primary NewsData key credits exhausted — switching to fallback key.")
                _primary_exhausted = True
                # Fall through to fallback logic below.
            else:
                log.warning(f"NewsData API error (q={q[:60]}): {e}")
                raise
        except Exception as e:
            log.warning(f"Failed to fetch articles (q={q[:60]}): {e}")
            raise

    # Fallback key path.
    if not settings.NEWSDATA_FALLBACK_API_KEY:
        raise RuntimeError(
            "NewsData primary API key credits exhausted and NEWSDATA_FALLBACK_API_KEY is not set."
        )

    try:
        results = _fetch_with_key(settings.NEWSDATA_FALLBACK_API_KEY, params)
        return results[:max_results]
    except concurrent.futures.TimeoutError:
        log.warning(f"NewsData fallback API timed out after {_API_TIMEOUT}s (q={q[:60]})")
        return []
    except newsdataapi_exception.NewsdataException as e:
        if _is_credit_exhausted(e):
            raise RuntimeError("Both NewsData API keys have exhausted their credits.") from e
        log.warning(f"NewsData fallback API error (q={q[:60]}): {e}")
        raise
    except Exception as e:
        log.warning(f"NewsData fallback fetch failed (q={q[:60]}): {e}")
        raise


# --- Example Usage ---
if __name__ == "__main__":
    news = fetch_finance_news_from_newsdataio(q="NVDA,Nvidia,Semiconductors")
    for i, article in enumerate(news):
        print(f"[{i+1}] {article['title']}\n{article['link']}\n{article['pubDate']}")
