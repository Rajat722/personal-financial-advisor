from typing import Optional
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment variables and .env file."""

    model_config = ConfigDict(env_file=".env", extra="ignore")

    NEWSDATA_API_KEY: str
    NEWSDATA_FALLBACK_API_KEY: Optional[str] = None  # secondary account key; used when primary credits are exhausted
    GEMINI_API_KEY: str
    GEMINI_FALLBACK_API_KEY: Optional[str] = None    # secondary account key; used when primary credits are exhausted
    MAILERSEND_API_KEY: Optional[str] = None  # required for email delivery; optional for pipeline-only use

    # Fetching
    FETCH_LANGUAGE: str = "en"
    FETCH_PAGE_SIZE: int = 50  # if API supports
    MAX_PAGES: int = 5

    # Windows (ET)
    PRE_START: str = "16:00"
    PRE_END:   str = "09:30"
    POST_START:str = "09:30"
    POST_END:  str = "16:00"
    TZ_MARKET: str = "America/New_York"

    # Relevance
    SIM_THRESHOLD: float = 0.75
    TOP_N: int = 8
    EXACT_TICKER_BOOST: float = 0.05

    # Collections / paths
    CHROMA_DIR: str = ".chroma"
    ARTICLES_COLL: str = "articles"
    RUN_STATE_PATH: str = "state/sent_registry.json"
    METRICS_PATH: str = "state/metrics.jsonl"

    # LLM
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    GEMINI_SUMMARY_MODEL: str = "gemini-2.5-flash-lite"  # kept for backward compat
    GEMINI_EXTRACT_MODEL: str = "gemini-2.5-flash-lite"   # Call 1: factual extraction (fast, cheap)
    GEMINI_EDITORIAL_MODEL: str = "gemini-2.5-flash"      # Call 2: newsletter writing (higher quality)
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 512

    # Gemini retry / rate-limit handling
    GEMINI_RETRY_ATTEMPTS: int = 3
    GEMINI_RETRY_DELAY: float = 1.0  # base delay in seconds (doubles on each retry)

settings = Settings()
