"""Data collection module.

Responsible for downloading historical OHLCV data and caching it into SQLite.
"""

from __future__ import annotations

import logging
from typing import Dict

import pandas as pd
import yfinance as yf

from modules.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

REQUIRED_OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def _canonicalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    # yfinance 1.4.0 returns a MultiIndex like (Price, Ticker)
    # Flatten it by keeping only the first level
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # Rename lowercase to title case if needed
    rename_map = {
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'
    }
    df = df.rename(columns=rename_map)
    
    # Keep only OHLCV columns
    ohlcv = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing = [c for c in ohlcv if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {', '.join(missing)}")
    
    return df[ohlcv].copy()


def fetch_stock_data(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Fetch historical OHLCV data for a ticker.

    Steps:
    - Download via yfinance
    - Validate required OHLCV columns
    - Flatten MultiIndex columns if present
    - Drop rows with NaNs in OHLCV columns
    - Save cleaned data into SQLite cache
    - On download failure, load from SQLite cache
    """
    db = DatabaseManager()

    # Create schema on first run. If this fails we still try the cache path.
    try:
        db.init_db()
    except Exception:
        logger.exception("Could not init_db; continuing with best-effort download/cache.")

    try:
        df = yf.download(ticker, period=period, progress=False)
        if df is None or df.empty:
            raise ValueError("yfinance returned an empty DataFrame")

        df = _canonicalize_ohlcv_columns(df)
        df = df.dropna(subset=REQUIRED_OHLCV)
        if df.empty:
            raise ValueError("No rows left after OHLCV NaN cleaning")

        # Ensure datetime index for consistent caching.
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            # Keep original index if conversion fails; save_stock_data will still stringize idx.
            pass

        # Cache: db_manager expects lowercase OHLCV column names.
        df_to_store = df.copy()
        df_to_store.columns = [str(c).lower() for c in df_to_store.columns]
        db.save_stock_data(ticker, df_to_store)

        return df
    except Exception as yerr:
        logger.warning("yfinance fetch failed for %s; falling back to cache. Error: %s", ticker, yerr)
        cached = db.load_stock_data(ticker)
        if cached is None or cached.empty:
            raise RuntimeError(f"Failed to fetch {ticker} from yfinance and no cache is available.") from yerr

        # Normalize cached OHLCV columns back to canonical casing.
        rename_cached = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        cached = cached.rename(columns={k: v for k, v in rename_cached.items() if k in cached.columns})

        cached = _canonicalize_ohlcv_columns(cached)
        cached = cached.dropna(subset=REQUIRED_OHLCV)
        if cached.empty:
            raise RuntimeError(f"Cache loaded for {ticker} but contains no valid OHLCV rows.") from yerr

        return cached


class DataCollector:
    """Collect market data from external providers."""

    def download_data(self, ticker: str = "AAPL", period: str = "5y") -> pd.DataFrame:
        """Download historical data for a ticker (with caching)."""
        return fetch_stock_data(ticker=ticker, period=period)
