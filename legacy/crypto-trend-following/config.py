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
    
    # --- Strategy Timeframe (Dimension Reduction) ---
    # 1 = Original 1m strategy
    # 15 = 15m downsampling strategy (data still 1m, but indicators aggregated to 15m)
    # 60 = 1h downsampling strategy
    'strategy_timeframe_minutes': 15,
    
    # --- Trade Direction ---
    # 'LONG'  = Long only (breakout / momentum)
    # 'SHORT' = Short only (post-hype reversion)
    'trade_direction': 'SHORT',  # Post-Hype Butcher Strategy
    
    # --- SHORT Strategy Parameters (Sniper Butcher v2) ---
    'short_stop_loss_pct': 0.04,      # 5% stop (room to breathe)
    'short_take_profit_pct': 0.5,    # 50% target profit
    'short_trailing_trigger': 0.06,   # Enable trailing after 6% profit
    'short_trailing_dist': 0.03,      # 3% trailing distance
    'short_time_stop_mins': 45,       # Time stop for stale shorts
    'cooldown_minutes': 240,          # 4h cooldown after exit (prevent churn)
    
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
    'min_natr': 0.08,  # 8% - filter out low volatility "dead fish" (LTC, EOS etc)
    # EMA filter: price must be above N-hour EMA (trend structure)
    'ema_trend_span': 96 * 60,  # 96 hours in minutes (4 days)
    # Top gainers selection: Top X% of 24h gainers with min/max bounds
    'top_gainers_pct': 0.05,  # Select top 5% of 24h gainers
    'top_gainers_min': 5,     # Minimum number of symbols to select
    'top_gainers_max': 20,    # Maximum number of symbols to select
    'universe_check_interval_minutes': 60,  # Check universe every 60 minutes
    
    # --- Entry Signal Parameters ---
    # System Circuit Breaker (BTC 1h change threshold)
    'btc_hourly_drop_threshold': -0.01,  # -1%
    
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
    'atr_multiplier': 6.0,  # Tightened: cut losers faster with wider universe
    
    # Break-even mechanism: move stop to entry when profit hits threshold
    'breakeven_trigger_pct': 0.05,  # Trigger at +5% profit
    'breakeven_stop_offset': 0.001,  # Move stop to entry + 0.1% (micro-profit lock)
    
    # Time Stop
    'time_stop_minutes': 480,  # 8 hours - meme coins moon fast or die slow
    'time_stop_min_profit_pct': 0.0,  # 0.0%
    
    # --- Day-1 Listing Strategy Parameters ---
    # Trade only coins within their first N hours of listing
    'day1_listing_window_hours': 24,   # Only trade coins listed within 24 hours
    'day1_wait_minutes': 20,           # Wait 20 minutes for clear direction
    'day1_disaster_stop_pct': 0.04,    # 4% hard stop (tight) for new listings
    'day1_breakout_buffer': 0.02,      # 2% buffer above ORB high (strong moat)
    'day1_volume_factor': 2,         # Require 2x volume vs MA
    
    # [Day-1 Fast Cut] 10-Minute Stalemate Rule
    'day1_stalemate_mins': 15,         # Stalemate exit after 15 minutes if losing
    
    # [Day-1 Time-Momentum Stop] Up-or-Out
    'day1_time_stop_mins': 20,         # Time stop after 20 minutes
    'day1_time_stop_threshold': 0.01,  # Exit if profit < 1% after time_stop_mins
    
    # [Day-1 Stepped Risk Control] Three-stage rocket system
    # Stage 1: Growth phase - move to breakeven to eliminate zombie trades
    'day1_stage1_trigger': 0.025,      # Trigger at +2.5% profit (greedier BE)
    'day1_stage1_action': 'BE',        # Action: Move to Breakeven (+0.5% for fees)
    
    # Stage 2: Breakout phase - wide trailing to survive shakeouts  
    'day1_stage2_trigger': 0.09,       # Trigger at +9% profit
    'day1_stage2_trail': 0.05,         # Action: 5% wide trailing stop
    
    # Stage 3: Mania phase - tight trailing to lock profits
    'day1_stage3_trigger': 0.3,       # Trigger at +30% profit
    'day1_stage3_trail': 0.05,         # Action: 5% tight trailing stop
    
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