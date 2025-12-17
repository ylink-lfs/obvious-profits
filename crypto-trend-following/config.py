# config.py
# Meme Coin Momentum Strategy Configuration

import pandas as pd

def to_ms(date_str):
    """Convert date string to milliseconds timestamp."""
    return int(pd.Timestamp(date_str).value // 10**6)

CONFIG = {
    # --- Data Source Paths ---
    # Futures data path (contains contract kline data in zip format)
    'futures_data_path': '../../binance-public-data/test-data/futures/um/daily/klines',
    # Spot data path (for BTC reference)
    'spot_data_path': '../../binance-public-data/test-data/spot/daily/klines',
    
    # --- Backtest Date Range ---
    'backtest_start_date': to_ms('2024-01-01 00:00:00'),
    'backtest_end_date': to_ms('2024-12-31 23:59:59'),
    
    # --- Data Parameters ---
    'timeframe': '1m',  # Primary timeframe for entry/exit
    
    # --- Universe Filters ---
    # Valid quote assets (only pairs ending with these will be included)
    'valid_quote_assets': ['USDT', 'BUSD', 'USDC'],
    # Non-crypto assets to exclude (e.g., gold, silver)
    'excluded_non_crypto': ['XAU', 'XAG'],
    # Stablecoins to exclude (including zombie stablecoins like USTC)
    'excluded_stablecoins': ['USDC', 'TUSD', 'FDUSD', 'BUSD', 'DAI', 'USDD', 'USDP', 'USTC', 'USDE', 'PYUSD', 'EURI'],
    # Index contracts to exclude
    'excluded_indices': ['BTCDOM', 'DEFI', 'FOOTBALL', 'BLUEBIRD'],
    # Low volatility giants to exclude
    'excluded_giants': ['BTC', 'ETH'],
    
    # --- Universe Selection ---
    # Liquidity filter: minimum 24h quote volume in USDT
    'min_24h_quote_volume': 10_000_000,  # 10M USDT minimum turnover
    # Top gainers selection: Top X% of 24h gainers with min/max bounds
    'top_gainers_pct': 0.10,  # Select top 10% of 24h gainers
    'top_gainers_min': 5,     # Minimum number of symbols to select
    'top_gainers_max': 20,    # Maximum number of symbols to select
    'universe_check_interval_minutes': 60,  # Check universe every 60 minutes
    
    # --- Entry Signal Parameters ---
    # System Circuit Breaker (BTC 1h change threshold)
    'btc_hourly_drop_threshold': -0.015,  # -1.5%
    
    # Bollinger Band for Volatility Breakout
    'bb_length': 20,
    'bb_std': 2.0,
    
    # Volume Confirmation
    'volume_ma_length': 20,
    'volume_multiplier': 2.0,
    
    # --- Exit Signal Parameters ---
    # Disaster Stop Loss (hard stop)
    'disaster_stop_pct': 0.04,  # -4%
    
    # Structural Exit - Lowest Low Lookback (can try 30 or 60)
    'structural_exit_lookback': 20,
    
    # Time Stop
    'time_stop_minutes': 45,
    'time_stop_min_profit_pct': 0.015,  # 1.5%
    
    # --- Portfolio / Risk Management ---
    'initial_capital': 2050,
    'position_size_usd': 500,
    'leverage': 1,
    
    # --- Trading Costs ---
    'fee_rate': 0.0005,  # 0.05% per trade
    'slippage_rate': 0.002,  # 0.2% slippage (applied to both buy and sell)
    
    # --- Contract Listing Cache ---
    'listing_cache_file': 'contract_listings.json',
}