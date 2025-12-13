# config.py
# [MODIFIED] Added Bollinger Band and ADX Chop parameters

import pandas as pd

def to_ms(date_str):
    return int(pd.Timestamp(date_str).value // 10**6)

CONFIG = {
    # --- Data Parameters ---
    'symbol': 'BTC/USDT',
    'timeframe': '4h', 
    'pandas_freq': '4h',
    
    # --- Train / Test Split ---
    'train_start_date': to_ms('2020-01-01 00:00:00'),
    'train_end_date':   to_ms('2023-12-31 23:59:59'),
    'test_start_date':  to_ms('2024-01-01 00:00:00'),
    'test_end_date':    to_ms('2025-10-31 23:59:59'),

    # --- Strategy Parameters: Mean Reversion (BB) ---
    'bb_length': 20,
    'bb_std': 2.0,
    'bb_lower_col': 'BB_LOWER_STATIC',   # [修改] 使用静态名称
    'bb_middle_col': 'BB_MIDDLE_STATIC', # [修改] 使用静态名称

    # --- Filter Parameters: ADX Chop ---
    'adx_length': 14,
    'adx_col_name': 'ADX_14',
    'adx_chop_threshold': 30, # ADX < 30 means "Choppy Market"

    # --- Risk Management ---
    'atr_length': 14,
    'atr_col_name': 'ATR_14',
    'atr_sl_multiplier': 1.0, # Tighter SL for mean reversion

    # --- Portfolio Parameters ---
    'initial_capital': 10000,
    'risk_per_trade_percent': 0.02,
    
    # --- Unused (Compatibility) ---
    'ma_period': 20, 'ma_col_name': 'MA_20',
    'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9,
    'macd_col_name': 'MACD', 'macd_signal_col_name': 'MACDs',
    'divergence_lookback': 20
}