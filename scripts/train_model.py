from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

"""Train and persist LSTM models for a default ticker list."""

from modules.data_collector import fetch_stock_data
from modules.indicators import compute_indicators
from modules.lstm_model import build_model, evaluate_model, save_model, train_model
from modules.preprocessor import prepare_data, save_scaler


def main() -> None:
    tickers = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", 
        "NVDA", "NFLX", "AMD", "INTC", "JPM", "BAC", "GS", 
        "MS", "WFC", "V", "MA", "PYPL", "SQ", "COIN",
        "JNJ", "PFE", "MRK", "ABBV", "UNH", "CVS", "AMGN", 
        "GILD", "BMY", "LLY", "XOM", "CVX", "COP", "SLB", 
        "NEE", "WMT", "TGT", "COST", "HD", "LOW", 
        "MCD", "SBUX", "NKE", "DIS", "IBM"
    ]
    total = len(tickers)

    for idx, ticker in enumerate(tickers, start=1):
        print(f"\n[{idx}/{total}] Training pipeline for {ticker}...", flush=True)
        try:
            raw_df = fetch_stock_data(ticker=ticker, period="5y")
            feat_df = compute_indicators(raw_df)
            x_train, y_train, x_test, y_test, scaler = prepare_data(
                df=feat_df, ticker=ticker, sequence_length=60
            )

            input_shape = (x_train.shape[1], x_train.shape[2])
            model = build_model(input_shape=input_shape)
            model = train_model(model=model, x_train=x_train, y_train=y_train)

            save_model(model=model, ticker=ticker)
            save_scaler(scaler=scaler, ticker=ticker)

            metrics = evaluate_model(model=model, x_test=x_test, y_test=y_test)
            print(
                (
                    f"{ticker} | "
                    f"MAPE: {metrics['MAPE']:.4f}% | "
                    f"RMSE: {metrics['RMSE']:.4f} | "
                    f"MAE: {metrics['MAE']:.4f}"
                ),
                flush=True,
            )
        except Exception as exc:
            print(f"{ticker} | ERROR: {exc}", flush=True)


if __name__ == "__main__":
    main()
