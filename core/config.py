from pydantic import BaseSettings, AnyUrl

class Settings(BaseSettings):
    NEWSDATA_API_KEY: str
    GEMINI_API_KEY: str
    MAILERSEND_API_KEY: str

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
    SIM_THRESHOLD: float = 0.72
    TOP_N: int = 8
    EXACT_TICKER_BOOST: float = 0.05

    # Collections / paths
    CHROMA_DIR: str = ".chroma"
    ARTICLES_COLL: str = "articles"
    RUN_STATE_PATH: str = "state/sent_registry.json"
    METRICS_PATH: str = "state/metrics.jsonl"

    # LLM
    GEMINI_EMBED_MODEL: str = "text-embedding-001"
    GEMINI_SUMMARY_MODEL: str = "gemini-2.0-flash"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 512

    class Config:
        env_file = ".env"

settings = Settings()
