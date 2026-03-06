import yfinance as yf
import pytz
import pandas as pd

def get_stock_OHLCV_data(tickers: list, interval: str, period: str) -> dict:
    """Download intraday OHLCV data for each ticker and return a dict of DataFrames keyed by ticker."""
    result = {}
    # set timezone
    eastern_tz = pytz.timezone("US/Eastern")
    for ticker in tickers:
        # get intraday OHLCV info for each ticker
        df = yf.download(ticker, interval=interval, period=period, progress=False)

        # convert the recieved timestamp to EST time zone
        df.index = df.index.tz_convert(eastern_tz)
        df = df.between_time("09:30", "16:30")

        # Drop last row if it's not a full interval
        if df.index[-1].time().strftime('%H:%M') != "16:30":
            df = df.iloc[:-1]
        result[ticker] = df

    return result

# --- Format as compact JSON (summary version for LLMs) ---
def format_summary_json(data: dict) -> dict:
    """Return a compact per-ticker summary (open, close, % change, volume) for LLM consumption."""
    summary = {}
    for ticker, df in data.items():
        latest = df.iloc[-1]
        first = df.iloc[0]
        open_price = float(first['Open'])
        close_price = float(latest['Close'])
        change_percent = round(((close_price - open_price) / open_price) * 100, 2)

        summary[ticker] = {
            "open": round(open_price, 2),
            "close": round(close_price, 2),
            "change_percent": change_percent,
            "volume_sum": int(df['Volume'].sum()),
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
            "open": float(row['Open']),
            "high": float(row['High']),
            "low": float(row['Low']),
            "close": float(row['Close']),
            "volume": int(row['Volume'])
            })
    return table

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



