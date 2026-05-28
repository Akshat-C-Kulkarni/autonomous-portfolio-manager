import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

"""Download stock data for a default ticker list.

This script is intended to be run manually, and will cache results into SQLite.
"""

from modules.data_collector import fetch_stock_data


def main() -> None:
    tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
    period = "5y"

    total = len(tickers)
    for i, ticker in enumerate(tickers, start=1):
        print(f"[{i}/{total}] Fetching {ticker} ({period}) ...", flush=True)
        df = fetch_stock_data(ticker=ticker, period=period)
        print(f"    {ticker}: cached/loaded {len(df)} rows", flush=True)


if __name__ == "__main__":
    main()
