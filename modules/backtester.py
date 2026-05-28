"""Backtesting module."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from modules.signal_engine import generate_signal


class Backtester:
    """Backtest strategy signals on historical data."""

    def __init__(self, ticker: str, initial_cash: float = 100000) -> None:
        self.ticker = ticker.upper()
        self.initial_cash = float(initial_cash)

    def run(self, df_with_predictions: pd.DataFrame) -> dict:
        """Simulate trades and return strategy metrics."""
        if df_with_predictions is None or df_with_predictions.empty:
            raise ValueError("df_with_predictions is empty")

        required = {"Close", "predicted_high", "predicted_low"}
        missing = required.difference(df_with_predictions.columns)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

        df = df_with_predictions.copy().dropna(subset=["Close", "predicted_high", "predicted_low"])
        if df.empty:
            raise ValueError("No valid rows after dropping NaNs.")

        cash = self.initial_cash
        holdings = 0
        avg_cost = 0.0
        portfolio_values: list[float] = []
        trades: list[dict[str, Any]] = []

        for idx, row in df.iterrows():
            current_price = float(row["Close"])
            predicted_high = float(row["predicted_high"])
            predicted_low = float(row["predicted_low"])
            signal_payload = generate_signal(current_price, predicted_high, predicted_low)
            signal = signal_payload["signal"]

            # Position sizing: up to 10% of cash per BUY.
            if signal == "BUY":
                max_budget = cash * 0.10
                shares_to_buy = int(max_budget // current_price)
                if shares_to_buy > 0:
                    cost = shares_to_buy * current_price
                    cash -= cost
                    new_holdings = holdings + shares_to_buy
                    avg_cost = ((avg_cost * holdings) + cost) / new_holdings if new_holdings > 0 else 0.0
                    holdings = new_holdings
                    trades.append(
                        {
                            "date": str(idx),
                            "ticker": self.ticker,
                            "signal": "BUY",
                            "price": current_price,
                            "shares": shares_to_buy,
                            "realized_pnl": 0.0,
                        }
                    )
            elif signal == "SELL" and holdings > 0:
                shares_to_sell = holdings
                proceeds = shares_to_sell * current_price
                realized_pnl = (current_price - avg_cost) * shares_to_sell
                cash += proceeds
                holdings = 0
                avg_cost = 0.0
                trades.append(
                    {
                        "date": str(idx),
                        "ticker": self.ticker,
                        "signal": "SELL",
                        "price": current_price,
                        "shares": shares_to_sell,
                        "realized_pnl": realized_pnl,
                    }
                )

            portfolio_values.append(cash + holdings * current_price)

        final_price = float(df["Close"].iloc[-1])
        final_value = cash + holdings * final_price
        total_return = ((final_value - self.initial_cash) / self.initial_cash) * 100.0

        values_series = pd.Series(portfolio_values, dtype=float)
        returns = values_series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()

        buy_hold = self.compare_to_buy_and_hold(df=df, initial_cash=self.initial_cash)

        return {
            "ticker": self.ticker,
            "total_return": float(total_return),
            "sharpe_ratio": float(self.compute_sharpe_ratio(returns)),
            "max_drawdown": float(self.compute_max_drawdown(portfolio_values)),
            "win_rate": float(self.compute_win_rate(trades)),
            "buy_hold_return": float(buy_hold["buy_hold_return"]),
            "num_trades": int(len(trades)),
            "portfolio_values": portfolio_values,
            "trades": trades,
        }

    def compute_sharpe_ratio(self, returns) -> float:
        """Compute annualized Sharpe ratio from periodic returns."""
        if isinstance(returns, list):
            returns = pd.Series(returns, dtype=float)
        returns = pd.Series(returns, dtype=float).dropna()
        if returns.empty:
            return 0.0
        std = float(returns.std(ddof=0))
        if std == 0:
            return 0.0
        mean = float(returns.mean())
        return (mean / std) * math.sqrt(252.0)

    def compute_max_drawdown(self, portfolio_values) -> float:
        """Compute maximum drawdown (%) from portfolio value series."""
        values = np.asarray(portfolio_values, dtype=float)
        if values.size == 0:
            return 0.0
        running_peak = np.maximum.accumulate(values)
        drawdowns = (values - running_peak) / running_peak
        return float(abs(np.min(drawdowns) * 100.0))

    def compute_win_rate(self, trades) -> float:
        """Compute % of profitable SELL trades."""
        sell_trades = [t for t in trades if str(t.get("signal", "")).upper() == "SELL"]
        if not sell_trades:
            return 0.0
        wins = [t for t in sell_trades if float(t.get("realized_pnl", 0.0)) > 0]
        return float((len(wins) / len(sell_trades)) * 100.0)

    def compare_to_buy_and_hold(self, df: pd.DataFrame, initial_cash: float) -> dict:
        """Compare strategy to buy-and-hold over the same period."""
        if df.empty:
            return {"buy_hold_return": 0.0}
        first_close = float(df["Close"].iloc[0])
        last_close = float(df["Close"].iloc[-1])
        if first_close <= 0:
            return {"buy_hold_return": 0.0}
        shares = initial_cash / first_close
        final_value = shares * last_close
        buy_hold_return = ((final_value - initial_cash) / initial_cash) * 100.0
        return {"buy_hold_return": float(buy_hold_return)}
