# config.py
# [MODIFIED] Reverted to best config (4H, vol=0.0, risk=2.0%)
# [NEW] Added R:R Take Profit parameter

CONFIG = {
    # Data parameters
    'symbol': 'BTC/USDT',
    'start_date': '2020-01-01 00:00:00',
    'filter_timeframe': '1d',
    'entry_timeframe': '4h',
    'pandas_filter_freq': '1D',
    'pandas_entry_freq': '4H',

    # --- Trend Filter ---
    'filter_ma_period': 200,

    # --- N-Pattern Strategy Parameters ---
    'vol_avg_period': 20,
    'vol_multiplier': 0.0, # Keep vol=0.0 (our best strategy)

    # --- [NEW] R:R Take Profit Parameter ---
    'RR_MULTIPLIER': 3.0, # Take Profit at 3x the initial risk

    # --- (Unused parameters, for DataHandler compatibility) ---
    # (These are not used by the strategy but ensures data_handler doesn't crash)
    'rsi_length': 14,
    'rsi_col_name': 'RSI_14',
    'atr_length': 14,
    'atr_col_name': 'ATR_14',

    # --- Portfolio Parameters ---
    'initial_capital': 10000,
    'risk_per_trade_percent': 0.02 # [REVERTED] Back to 2%
}