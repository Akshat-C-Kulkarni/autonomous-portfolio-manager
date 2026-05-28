"""LSTM model module."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.metrics import mean_absolute_error, mean_squared_error
from tensorflow.keras.callbacks import EarlyStopping

MODELS_DIR = Path("models")


def build_model(input_shape: tuple[int, int]) -> tf.keras.Model:
    """Build and compile the portfolio prediction LSTM model."""
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=input_shape),
            tf.keras.layers.LSTM(64, return_sequences=True),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(32, return_sequences=False),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(2, activation="linear"),
        ]
    )
    model.compile(optimizer=tf.keras.optimizers.Adam(), loss="mse", metrics=["mae"])
    return model


def train_model(
    model: tf.keras.Model,
    x_train: np.ndarray,
    y_train: np.ndarray,
    epochs: int = 50,
    batch_size: int = 32,
) -> tf.keras.Model:
    """Train model with early stopping and return trained model."""
    early_stopping = EarlyStopping(
        monitor="val_loss",
        patience=10,
        restore_best_weights=True,
    )
    model.fit(
        x_train,
        y_train,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=0.1,
        callbacks=[early_stopping],
        verbose=0,
    )
    return model


def save_model(model: tf.keras.Model, ticker: str) -> None:
    """Save model to models/{ticker}_lstm.h5."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"{ticker}_lstm.h5"
    model.save(model_path)


def load_model_for_ticker(ticker: str):
    """Load model for ticker from disk if available."""
    model_path = MODELS_DIR / f"{ticker}_lstm.h5"
    if not model_path.exists():
        return None
    return tf.keras.models.load_model(model_path)


def predict(model: tf.keras.Model, x_last_sequence: np.ndarray) -> list[float]:
    """Predict next-day high/low from one sequence or a batch."""
    arr = np.asarray(x_last_sequence)
    if arr.ndim == 2:
        arr = np.expand_dims(arr, axis=0)
    if arr.ndim != 3:
        raise ValueError("X_last_sequence must be shape (seq_len, features) or (n, seq_len, features).")

    preds = model.predict(arr, verbose=0)
    first_pred = preds[0]
    return [float(first_pred[0]), float(first_pred[1])]


def evaluate_model(model: tf.keras.Model, x_test: np.ndarray, y_test: np.ndarray) -> dict:
    """Evaluate model and return MAPE, RMSE, and MAE."""
    y_pred = model.predict(x_test, verbose=0)
    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(math.sqrt(mean_squared_error(y_test, y_pred)))

    # Safe MAPE: ignore zero denominators.
    denom = np.where(np.abs(y_test) < 1e-8, np.nan, y_test)
    mape = np.nanmean(np.abs((y_test - y_pred) / denom)) * 100.0
    mape_value = float(mape) if not np.isnan(mape) else float("inf")

    return {"MAPE": mape_value, "RMSE": rmse, "MAE": mae}


class LSTMModel:
    """Backwards-compatible wrapper around module-level LSTM utilities."""

    def build_model(self, input_shape: tuple[int, int]) -> tf.keras.Model:
        return build_model(input_shape=input_shape)

    def train_model(
        self,
        model: tf.keras.Model,
        x_train: np.ndarray,
        y_train: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
    ) -> tf.keras.Model:
        return train_model(
            model=model,
            x_train=x_train,
            y_train=y_train,
            epochs=epochs,
            batch_size=batch_size,
        )

    def save_model(self, model: tf.keras.Model, ticker: str) -> None:
        save_model(model=model, ticker=ticker)

    def load_model_for_ticker(self, ticker: str):
        return load_model_for_ticker(ticker=ticker)

    def predict(self, model: tf.keras.Model, x_last_sequence: np.ndarray) -> list[float]:
        return predict(model=model, x_last_sequence=x_last_sequence)

    def evaluate_model(self, model: tf.keras.Model, x_test: np.ndarray, y_test: np.ndarray) -> dict:
        return evaluate_model(model=model, x_test=x_test, y_test=y_test)
