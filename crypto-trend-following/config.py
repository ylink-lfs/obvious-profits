# config.py
# Meme Coin Momentum Strategy Configuration

import os
import pandas as pd

# Project root directory (where config.py lives)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def to_ms(date_str):
    """Convert date string to milliseconds timestamp."""
    return int(pd.Timestamp(date_str).value // 10**6)

CONFIG = {
    # --- Data Source Paths ---
    # Futures data path (contains contract kline data in zip format)
    'futures_data_path': '../../binance-public-data/python/data/futures/um/daily/klines',
    # Spot data path (for BTC reference)
    'spot_data_path': '../../binance-public-data/python/data/spot/daily/klines',
    
    # --- Backtest Date Range ---
    'backtest_start_date': to_ms('2021-01-01 00:00:00'),
    'backtest_end_date': to_ms('2022-12-31 23:59:59'),
    
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
    'min_24h_quote_volume': 50_000_000,  # 50M USDT - filter out low liquidity coins
    # NATR filter: minimum normalized ATR (daily range / close)
    'min_natr': 0.07,  # 7% - filter out low volatility "dead fish" (LTC, EOS etc)
    # EMA filter: price must be above N-hour EMA (trend structure)
    'ema_trend_span': 96 * 60,  # 96 hours in minutes (4 days)
    # Top gainers selection: Top X% of 24h gainers with min/max bounds
    'top_gainers_pct': 0.05,  # Select top 5% of 24h gainers
    'top_gainers_min': 5,     # Minimum number of symbols to select
    'top_gainers_max': 20,    # Maximum number of symbols to select
    'universe_check_interval_minutes': 60,  # Check universe every 60 minutes
    
    # --- Entry Signal Parameters ---
    # System Circuit Breaker (BTC 1h change threshold)
    'btc_hourly_drop_threshold': -0.015,  # -1.5%
    
    # Bollinger Band for Volatility Breakout
    'bb_length': 20,
    'bb_std': 2.8,  # Increased from 2.0 to filter noise
    
    # Volume Confirmation
    'volume_ma_length': 20,
    'volume_multiplier': 3.0,
    
    # ADX Trend Filter - only trade in trending markets
    'adx_length': 14,
    'adx_threshold': 0,  # DISABLED: Momentum is momentum
    
    # EMA Deviation Filter - avoid buying at tops
    'ema_deviation_length': 60,  # 60-minute EMA as "fair value"
    'max_ema_deviation': 100.0,  # DISABLED: Allow momentum chasing (was 0.03)
    
    # Daily Trade Limit - prevent over-trading same symbol
    'max_daily_trades_per_symbol': 2,  # Allow retry within same day
    
    # --- Exit Signal Parameters ---
    # Disaster Stop Loss (hard stop)
    'disaster_stop_pct': 0.2,  # -20%
    
    # ATR Chandelier Exit (Trailing Stop) - replaces StructuralExit
    'atr_length': 14,  # ATR calculation period
    'atr_multiplier': 5.0,  # Tightened: cut losers faster with wider universe
    
    # Break-even mechanism: move stop to entry when profit hits threshold
    'breakeven_trigger_pct': 0.05,  # Trigger at +5% profit
    'breakeven_stop_offset': 0.001,  # Move stop to entry + 0.1% (micro-profit lock)
    
    # Time Stop
    'time_stop_minutes': 480,  # 8 hours - meme coins moon fast or die slow
    'time_stop_min_profit_pct': 0.0,  # 0.0%
    
    # --- Portfolio / Risk Management ---
    'initial_capital': 2050,
    'position_size_usd': 500,
    'leverage': 1,
    
    # --- Trading Costs ---
    'fee_rate': 0.0005,  # 0.05% per trade
    'slippage_rate': 0.002,  # 0.2% slippage (applied to both buy and sell)
    
    # --- Contract Listing Cache ---
    'listing_cache_file': os.path.join(PROJECT_ROOT, '.cache',  'contract_listings.json'),
    
    # --- Precomputed Universe Cache ---
    'universe_cache_file': os.path.join(PROJECT_ROOT, '.cache', 'universe_precomputed.json'),
}