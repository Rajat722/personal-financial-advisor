import yfinance as yf
import pytz
import pandas as pd
from datetime import date, timedelta
from core.logging import get_logger

_log = get_logger("stock_details")

def get_stock_OHLCV_data(tickers: list, interval: str, period: str) -> dict:
    """Download intraday OHLCV data for each ticker and return a dict of DataFrames keyed by ticker."""
    result = {}
    eastern_tz = pytz.timezone("US/Eastern")
    for ticker in tickers:
        try:
            df = yf.download(ticker, interval=interval, period=period, progress=False)

            if df.empty:
                _log.warning(f"[{ticker}] No data returned — market may be closed or ticker invalid. Skipping.")
                continue

            # Convert timestamp to EST and filter to market hours
            df.index = df.index.tz_convert(eastern_tz)
            df = df.between_time("09:30", "16:30")

            if df.empty:
                _log.warning(f"[{ticker}] No data within market hours (09:30–16:30 ET). Skipping.")
                continue

            # Select the most recent trading date with >1 bar.
            # If the market just opened (only 1 incomplete bar today), fall back to
            # the previous trading day's complete data instead.
            dates = sorted(df.index.normalize().unique(), reverse=True)
            selected = None
            for d in dates:
                day_df = df[df.index.normalize() == d]
                if len(day_df) > 1:
                    selected = day_df
                    break
            if selected is None:
                _log.warning(f"[{ticker}] Only 1 bar available — using it as best-effort.")
                selected = df[df.index.normalize() == dates[0]]
            df = selected

            # Drop the last bar if it's not a full interval (only when >1 bar remain)
            if len(df) > 1 and df.index[-1].time().strftime('%H:%M') != "16:30":
                df = df.iloc[:-1]

            result[ticker] = df
        except Exception as e:
            _log.error(f"[{ticker}] Failed to fetch OHLCV data: {e}")

    return result

# --- Format as compact JSON (summary version for LLMs) ---
def format_summary_json(data: dict) -> dict:
    """Return a compact per-ticker summary (open, close, % change, volume) for LLM consumption."""
    summary = {}
    for ticker, df in data.items():
        latest = df.iloc[-1]
        first = df.iloc[0]
        open_price = float(first['Open'].iloc[0])
        close_price = float(latest['Close'].iloc[0])
        change_percent = round(((close_price - open_price) / open_price) * 100, 2)

        summary[ticker] = {
            "open": round(open_price, 2),
            "close": round(close_price, 2),
            "change_percent": change_percent,
            "volume_sum": int(df['Volume'].values.sum()),
            "intervals": len(df),
        }
    return summary

# --- Format as time-series table (Excel-like) ---
def format_time_series_table(data: dict) -> dict:
    """Return a full per-ticker time-series table with OHLCV rows for LLM prompt input."""
    table = {}
    for ticker, df in data.items():
        table[ticker] = []
        for idx, row in df.iterrows():
            table[ticker].append({
                "time": idx.strftime('%Y-%m-%d %H:%M'),
                "open": float(row['Open'].iloc[0]),
                "high": float(row['High'].iloc[0]),
                "low": float(row['Low'].iloc[0]),
                "close": float(row['Close'].iloc[0]),
                "volume": int(row['Volume'].iloc[0]),
            })
    return table

# --- Upcoming earnings calendar ---
def get_upcoming_earnings(equities: list[dict], days_ahead: int = 14) -> list[dict]:
    """Return upcoming earnings events for portfolio equities within the next days_ahead days.

    Also includes events from the past 3 days (recently reported — still market-relevant).
    Each entry: {ticker, company, date, days_until, eps_avg, eps_low, eps_high, rev_avg}.
    Missing fields default to None. Tickers with no calendar data are silently skipped.
    Results are sorted by earnings date ascending.
    """
    today = date.today()
    lookback = today - timedelta(days=3)
    lookahead = today + timedelta(days=days_ahead)

    events = []
    for equity in equities:
        ticker = equity["ticker"]
        company = equity.get("company", ticker)
        try:
            cal = yf.Ticker(ticker).calendar
            if not cal or not isinstance(cal, dict):
                continue
            dates = cal.get("Earnings Date")
            if not dates:
                continue
            earnings_date = dates[0] if isinstance(dates, list) else dates
            if hasattr(earnings_date, "date"):
                earnings_date = earnings_date.date()
            if not (lookback <= earnings_date <= lookahead):
                continue
            events.append({
                "ticker": ticker,
                "company": company,
                "date": earnings_date.isoformat(),
                "days_until": (earnings_date - today).days,
                "eps_avg": cal.get("Earnings Average"),
                "eps_low": cal.get("Earnings Low"),
                "eps_high": cal.get("Earnings High"),
                "rev_avg": cal.get("Revenue Average"),
            })
        except Exception as e:
            _log.debug(f"[{ticker}] No earnings calendar: {e}")

    return sorted(events, key=lambda x: x["date"])


# --- Run end-to-end example ---
if __name__ == "__main__":
    tickers = ["AAPL", "TSLA"]
    stock_data = get_stock_OHLCV_data(tickers, "30m", "1d")

    summary_output = format_summary_json(stock_data)
    table_output = format_time_series_table(stock_data)

    print("\n--- COMPACT SUMMARY FORMAT ---")
    for ticker, summary in summary_output.items():
        print(f"{ticker}: {summary}")

    print("\n--- FULL TIME-SERIES TABLE FORMAT ---")
    for ticker, rows in table_output.items():
        print(f"\n{ticker}:")
        for row in rows:
            print(row)



