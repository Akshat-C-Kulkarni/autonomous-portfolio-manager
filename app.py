"""Flask entrypoint for the Autonomous Financial Portfolio Manager Agent."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory, session, redirect, url_for
import hashlib
import secrets
from dotenv import load_dotenv

from modules.data_collector import fetch_stock_data
from modules.backtester import Backtester
from modules.db_manager import DatabaseManager
from modules.indicators import compute_indicators, get_feature_columns
from modules.lstm_model import load_model_for_ticker, predict as predict_next
from modules.preprocessor import load_scaler, prepare_data
from modules.signal_engine import generate_signal
from modules.trading_engine import PaperTradingEngine

load_dotenv()

app = Flask(__name__)
app.config["ENV"] = os.getenv("FLASK_ENV", "production")
app.config["DEBUG"] = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

# Session secret
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False

logger = logging.getLogger(__name__)

db_manager = DatabaseManager("portfolio.db")
db_manager.init_db()
_user_engines = {}

def get_user_engine(user_id: int) -> PaperTradingEngine:
    if user_id not in _user_engines:
        _user_engines[user_id] = PaperTradingEngine(
            initial_cash=100000, 
            db_path="portfolio.db",
            user_id=user_id
        )
    return _user_engines[user_id]

# Price cache
_price_cache: dict[str, float] = {}
_price_cache_time: dict[str, float] = {}
PRICE_CACHE_TTL = 60  # seconds

# Model cache to avoid reloading TensorFlow models repeatedly
_model_cache: dict[str, Any] = {}


def _latest_price(ticker: str) -> float:
    """Return latest close price for a ticker."""
    df = fetch_stock_data(ticker=ticker, period="1mo")
    if df.empty:
        raise ValueError(f"No recent price data for {ticker}")
    return float(df["Close"].iloc[-1])


def get_cached_price(ticker: str) -> float | None:
    """Get price for ticker with caching (TTL 60 seconds).
    
    Returns cached price if fresh, fetches new price otherwise.
    On exception, returns last cached price if available, else None.
    """
    import time
    
    current_time = time.time()
    
    # Return cached price if still fresh
    if ticker in _price_cache and ticker in _price_cache_time:
        if current_time - _price_cache_time[ticker] < PRICE_CACHE_TTL:
            return _price_cache[ticker]
    
    # Fetch new price
    try:
        price = _latest_price(ticker)
        _price_cache[ticker] = price
        _price_cache_time[ticker] = current_time
        return price
    except Exception:
        # Return last cached price if available
        if ticker in _price_cache:
            return _price_cache[ticker]
        return None


def _json_error(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user_id() -> int | None:
    return session.get("user_id")


def require_login():
    if not get_current_user_id():
        raise ApiError("Not logged in", 401)
    return get_current_user_id()


class ApiError(Exception):
    """Application-level API error with HTTP status code."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _validated_ticker(ticker: str) -> str:
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        raise ApiError("Ticker is required", 400)
    return ticker


@app.errorhandler(ApiError)
def handle_api_error(err: ApiError):
    return _json_error(err.message, err.status_code)


@app.errorhandler(ValueError)
def handle_value_error(err: ValueError):
    return _json_error(str(err), 400)


@app.errorhandler(404)
def handle_not_found(_err):
    if request.path.startswith("/api/"):
        return _json_error("Resource not found", 404)
    return _err


@app.errorhandler(Exception)
def handle_unexpected_error(_err):
    if request.path.startswith("/api/"):
        return _json_error("Internal server error", 500)
    return _err


@app.route("/", methods=["GET"])
def index():
    """Serve main dashboard or redirect to login when unauthenticated."""
    if not get_current_user_id():
        return redirect(url_for("login_page"))
    return render_template("index.html")


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route("/signup", methods=["GET"])
def signup_page():
    return render_template("signup.html")


@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@app.route("/api/auth/signup", methods=["POST"])
def api_signup():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", "")).strip()
    tickers = body.get("tickers", [])
    if not username or not password:
        raise ApiError("Username and password are required", 400)
    if len(password) < 6:
        raise ApiError("Password must be at least 6 characters", 400)
    if not tickers:
        raise ApiError("Select at least one stock", 400)
    existing = db_manager.get_user_by_username(username)
    if existing:
        raise ApiError("Username already taken", 409)
    user_id = db_manager.create_user(username, hash_password(password))
    db_manager.save_user_stocks(user_id, tickers)
    session["user_id"] = user_id
    session["username"] = username
    return jsonify({"success": True, "username": username, "redirect": "/"})


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", "")).strip()
    if not username or not password:
        raise ApiError("Username and password are required", 400)
    user = db_manager.get_user_by_username(username)
    if not user or user["password_hash"] != hash_password(password):
        raise ApiError("Invalid username or password", 401)
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    print(f"DEBUG login success - session set to: user_id={user['id']} username={username}")
    return jsonify({"success": True, "username": username, "redirect": "/"})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    user_id = get_current_user_id()
    if user_id and user_id in _user_engines:
        del _user_engines[user_id]
    session.clear()
    return jsonify({"success": True, "redirect": "/login"})


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    print(f"DEBUG /api/auth/me - session contents: {dict(session)}")
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"logged_in": False})
    user = db_manager.get_user_by_id(user_id)
    stocks = db_manager.get_user_stocks(user_id)
    return jsonify({"logged_in": True, "username": user["username"], "stocks": stocks})


@app.route("/api/portfolio/stocks", methods=["GET"])
def api_get_portfolio_stocks():
    user_id = require_login()
    return jsonify({"stocks": db_manager.get_user_stocks(user_id)})


@app.route("/api/portfolio/stocks", methods=["POST"])
def api_update_portfolio_stocks():
    user_id = require_login()
    body = request.get_json(silent=True) or {}
    tickers = body.get("tickers", [])
    if not tickers:
        raise ApiError("At least one ticker required", 400)
    db_manager.save_user_stocks(user_id, tickers)
    return jsonify({"success": True, "stocks": tickers})


@app.route("/api/predict/<ticker>", methods=["GET"])
def api_predict(ticker: str):
    """Run inference for ticker and return predicted bounds with signal."""
    ticker = _validated_ticker(ticker)
    if ticker not in _model_cache:
        _model_cache[ticker] = load_model_for_ticker(ticker)
    model = _model_cache[ticker]
    scaler = load_scaler(ticker)
    if model is None or scaler is None:
        raise ApiError("Model not trained for ticker", 404)

    raw_df = fetch_stock_data(ticker=ticker, period="5y")
    feature_df = compute_indicators(raw_df)
    if feature_df.empty:
        raise ApiError("Not enough data to compute indicators", 404)

    feature_cols = get_feature_columns()
    latest_features = feature_df[feature_cols].tail(60)
    if len(latest_features) < 60:
        raise ApiError("Not enough sequence data for prediction", 400)

    scaled = scaler.transform(latest_features.to_numpy(dtype=float))
    if (scaled == 0.0).any() or (scaled == 1.0).any():
        logger.warning("Scaler out-of-range values detected for %s — predictions may be degraded. Consider retraining.", ticker)
    
    predicted_high, predicted_low = predict_next(model, scaled)
    current_price = float(feature_df["Close"].iloc[-1])
    signal_payload = generate_signal(
        current_price=current_price,
        predicted_high=predicted_high,
        predicted_low=predicted_low,
    )

    payload = {
        "ticker": ticker,
        "predicted_high": signal_payload["predicted_high"],
        "predicted_low": signal_payload["predicted_low"],
        "current_price": signal_payload["current_price"],
        "signal": signal_payload["signal"],
        "confidence": signal_payload["confidence"],
        "days_ahead": 5,
    }
    return jsonify(payload)


@app.route("/api/indicators/<ticker>", methods=["GET"])
def api_indicators(ticker: str):
    """Return latest indicator snapshot for ticker."""
    ticker = _validated_ticker(ticker)
    raw_df = fetch_stock_data(ticker=ticker, period="1y")
    data = compute_indicators(raw_df)
    if data.empty:
        raise ApiError("No indicator data available", 404)

    latest = data.iloc[-1]
    payload = {
        "ticker": ticker,
        "current_price": float(latest["Close"]),
        "SMA_20": float(latest["SMA_20"]),
        "SMA_50": float(latest["SMA_50"]),
        "EMA_20": float(latest["EMA_20"]),
        "RSI": float(latest["RSI_14"]),
        "MACD": float(latest["MACD_12_26_9"]),
        "BB_upper": float(latest["BBU_20_2.0"]),
        "BB_lower": float(latest["BBL_20_2.0"]),
        "ADX": float(latest["ADX_14"]),
    }
    return jsonify(payload)


@app.route("/api/portfolio", methods=["GET"])
def api_portfolio():
    """Return current paper portfolio state."""
    user_id = require_login()
    trading_engine = get_user_engine(user_id)
    print(f"DEBUG portfolio: cash={trading_engine.get_cash()}, holdings={trading_engine.get_holdings()}, transactions={len(trading_engine.get_transaction_history())}")
    print(f"DEBUG portfolio check: engine id={id(trading_engine)}, cash={trading_engine.get_cash()}")
    holdings = trading_engine.get_holdings()
    
    # Build fallback prices from transaction history (most recent first)
    fallback_prices: dict[str, float] = {}
    for tx in reversed(trading_engine.get_transaction_history()):
        t = tx.get("ticker")
        if t and t not in fallback_prices:
            fallback_prices[t] = float(tx.get("price", 0))
    
    current_prices: dict[str, float] = {}
    for ticker in holdings:
        current_prices[ticker] = get_cached_price(ticker) or fallback_prices.get(ticker, 0)

    total_value = trading_engine.get_portfolio_value(current_prices)
    pnl = trading_engine.get_pnl(current_prices)
    history = trading_engine.get_transaction_history()
    # Return last 20, newest first
    history_reversed = list(reversed(history))[:20]

    return jsonify({
        "cash": round(trading_engine.get_cash(), 4),
        "holdings": holdings,
        "total_value": round(float(total_value), 4),
        "pnl": round(float(pnl), 4),
        "win_rate": round(float(trading_engine.get_win_rate()), 4),
        "transactions": history_reversed,
    })


@app.route("/api/status", methods=["GET"])
def api_status():
    """Return database status and statistics."""
    try:
        user_id = get_current_user_id()
        if user_id:
            engine = get_user_engine(user_id)
            txs = engine.get_transaction_history()
            num_positions = len(engine.get_holdings())
            fallback_prices = {}
            for tx in reversed(txs):
                t = tx.get("ticker")
                if t and t not in fallback_prices:
                    fallback_prices[t] = float(tx.get("price", 0))
            portfolio_value = engine.get_portfolio_value(fallback_prices)
        else:
            txs = []
            num_positions = 0
            portfolio_value = 0.0

        return jsonify({
            "db": "connected",
            "transaction_count": len(txs),
            "positions": num_positions,
            "portfolio_value": portfolio_value
        })
    except Exception as e:
        return jsonify({"db": "error", "message": str(e)}), 500


@app.route("/api/trade", methods=["POST"])
def api_trade():
    """Execute BUY/SELL trade on paper portfolio."""
    user_id = require_login()
    trading_engine = get_user_engine(user_id)
    body = request.get_json(silent=True) or {}
    ticker = _validated_ticker(body.get("ticker", ""))
    signal_type = str(body.get("signal_type", "")).upper()
    price = float(body.get("price", 0))
    shares = float(body.get("shares", 0))

    if signal_type not in {"BUY", "SELL"}:
        raise ApiError("signal_type must be BUY or SELL", 400)
    if price <= 0:
        raise ApiError("price must be positive", 400)

    shares = max(1.0, shares)

    if signal_type == "BUY":
        available_cash = trading_engine.get_cash()
        if available_cash < price:
            return jsonify({
                "success": False,
                "updated_cash": round(available_cash, 2),
                "updated_holdings": trading_engine.get_holdings(),
                "message": f"Insufficient cash. Have ${available_cash:.2f}, need ${price:.2f} for 1 share."
            })
        max_shares = int(available_cash * 0.10 / price)
        shares = max(1, min(int(shares), max_shares if max_shares > 0 else 1))
        success = trading_engine.buy(ticker=ticker, shares=shares, price=price)
    else:
        held = trading_engine.get_holdings().get(ticker, 0)
        if held <= 0:
            return jsonify({
                "success": False,
                "updated_cash": round(trading_engine.get_cash(), 2),
                "updated_holdings": trading_engine.get_holdings(),
                "message": f"Auto-trade skipped: No {ticker} shares held to sell. Wait for a BUY signal first."
            })
        shares = min(int(shares), int(held))
        success = trading_engine.sell(ticker=ticker, shares=shares, price=price)

    message = "Trade executed successfully" if success else "Trade failed"
    return jsonify({
        "success": bool(success),
        "updated_cash": round(trading_engine.get_cash(), 4),
        "updated_holdings": trading_engine.get_holdings(),
        "message": message
    })


@app.route("/api/chart/<ticker>", methods=["GET"])
def api_chart(ticker: str):
    """Return chart-ready OHLCV + indicator arrays for Plotly."""
    ticker = _validated_ticker(ticker)
    raw_df = fetch_stock_data(ticker=ticker, period="1y")
    data = compute_indicators(raw_df)
    if data.empty:
        raise ApiError("No chart data available", 404)

    chart_df = data.tail(180).copy()
    chart_df = chart_df.replace([np.inf, -np.inf], np.nan).dropna()
    if chart_df.empty:
        raise ApiError("No valid chart rows after cleaning", 404)

    payload = {
        "ticker": ticker,
        "dates": [str(idx.date()) for idx in chart_df.index],
        "open": chart_df["Open"].astype(float).tolist(),
        "high": chart_df["High"].astype(float).tolist(),
        "low": chart_df["Low"].astype(float).tolist(),
        "close": chart_df["Close"].astype(float).tolist(),
        "volume": chart_df["Volume"].astype(float).tolist(),
        "sma_20": chart_df["SMA_20"].astype(float).tolist(),
        "sma_50": chart_df["SMA_50"].astype(float).tolist(),
        "bb_upper": chart_df["BBU_20_2.0"].astype(float).tolist(),
        "bb_lower": chart_df["BBL_20_2.0"].astype(float).tolist(),
    }
    return jsonify(payload)


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset paper trading portfolio to initial state."""
    user_id = require_login()
    trading_engine = get_user_engine(user_id)
    trading_engine.reset_portfolio()
    return jsonify({"success": True, "message": "Portfolio reset successfully"})


@app.route("/api/backtest/<ticker>", methods=["GET"])
def api_backtest(ticker: str):
    """Run historical backtest for ticker using model predictions."""
    ticker = _validated_ticker(ticker)
    if ticker not in _model_cache:
        _model_cache[ticker] = load_model_for_ticker(ticker)
    model = _model_cache[ticker]
    scaler = load_scaler(ticker)
    if model is None or scaler is None:
        raise ApiError("Model not trained for ticker", 404)

    raw_df = fetch_stock_data(ticker=ticker, period="5y")
    feature_df = compute_indicators(raw_df)
    if feature_df.empty:
        raise ApiError("Not enough data to run backtest", 404)

    feature_cols = get_feature_columns()
    if len(feature_df) < 120:
        raise ApiError("Not enough data points for backtest sequences", 400)

    sequence_length = 60
    _, _, x_test, _, _ = prepare_data(df=feature_df, ticker=ticker, sequence_length=sequence_length)
    if len(x_test) == 0:
        raise ApiError("No test sequences available for backtest", 400)

    aligned = feature_df.copy()
    aligned["target_high"] = aligned["High"].shift(-1)
    aligned["target_low"] = aligned["Low"].shift(-1)
    aligned = aligned.dropna(subset=feature_cols + ["target_high", "target_low"])
    seq_dates = [aligned.index[i] for i in range(sequence_length, len(aligned))]
    seq_closes = [float(aligned["Close"].iloc[i]) for i in range(sequence_length, len(aligned))]

    split_idx = int(len(seq_dates) * 0.8)
    test_dates = seq_dates[split_idx:]
    test_closes = seq_closes[split_idx:]

    if len(x_test) != len(test_dates):
        raise ApiError("Sequence length mismatch in backtest alignment", 500)

    pred_rows = []
    for i, seq in enumerate(x_test):
        pred_high, pred_low = predict_next(model, seq)
        pred_rows.append(
            {
                "date": test_dates[i],
                "Close": float(test_closes[i]),
                "predicted_high": float(pred_high),
                "predicted_low": float(pred_low),
            }
        )

    if not pred_rows:
        raise ApiError("No prediction rows generated for backtest", 500)

    pred_df = pd.DataFrame(pred_rows).set_index("date")
    backtester = Backtester(ticker=ticker, initial_cash=100000)
    metrics = backtester.run(pred_df)

    response = {
        "ticker": ticker,
        "total_return": round(float(metrics["total_return"]), 4),
        "sharpe_ratio": round(float(metrics["sharpe_ratio"]), 4),
        "max_drawdown": round(float(metrics["max_drawdown"]), 4),
        "win_rate": round(float(metrics["win_rate"]), 4),
        "buy_hold_return": round(float(metrics["buy_hold_return"]), 4),
        "num_trades": int(metrics["num_trades"]),
    }
    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])
