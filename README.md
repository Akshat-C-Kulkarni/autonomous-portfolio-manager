# Autonomous Financial Portfolio Manager Agent

Autonomous Financial Portfolio Manager Agent is a Flask-based, end-to-end workflow for market data ingestion, feature engineering, LSTM-based prediction, signal generation, paper trading, and historical backtesting. The project combines data science and backend engineering to provide both model-driven forecasts and actionable portfolio operations through a single dashboard and REST API.

The platform supports semi-autonomous and fully autonomous trading simulation modes using stored models, persistent portfolio state, and technical indicators. It is designed for rapid iteration: download fresh data, retrain models, evaluate with backtests, and interact with the strategy in a modern browser dashboard.

## Tech Stack

- Python 3.10+
- Flask (REST API + templated frontend)
- TensorFlow/Keras (LSTM model training/inference)
- pandas, NumPy, scikit-learn (data processing + scaling)
- pandas_ta (technical indicators)
- SQLite (persistent data/portfolio state)
- Plotly.js + Bootstrap 5 + vanilla JavaScript (dashboard UI)
- python-dotenv (environment-based configuration)

## Setup Instructions

```bash
git clone <your-repo-url>
cd autonomous-portfolio-manager
pip install -r requirements.txt
python scripts/download_data.py
python scripts/train_model.py
python app.py
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Serves the main dashboard page |
| GET | `/api/predict/<ticker>` | Returns latest predicted high/low, signal, confidence |
| GET | `/api/indicators/<ticker>` | Returns latest technical indicator snapshot |
| GET | `/api/chart/<ticker>` | Returns chart-ready OHLCV + overlays for last ~180 rows |
| GET | `/api/portfolio` | Returns current paper portfolio stats and last 20 transactions |
| POST | `/api/trade` | Executes paper BUY/SELL trade |
| POST | `/api/reset` | Resets paper portfolio to initial state |
| GET | `/api/backtest/<ticker>` | Runs historical model-based backtest and returns metrics |

## Screenshots

- Dashboard overview: `docs/screenshots/dashboard-overview.png` (placeholder)
- Prediction + chart view: `docs/screenshots/prediction-chart.png` (placeholder)
- Portfolio + transaction history: `docs/screenshots/portfolio-history.png` (placeholder)
- Backtesting results card: `docs/screenshots/backtest-results.png` (placeholder)

## Team Credits

- Akshat C Kulkarni — 245323748069
- Thumula Bhuvan Sai — 245323748119
- Srujan Sandarkari — 245323748114

Internal Guide: Mr. M. Manohar Rao, Assistant Professor  
Institution: Neil Gogte Institute of Technology, Hyderabad
