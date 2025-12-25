# backtest/precompute_universe.py
# PLUGGABLE SELECTION MODE
# Strategy Pattern: Switch between different coin selection logics
# Modes: TREND_24H (original), BREAKOUT_1H (ignition), REVERSION_1H (shorting)

import pandas as pd
import numpy as np
import json
import os
import sys
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG
from backtest.data_loader import BacktestDataLoader as MemeDataHandler
from core.universe import UniverseManager

# ==============================================================================
# [CONFIG] Selection Mode Switch
# ------------------------------------------------------------------------------
# Mode descriptions:
# 'TREND_24H'    : (Original) Find coins with highest 24h gain + volatility (trend following)
# 'BREAKOUT_1H'  : Find coins with sudden 1h volume spike + price surge (ignition)
# 'REVERSION_1H' : Find coins with extreme 1h gains + mean deviation (shorting)
# 'NEW_LISTING'  : Find coins in their first 24 hours of life (Day-1 strategy)
# ==============================================================================
SELECTION_MODE = 'NEW_LISTING'

def calculate_indicators_and_score(df_1h, symbol=None, listing_time=None):
    """
    Calculate indicators and score based on SELECTION_MODE.
    Returns (df_1h with indicators, mask for valid entries).
    
    Args:
        df_1h: DataFrame with 1h OHLCV data
        symbol: Contract symbol (used for NEW_LISTING mode)
        listing_time: Listing timestamp in ms (used for NEW_LISTING mode)
    """
    # Ensure quote_volume exists
    if 'quote_volume' not in df_1h.columns:
        df_1h['quote_volume'] = df_1h['close'] * df_1h['volume']
    
    # -------------------------------------------------------------------------
    # [Common Indicators] Used by all modes
    # -------------------------------------------------------------------------
    df_1h['vol_24h'] = df_1h['quote_volume'].rolling(24).sum()
    
    # 24h Volatility (NATR) - Blue chips < 0.05, meme coins often > 0.10
    df_1h['high_24h'] = df_1h['high'].rolling(24).max()
    df_1h['low_24h'] = df_1h['low'].rolling(24).min()
    df_1h['natr'] = (df_1h['high_24h'] - df_1h['low_24h']) / df_1h['close']
    
    # -------------------------------------------------------------------------
    # [Mode-Specific Logic] Calculate score based on selection mode
    # -------------------------------------------------------------------------
    
    if SELECTION_MODE == 'TREND_24H':
        # [Original Logic] Chase 24h trend
        # Score = Momentum * Volatility
        df_1h['roc_24h'] = df_1h['close'].pct_change(24)
        df_1h['score'] = df_1h['roc_24h'] * df_1h['natr']
        
        # Filter: Basic liquidity + rising coins only
        min_volume = 10_000_000  # 10M USDT
        mask = (
            (df_1h['vol_24h'] >= min_volume) &
            (df_1h['roc_24h'] > 0)  # Only rising coins
        )
        
    elif SELECTION_MODE == 'BREAKOUT_1H':
        # [Ignition Logic] Catch 1h sudden breakout
        # Core hypothesis: Twitter calls cause short-term volume + price spikes
        
        # 1. Short-term momentum (1h ROC)
        df_1h['roc_1h'] = df_1h['close'].pct_change(1)
        
        # 2. Relative Volume (RVol) - Current 1h volume / Past 24h average
        # Emphasize RVol weight since volume spike is the key signal
        df_1h['vol_avg_24h'] = df_1h['volume'].rolling(window=24, min_periods=1).mean()
        df_1h['rvol'] = df_1h['volume'] / (df_1h['vol_avg_24h'] + 1e-5)  # Prevent div by zero
        
        # 3. Score: Fast riser * High volume = Ignition
        df_1h['score'] = df_1h['roc_1h'] * df_1h['rvol']
        
        # Filter: Stricter - only true ignitions
        min_volume = 5_000_000   # 5M USDT (lower threshold to catch new hotspots)
        mask = (
            (df_1h['vol_24h'] >= min_volume) &
            (df_1h['roc_1h'] > 0.02) &    # At least +2% in 1 hour
            (df_1h['rvol'] > 2.0)         # At least 2x average volume
        )
        
    elif SELECTION_MODE == 'REVERSION_1H':
        # [Future] Short top gainers
        # Logic: Higher ROC + Higher mean deviation = Higher crash probability
        
        df_1h['roc_1h'] = df_1h['close'].pct_change(1)
        df_1h['ema_24'] = df_1h['close'].ewm(span=24, adjust=False).mean()
        df_1h['bias'] = (df_1h['close'] - df_1h['ema_24']) / df_1h['ema_24']
        
        # Score: Find highest gainers with highest deviation
        df_1h['score'] = df_1h['roc_1h'] * df_1h['bias']
        
        # Filter: Only extreme pumps worth shorting
        min_volume = 10_000_000  # 10M USDT
        mask = (
            (df_1h['vol_24h'] >= min_volume) &
            (df_1h['roc_1h'] > 0.05)       # At least +5% pump to short
        )
        
    elif SELECTION_MODE == 'NEW_LISTING':
        # [Day-1 Strategy] Trade coins in their first 24 hours
        # Logic: New listings have extreme volatility, we capture the momentum
        
        if listing_time is None or listing_time <= 0:
            # No listing time available, return empty mask
            df_1h['score'] = np.nan
            return df_1h, pd.Series(False, index=df_1h.index)
        
        # Convert listing_time (ms) to datetime
        listing_dt = pd.to_datetime(listing_time, unit='ms', utc=True)
        
        # Calculate hours since listing for each row
        # df_1h.index is already timezone-aware timestamps
        time_diff_hours = (df_1h.index.tz_localize('UTC') - listing_dt).total_seconds() / 3600
        
        # Score: Newer coins get higher priority (inverted time)
        # All new coins get selected, sorting happens later
        df_1h['score'] = 1000 - time_diff_hours
        
        # Filter: Only first 24 hours of listing
        # time_diff >= 0 ensures we don't pick data before listing
        mask = (time_diff_hours >= 0) & (time_diff_hours <= 24)
        
    else:
        raise ValueError(f"Unknown SELECTION_MODE: {SELECTION_MODE}")
    
    # Final filter: Remove NaN scores
    mask = mask & (~df_1h['score'].isna())
    
    return df_1h, mask

def run_precomputation():
    print("=" * 60)
    print(f"=== Universe Precomputation ({SELECTION_MODE} MODE) ===")
    if SELECTION_MODE == 'TREND_24H':
        print("=== Strategy: Rank by 24h Momentum * Volatility ===")
    elif SELECTION_MODE == 'BREAKOUT_1H':
        print("=== Strategy: Rank by 1h ROC * Relative Volume ===")
    elif SELECTION_MODE == 'REVERSION_1H':
        print("=== Strategy: Rank by 1h ROC * Mean Bias (Short) ===")
    elif SELECTION_MODE == 'NEW_LISTING':
        print("=== Strategy: Day-1 Listing (First 24 hours only) ===")
    print("=" * 60)
    
    config = CONFIG
    data_handler = MemeDataHandler(config)
    universe_manager = UniverseManager(config)
    universe_manager.initialize()
    available_symbols = universe_manager.get_available_contracts(config['backtest_end_date'])
    
    hourly_candidates = {}
    top_n = 30  # Select top 30 coins per hour
    
    processed = 0
    skipped = 0
    
    for i, symbol in enumerate(available_symbols):
        print(f"[{i+1}/{len(available_symbols)}] Scanning {symbol}...", end='\r')
        
        # [NEW_LISTING] Get listing time for this symbol
        listing_time = universe_manager.get_listing_time(symbol)
        
        # Load data
        df = data_handler.load_contract_data(symbol, config['backtest_start_date'], config['backtest_end_date'], '1m')
        if df is None or df.empty:
            skipped += 1
            continue
            
        # Resample to 1h
        agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        if 'quote_volume' in df.columns: 
            agg_dict['quote_volume'] = 'sum'
        df_1h = df.resample('1h').agg(agg_dict).dropna()
        
        # For NEW_LISTING mode, we allow shorter history (new coins won't have 24h data)
        min_bars = 1 if SELECTION_MODE == 'NEW_LISTING' else 24
        if len(df_1h) < min_bars: 
            data_handler.clear_all_cache()
            del df
            continue
        
        # Calculate indicators and score based on SELECTION_MODE
        # Pass symbol and listing_time for NEW_LISTING mode
        df_1h, mask = calculate_indicators_and_score(df_1h, symbol, listing_time)
        valid_df = df_1h[mask]
        
        for ts, row in valid_df.iterrows():
            ts_key = str(int(ts.value // 10**6))
            if ts_key not in hourly_candidates: 
                hourly_candidates[ts_key] = []
            # Store symbol and score for subsequent sorting
            hourly_candidates[ts_key].append({'s': symbol, 'score': row['score']})
            
        processed += 1
        data_handler.clear_all_cache()
        del df, df_1h

    # Sort by score and select Top N
    print(f"\n[{SELECTION_MODE}] Ranking candidates...")
    final_universe = {}
    for ts_key, candidates in hourly_candidates.items():
        # Sort by score descending (higher is better)
        candidates.sort(key=lambda x: x['score'], reverse=True)
        # Take Top N
        final_universe[ts_key] = [item['s'] for item in candidates[:top_n]]
        
    # Save
    output_file = CONFIG.get('universe_cache_file', 'universe_precomputed.json')
    with open(output_file, 'w') as f: 
        json.dump(final_universe, f)
    print(f"\n[{SELECTION_MODE}] Done. Saved to {output_file}. Periods: {len(final_universe)}")

if __name__ == "__main__":
    run_precomputation()
