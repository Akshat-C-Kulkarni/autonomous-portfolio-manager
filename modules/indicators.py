"""Technical indicator calculation module."""

from __future__ import annotations

import pandas as pd
import ta
from ta.trend import SMAIndicator, EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange

REQUIRED_OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def get_feature_columns() -> list[str]:
    """Return the model feature columns used by downstream ML pipeline."""
    return [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "SMA_20",
        "SMA_50",
        "EMA_20",
        "RSI_14",
        "MACD_12_26_9",
        "BBU_20_2.0",
        "BBL_20_2.0",
        "ATRr_14",
        "ADX_14",
    ]


def _validate_input(df: pd.DataFrame) -> None:
    """Validate required OHLCV columns."""
    missing = [col for col in REQUIRED_OHLCV if col not in df.columns]

    if missing:
        raise ValueError(
            f"Missing required OHLCV columns: {', '.join(missing)}"
        )


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and append technical indicators.

    Indicators:
    - SMA_20, SMA_50, SMA_200
    - EMA_20
    - RSI_14
    - MACD_12_26_9
    - MACD_Signal_12_26_9
    - BBU_20_2.0
    - BBL_20_2.0
    - ATRr_14
    - ADX_14
    """

    if df is None or df.empty:
        return pd.DataFrame()

    _validate_input(df)

    data = df.copy()

    # Ensure numeric dtype
    for col in REQUIRED_OHLCV:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    # =========================
    # Moving Averages
    # =========================

    data["SMA_20"] = SMAIndicator(
        close=data["Close"],
        window=20
    ).sma_indicator()

    data["SMA_50"] = SMAIndicator(
        close=data["Close"],
        window=50
    ).sma_indicator()

    data["SMA_200"] = SMAIndicator(
        close=data["Close"],
        window=200
    ).sma_indicator()

    data["EMA_20"] = EMAIndicator(
        close=data["Close"],
        window=20
    ).ema_indicator()

    # =========================
    # RSI
    # =========================

    data["RSI_14"] = RSIIndicator(
        close=data["Close"],
        window=14
    ).rsi()

    # =========================
    # MACD
    # =========================

    macd = MACD(
        close=data["Close"],
        window_fast=12,
        window_slow=26,
        window_sign=9
    )

    data["MACD_12_26_9"] = macd.macd()
    data["MACD_Signal_12_26_9"] = macd.macd_signal()

    # =========================
    # Bollinger Bands
    # =========================

    bb = BollingerBands(
        close=data["Close"],
        window=20,
        window_dev=2
    )

    data["BBU_20_2.0"] = bb.bollinger_hband()
    data["BBL_20_2.0"] = bb.bollinger_lband()

    # =========================
    # ATR
    # =========================

    atr = AverageTrueRange(
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        window=14
    )

    data["ATRr_14"] = (
        atr.average_true_range() / data["Close"]
    ) * 100

    # =========================
    # ADX
    # =========================

    adx = ADXIndicator(
        high=data["High"],
        low=data["Low"],
        close=data["Close"],
        window=14
    )

    data["ADX_14"] = adx.adx()

    # Remove invalid rows generated during rolling calculations
    data = data.dropna().copy()

    return data


class IndicatorEngine:
    """Compute technical indicators from price data."""

    def add_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Backwards-compatible wrapper around compute_indicators."""
        return compute_indicators(data)