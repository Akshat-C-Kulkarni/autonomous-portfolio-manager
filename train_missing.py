import sys, os
sys.path.insert(0, os.path.abspath('.'))
from modules.data_collector import fetch_stock_data
from modules.indicators import compute_indicators
from modules.lstm_model import build_model, train_model, save_model, evaluate_model
from modules.preprocessor import prepare_data, save_scaler

for ticker in ['MRK', 'JPM']:
    print(f'Training {ticker}...')
    try:
        df = fetch_stock_data(ticker, '5y')
        df = compute_indicators(df)
        X_train, y_train, X_test, y_test, scaler = prepare_data(df, ticker)
        model = build_model((X_train.shape[1], X_train.shape[2]))
        model = train_model(model, X_train, y_train)
        save_model(model, ticker)
        save_scaler(scaler, ticker)
        mape = evaluate_model(model, X_test, y_test)['MAPE']
        print(f'{ticker} done. MAPE: {mape:.2f}%')
    except Exception as e:
        print(f'{ticker} failed: {e}')