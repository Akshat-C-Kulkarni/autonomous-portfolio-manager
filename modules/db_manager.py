"""Database manager module for portfolio data persistence."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH = Path("portfolio.db")

_DDL = """
CREATE TABLE IF NOT EXISTS stock_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    sma_20      REAL,
    sma_50      REAL,
    rsi         REAL,
    macd        REAL,
    UNIQUE (ticker, date)
);

CREATE TABLE IF NOT EXISTS predictions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    prediction_date  TEXT NOT NULL,
    predicted_high   REAL,
    predicted_low    REAL,
    actual_high      REAL,
    actual_low       REAL,
    accuracy         REAL
);

CREATE TABLE IF NOT EXISTS transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_date TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    signal_type      TEXT NOT NULL,
    price            REAL,
    shares           REAL,
    cash_impact      REAL,
    portfolio_value  REAL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_portfolio_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    UNIQUE(user_id, ticker),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS user_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    transaction_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    price REAL,
    shares REAL,
    cash_impact REAL,
    portfolio_value REAL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""


@contextmanager
def _get_connection(db_path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection with WAL mode and row factory set."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class DatabaseManager:
    """Handle SQLite interactions for portfolio records."""

    def __init__(self, db_path: str = "portfolio.db") -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        with _get_connection(self.db_path) as conn:
            yield conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create all tables if they do not yet exist."""
        try:
            with self._connect() as conn:
                conn.executescript(_DDL)
            logger.info("Database initialised at %s", self.db_path)
        except sqlite3.Error as exc:
            logger.error("init_db failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # stock_history
    # ------------------------------------------------------------------

    def save_stock_data(self, ticker: str, df: pd.DataFrame) -> None:
        """Upsert rows from *df* into stock_history for *ticker*.

        Expected columns (all optional except 'date'):
            date, open, high, low, close, volume,
            sma_20, sma_50, rsi, macd
        """
        if df.empty:
            logger.warning("save_stock_data called with empty DataFrame for %s", ticker)
            return

        rows = []
        for idx, row in df.iterrows():
            date_val = row.get("date", str(idx))
            rows.append(
                (
                    ticker,
                    str(date_val),
                    _f(row, "open"),
                    _f(row, "high"),
                    _f(row, "low"),
                    _f(row, "close"),
                    _f(row, "volume"),
                    _f(row, "sma_20"),
                    _f(row, "sma_50"),
                    _f(row, "rsi"),
                    _f(row, "macd"),
                )
            )

        sql = """
            INSERT INTO stock_history
                (ticker, date, open, high, low, close, volume, sma_20, sma_50, rsi, macd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open    = excluded.open,
                high    = excluded.high,
                low     = excluded.low,
                close   = excluded.close,
                volume  = excluded.volume,
                sma_20  = excluded.sma_20,
                sma_50  = excluded.sma_50,
                rsi     = excluded.rsi,
                macd    = excluded.macd
        """
        try:
            with self._connect() as conn:
                conn.executemany(sql, rows)
            logger.debug("Saved %d rows for %s", len(rows), ticker)
        except sqlite3.Error as exc:
            logger.error("save_stock_data failed for %s: %s", ticker, exc)
            raise

    def load_stock_data(self, ticker: str) -> pd.DataFrame:
        """Return all stock_history rows for *ticker* as a DataFrame."""
        sql = """
            SELECT date, open, high, low, close, volume, sma_20, sma_50, rsi, macd
            FROM stock_history
            WHERE ticker = ?
            ORDER BY date ASC
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(sql, (ticker,))
                rows = cursor.fetchall()
                columns = [col[0] for col in cursor.description]
            
            if not rows:
                return pd.DataFrame()
            
            df = pd.DataFrame(rows, columns=columns)
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            return df
        except sqlite3.Error as exc:
            logger.error("load_stock_data failed for %s: %s", ticker, exc)
            raise

    # ------------------------------------------------------------------
    # predictions
    # ------------------------------------------------------------------

    def save_prediction(self, data: dict) -> None:
        """Insert a prediction record.

        Expected keys: ticker, prediction_date, predicted_high,
        predicted_low, actual_high, actual_low, accuracy
        """
        sql = """
            INSERT INTO predictions
                (ticker, prediction_date, predicted_high, predicted_low,
                 actual_high, actual_low, accuracy)
            VALUES (:ticker, :prediction_date, :predicted_high, :predicted_low,
                    :actual_high, :actual_low, :accuracy)
        """
        try:
            with self._connect() as conn:
                conn.execute(sql, data)
            logger.debug("Prediction saved for %s on %s", data.get("ticker"), data.get("prediction_date"))
        except sqlite3.Error as exc:
            logger.error("save_prediction failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # transactions
    # ------------------------------------------------------------------

    def save_transaction(self, data: dict) -> None:
        """Insert a transaction record.

        Expected keys: transaction_date, ticker, signal_type, price,
        shares, cash_impact, portfolio_value
        """
        sql = """
            INSERT INTO transactions
                (transaction_date, ticker, signal_type, price,
                 shares, cash_impact, portfolio_value)
            VALUES (:transaction_date, :ticker, :signal_type, :price,
                    :shares, :cash_impact, :portfolio_value)
        """
        try:
            with self._connect() as conn:
                conn.execute(sql, data)
            logger.debug(
                "Transaction saved: %s %s @ %s",
                data.get("signal_type"),
                data.get("ticker"),
                data.get("price"),
            )
        except sqlite3.Error as exc:
            logger.error("save_transaction failed: %s", exc)
            raise

    def get_all_transactions(self) -> list[dict]:
        """Return all transaction records ordered by date descending."""
        sql = """
            SELECT id, transaction_date, ticker, signal_type,
                   price, shares, cash_impact, portfolio_value
            FROM transactions
            ORDER BY transaction_date DESC
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(sql).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            logger.error("get_all_transactions failed: %s", exc)
            raise

    def get_portfolio_state(self) -> dict:
        """Return an aggregate summary of the current portfolio.

        Computes per-ticker net shares and average cost from the
        transactions table, plus the latest cash_impact-derived balance.
        """
        sql_positions = """
            SELECT
                ticker,
                SUM(CASE WHEN signal_type = 'BUY'  THEN  shares
                         WHEN signal_type = 'SELL' THEN -shares
                         ELSE 0 END)                          AS net_shares,
                AVG(CASE WHEN signal_type = 'BUY' THEN price END) AS avg_cost
            FROM transactions
            GROUP BY ticker
            HAVING net_shares > 0
        """
        sql_cash = """
            SELECT portfolio_value
            FROM transactions
            ORDER BY transaction_date DESC, id DESC
            LIMIT 1
        """
        try:
            with self._connect() as conn:
                positions_rows = conn.execute(sql_positions).fetchall()
                cash_row = conn.execute(sql_cash).fetchone()

            positions = [dict(r) for r in positions_rows]
            latest_portfolio_value = dict(cash_row)["portfolio_value"] if cash_row else 0.0

            return {
                "positions": positions,
                "portfolio_value": latest_portfolio_value,
            }
        except sqlite3.Error as exc:
            logger.error("get_portfolio_state failed: %s", exc)
            raise

    def delete_all_transactions(self) -> None:
        """Delete all rows from the transactions table."""
        sql = "DELETE FROM transactions"
        try:
            with self._connect() as conn:
                conn.execute(sql)
            logger.debug("All transactions deleted")
        except sqlite3.Error as exc:
            logger.error("delete_all_transactions failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # users + user-specific data
    # ------------------------------------------------------------------

    def create_user(self, username: str, password_hash: str) -> int:
        sql = "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)"
        from datetime import datetime, timezone
        with self._connect() as conn:
            cursor = conn.execute(sql, (username, password_hash, datetime.now(timezone.utc).isoformat()))
            return cursor.lastrowid

    def get_user_by_username(self, username: str) -> dict | None:
        sql = "SELECT id, username, password_hash FROM users WHERE username = ?"
        with self._connect() as conn:
            row = conn.execute(sql, (username,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> dict | None:
        sql = "SELECT id, username FROM users WHERE id = ?"
        with self._connect() as conn:
            row = conn.execute(sql, (user_id,)).fetchone()
        return dict(row) if row else None

    def save_user_stocks(self, user_id: int, tickers: list[str]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM user_portfolio_stocks WHERE user_id = ?", (user_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO user_portfolio_stocks (user_id, ticker) VALUES (?, ?)",
                [(user_id, t.upper()) for t in tickers]
            )

    def get_user_stocks(self, user_id: int) -> list[str]:
        sql = "SELECT ticker FROM user_portfolio_stocks WHERE user_id = ? ORDER BY ticker"
        with self._connect() as conn:
            rows = conn.execute(sql, (user_id,)).fetchall()
        return [r["ticker"] for r in rows]

    def save_user_transaction(self, user_id: int, data: dict) -> None:
        sql = """INSERT INTO user_transactions
            (user_id, transaction_date, ticker, signal_type, price, shares, cash_impact, portfolio_value)
            VALUES (:user_id, :transaction_date, :ticker, :signal_type, :price, :shares, :cash_impact, :portfolio_value)"""
        data["user_id"] = user_id
        with self._connect() as conn:
            conn.execute(sql, data)

    def get_user_transactions(self, user_id: int) -> list[dict]:
        sql = """SELECT * FROM user_transactions 
                 WHERE user_id = ? ORDER BY transaction_date DESC"""
        with self._connect() as conn:
            rows = conn.execute(sql, (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_user_transactions(self, user_id: int) -> None:
        sql = "DELETE FROM user_transactions WHERE user_id = ?"
        with self._connect() as conn:
            conn.execute(sql, (user_id,))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _f(row: "pd.Series", col: str) -> float | None:
    """Safely extract a float from a row, returning None when absent/NaN."""
    val = row.get(col)
    if val is None:
        return None
    try:
        import math
        return None if math.isnan(float(val)) else float(val)
    except (TypeError, ValueError):
        return None
