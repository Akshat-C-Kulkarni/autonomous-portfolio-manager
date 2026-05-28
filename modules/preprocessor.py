"""Data preprocessing module."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from modules.indicators import get_feature_columns

MODELS_DIR = Path("models")


def save_scaler(scaler: MinMaxScaler, ticker: str) -> None:
    """Persist fitted scaler to disk for reuse."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    scaler_path = MODELS_DIR / f"{ticker}_scaler.pkl"
    joblib.dump(scaler, scaler_path)


def load_scaler(ticker: str):
    """Load scaler from disk if available; otherwise return None."""
    scaler_path = MODELS_DIR / f"{ticker}_scaler.pkl"
    if scaler_path.exists():
        return joblib.load(scaler_path)
    return None


def create_sequences(
    data: np.ndarray, targets: np.ndarray, sequence_length: int
) -> Tuple[np.ndarray, np.ndarray]:
    """Create sliding-window sequences and aligned targets.

    `targets[i]` corresponds to the target for the day right after the final
    day in `data[i-sequence_length:i]`.
    """
    if len(data) != len(targets):
        raise ValueError("data and targets must have the same length")
    if sequence_length <= 0:
        raise ValueError("sequence_length must be > 0")
    if len(data) <= sequence_length:
        return np.empty((0, sequence_length, data.shape[1])), np.empty((0, 2))

    x_list = []
    y_list = []
    for i in range(sequence_length, len(data)):
        x_list.append(data[i - sequence_length : i])
        y_list.append(targets[i])

    return np.array(x_list), np.array(y_list)


def prepare_data(
    df: pd.DataFrame, ticker: str, sequence_length: int = 60
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, MinMaxScaler]:
    """Prepare training/test arrays for sequence models.

    Steps:
    - Keep ML feature columns from indicators.get_feature_columns()
    - Scale features to [0, 1] with MinMaxScaler
    - Build next-day High/Low targets
    - Create time-ordered sequences
    - Split 80/20 without shuffling
    """
    if df is None or df.empty:
        raise ValueError("Input DataFrame is empty.")

    feature_cols = get_feature_columns()
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {', '.join(missing)}")
    if "High" not in df.columns or "Low" not in df.columns:
        raise ValueError("Input DataFrame must contain High and Low columns for targets.")

    # Build aligned dataset: features at day t -> targets at day t+1
    features_df = df[feature_cols].copy()
    targets_df = df[["High", "Low"]].shift(-1)
    aligned = pd.concat([features_df, targets_df.rename(columns={"High": "target_high", "Low": "target_low"})], axis=1)
    aligned = aligned.dropna().copy()

    if len(aligned) <= sequence_length:
        raise ValueError(
            f"Not enough rows ({len(aligned)}) for sequence_length={sequence_length}."
        )

    feature_values = aligned[feature_cols].to_numpy(dtype=float)
    target_values = aligned[["target_high", "target_low"]].to_numpy(dtype=float)

    scaler = load_scaler(ticker)
    if hasattr(scaler, 'n_features_in_') and scaler.n_features_in_ != len(feature_cols):
        scaler = None
    
    if scaler is None:
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_features = scaler.fit_transform(feature_values)
        save_scaler(scaler, ticker)
    else:
        scaled_features = scaler.transform(feature_values)

    x_all, y_all = create_sequences(scaled_features, target_values, sequence_length)
    if len(x_all) == 0:
        raise ValueError("No sequences created; check data length and sequence_length.")

    split_idx = int(len(x_all) * 0.8)
    x_train = x_all[:split_idx]
    y_train = y_all[:split_idx]
    x_test = x_all[split_idx:]
    y_test = y_all[split_idx:]

    return x_train, y_train, x_test, y_test, scaler


class Preprocessor:
    """Prepare model-ready sequences from indicator-enriched market data."""

    def prepare_data(
        self, df: pd.DataFrame, ticker: str, sequence_length: int = 60
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, MinMaxScaler]:
        return prepare_data(df=df, ticker=ticker, sequence_length=sequence_length)

    def create_sequences(
        self, data: np.ndarray, targets: np.ndarray, sequence_length: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        return create_sequences(data=data, targets=targets, sequence_length=sequence_length)

    def save_scaler(self, scaler: MinMaxScaler, ticker: str) -> None:
        save_scaler(scaler=scaler, ticker=ticker)

    def load_scaler(self, ticker: str):
        return load_scaler(ticker=ticker)
