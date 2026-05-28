"""Paper trading execution module with SQLite persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from modules.db_manager import DatabaseManager


class PaperTradingEngine:
    """Simple paper trading engine with persistent portfolio state."""

    def __init__(self, initial_cash: float = 100000, db_path: str = "portfolio.db") -> None:
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.holdings: Dict[str, float] = {}
        self.transactions: List[dict] = []
        self._cost_basis: Dict[str, float] = {}
        self._profitable_sells = 0
        self._total_sells = 0

        self.db_manager = DatabaseManager(db_path=db_path)
        self.db_manager.init_db()
        self._load_state_from_db()

    def _load_state_from_db(self) -> None:
        """Rebuild in-memory state from persisted transactions."""
        rows = self.db_manager.get_all_transactions()
        # DB returns DESC; replay in chronological order.
        rows = sorted(rows, key=lambda r: (r.get("transaction_date", ""), r.get("id", 0)))

        if not rows:
            return

        first = rows[0]
        first_portfolio_value = float(first.get("portfolio_value", self.initial_cash))
        first_cash_impact = float(first.get("cash_impact", 0.0))
        # Infer starting cash from first recorded transaction.
        self.initial_cash = first_portfolio_value - first_cash_impact
        self.cash = self.initial_cash

        self.holdings = {}
        self._cost_basis = {}
        self._profitable_sells = 0
        self._total_sells = 0
        self.transactions = []

        for tx in rows:
            self._apply_transaction(tx, persist=False)

    def _apply_transaction(self, tx: dict, persist: bool) -> None:
        """Apply transaction to in-memory state and optionally persist."""
        signal_type = str(tx["signal_type"]).upper()
        ticker = str(tx["ticker"]).upper()
        shares = float(tx["shares"])
        price = float(tx["price"])
        cash_impact = float(tx["cash_impact"])

        if signal_type == "BUY":
            prev_shares = self.holdings.get(ticker, 0.0)
            prev_avg = self._cost_basis.get(ticker, 0.0)
            new_shares = prev_shares + shares
            new_avg = ((prev_shares * prev_avg) + (shares * price)) / new_shares if new_shares > 0 else 0.0
            self.holdings[ticker] = new_shares
            self._cost_basis[ticker] = new_avg
        elif signal_type == "SELL":
            prev_shares = self.holdings.get(ticker, 0.0)
            if prev_shares > 0:
                avg_cost = self._cost_basis.get(ticker, 0.0)
                self._total_sells += 1
                if price > avg_cost:
                    self._profitable_sells += 1
                remaining = max(0.0, prev_shares - shares)
                if remaining == 0:
                    self.holdings.pop(ticker, None)
                    self._cost_basis.pop(ticker, None)
                else:
                    self.holdings[ticker] = remaining
            else:
                # If historical data is inconsistent, skip holdings adjustment.
                pass

        self.cash += cash_impact

        stored = {
            "transaction_date": tx["transaction_date"],
            "ticker": ticker,
            "signal_type": signal_type,
            "price": price,
            "shares": shares,
            "cash_impact": cash_impact,
            "portfolio_value": float(tx.get("portfolio_value", self.cash)),
        }
        self.transactions.append(stored)

        if persist:
            self.db_manager.save_transaction(stored)

    def buy(self, ticker: str, shares: float, price: float) -> bool:
        """Execute a BUY if enough cash is available."""
        ticker = ticker.upper()
        shares = float(shares)
        price = float(price)
        if shares <= 0 or price <= 0:
            return False

        cost = shares * price
        if cost > self.cash:
            return False

        tx = {
            "transaction_date": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "signal_type": "BUY",
            "price": price,
            "shares": shares,
            "cash_impact": -cost,
            "portfolio_value": self.cash - cost,
        }
        self._apply_transaction(tx, persist=True)
        return True

    def sell(self, ticker: str, shares: float, price: float) -> bool:
        """Execute a SELL if enough holdings are available."""
        ticker = ticker.upper()
        shares = float(shares)
        price = float(price)
        if shares <= 0 or price <= 0:
            return False

        owned = self.holdings.get(ticker, 0.0)
        if shares > owned:
            return False

        proceeds = shares * price
        tx = {
            "transaction_date": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "signal_type": "SELL",
            "price": price,
            "shares": shares,
            "cash_impact": proceeds,
            "portfolio_value": self.cash + proceeds,
        }
        self._apply_transaction(tx, persist=True)
        return True

    def get_portfolio_value(self, current_prices: dict) -> float:
        """Return cash + market value of holdings."""
        holdings_value = 0.0
        for ticker, shares in self.holdings.items():
            if ticker in current_prices:
                holdings_value += float(shares) * float(current_prices[ticker])
        return float(self.cash + holdings_value)

    def get_holdings(self) -> dict:
        """Return current holdings (ticker -> shares)."""
        return dict(self.holdings)

    def get_cash(self) -> float:
        """Return current cash balance."""
        return float(self.cash)

    def get_pnl(self, current_prices: dict) -> float:
        """Return portfolio PnL relative to initial cash."""
        return float(self.get_portfolio_value(current_prices) - self.initial_cash)

    def get_win_rate(self) -> float:
        """Return percentage of profitable sell trades."""
        if self._total_sells == 0:
            return 0.0
        return float((self._profitable_sells / self._total_sells) * 100.0)

    def get_transaction_history(self) -> list[dict]:
        """Return all known transactions in chronological order."""
        return list(self.transactions)

    def calculate_shares_to_buy(self, price: float, max_pct_of_cash: float = 0.1) -> int:
        """Return integer shares to buy with at most max_pct_of_cash budget."""
        price = float(price)
        max_pct_of_cash = float(max_pct_of_cash)
        if price <= 0 or max_pct_of_cash <= 0:
            return 0
        budget = self.cash * min(max_pct_of_cash, 1.0)
        return max(0, int(budget // price))

    def reset_portfolio(self) -> None:
        """Reset holdings/cash and clear transaction history from DB."""
        # Persist reset by clearing transaction log.
        with self.db_manager._connect() as conn:
            conn.execute("DELETE FROM transactions")

        self.cash = float(self.initial_cash)
        self.holdings = {}
        self.transactions = []
        self._cost_basis = {}
        self._profitable_sells = 0
        self._total_sells = 0


class TradingEngine(PaperTradingEngine):
    """Compatibility alias for existing imports."""
