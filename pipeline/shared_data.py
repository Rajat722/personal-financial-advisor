# pipeline/shared_data.py
"""
Shared data fetcher for multi-user pipeline.

Fetches stock OHLCV data and earnings calendar once for all tickers
across all users, caches in memory. Per-user digest generation reads
from this cache instead of making redundant API calls.
"""

from core.logging import get_logger
from utils.stock_details import get_stock_OHLCV_data, format_summary_json, format_time_series_table, get_upcoming_earnings

logger = get_logger("shared_data")


def fetch_shared_stock_data(all_tickers: list[str]) -> dict:
    """Fetch OHLCV data for all tickers across all users. Returns raw dict of DataFrames."""
    logger.info(f"Fetching shared stock data for {len(all_tickers)} tickers: {all_tickers}")
    stock_data = get_stock_OHLCV_data(all_tickers, interval="30m", period="5d")
    logger.info(f"Stock data fetched for {len(stock_data)}/{len(all_tickers)} tickers.")
    return stock_data


def fetch_shared_earnings(master_equities: list[dict]) -> list[dict]:
    """Fetch earnings calendar for all equities across all users."""
    logger.info(f"Fetching shared earnings calendar for {len(master_equities)} tickers...")
    earnings = get_upcoming_earnings(master_equities)
    logger.info(f"Earnings calendar: {len(earnings)} event(s) found.")
    return earnings
