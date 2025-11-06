# config.py
# [MODIFIED] Combining N-Pattern (vol=1.0) + KC Filter + ATR Stop Loss

CONFIG = {
    # Data parameters
    'symbol': 'BTC/USDT',
    'start_date': '2020-01-01 00:00:00',
    'filter_timeframe': '1d',
    'entry_timeframe': '1h',      # Use 1h for more signals
    'pandas_filter_freq': '1D',
    'pandas_entry_freq': 'h',     # Use 'h' for 1h

    # --- N-Pattern Strategy Parameters ---
    'filter_ma_period': 200,
    'vol_avg_period': 20,
    'vol_multiplier': 1.0, # [CHANGED] Use 1.0 (from 50% win rate test)

    # --- Keltner Channel Filter Parameters ---
    'kc_length': 20,
    'kc_multiplier': 2.0,
    'kc_upper_col_name': 'KC_UPPER_STATIC', # Static name

    # --- [MODIFIED] ATR Stop Loss Parameters (NOW ACTIVE) ---
    'atr_length': 14,
    'atr_col_name': 'ATR_14',
    'atr_sl_multiplier': 3.0,   # SL = Entry - (ATR * 3.0)

    # --- RSI Parameters (Still needed for DataHandler) ---
    'rsi_length': 14,
    'rsi_col_name': 'RSI_14',
    # (These are unused by this strategy but DataHandler calculates them)
    'rsi_overbought_threshold': 70,
    'rsi_buy_threshold': 30,
    'rsi_reset_threshold': 50,

    # --- Portfolio Parameters ---
    'initial_capital': 10000,
    'risk_per_trade_percent': 0.02
}