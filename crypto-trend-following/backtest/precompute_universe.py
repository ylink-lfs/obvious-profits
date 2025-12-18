# backtest/precompute_universe.py
# UNIVERSAL SELECTION VERSION
# Logic: "Survival of the fittest" - No Blacklists.
# Strategy: Rank by (Momentum * Volatility). Heavy coins naturally drop to bottom.

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

def run_precomputation():
    print("=" * 60)
    print("=== Universe Precomputation (UNIVERSAL MODE) ===")
    print("=== Strategy: Rank by Momentum * Volatility ===")
    print("=== BLACKLIST REMOVED: Let the math decide. ===")
    print("=" * 60)
    
    config = CONFIG
    data_handler = MemeDataHandler(config)
    universe_manager = UniverseManager(config)
    universe_manager.initialize()
    available_symbols = universe_manager.get_available_contracts(config['backtest_end_date'])
    
    hourly_candidates = {}
    
    # Baseline threshold (Universal Baseline)
    min_volume = 10_000_000  # 10M (Lowered threshold, some early meme coins haven't gained volume yet)
    top_n = 30               # Select the 30 most volatile in the market
    
    print(f"[Universal] Filters: Vol > {min_volume//1e6}M")
    print(f"[Universal] Ranking: Score = 24h_ROC * NATR")
    
    processed = 0
    skipped = 0
    
    for i, symbol in enumerate(available_symbols):
        # Remove all blacklist checks
        # Even BTC, if it has volatility and momentum to beat SHIB one day, it deserves to be traded
        
        print(f"[{i+1}/{len(available_symbols)}] Scanning {symbol}...", end='\r')
        
        # Load data
        df = data_handler.load_contract_data(symbol, config['backtest_start_date'], config['backtest_end_date'], '1m')
        if df is None or df.empty:
            skipped += 1
            continue
            
        # Resample to 1h
        agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        if 'quote_volume' in df.columns: agg_dict['quote_volume'] = 'sum'
        df_1h = df.resample('1h').agg(agg_dict).dropna()
        if len(df_1h) < 24: 
            data_handler.clear_all_cache()
            del df
            continue
        
        # Calculate Universal Metrics
        if 'quote_volume' not in df_1h.columns:
            df_1h['quote_volume'] = df_1h['close'] * df_1h['volume']
            
        # 1. Volume (Liquidity Check)
        df_1h['vol_24h'] = df_1h['quote_volume'].rolling(24).sum()
        
        # 2. NATR (Volatility Quality) - The "Meme Factor"
        # Blue chips' NATR rarely exceeds 0.05, meme coins often stay above 0.10
        df_1h['high_24h'] = df_1h['high'].rolling(24).max()
        df_1h['low_24h'] = df_1h['low'].rolling(24).min()
        df_1h['natr'] = (df_1h['high_24h'] - df_1h['low_24h']) / df_1h['close']
        
        # 3. Momentum (24h ROC)
        df_1h['roc_24h'] = df_1h['close'].pct_change(24)
        
        # 4. Composite Score (Core ranking formula)
        # Score = Momentum * Volatility
        # Logic: We want coins with "violent volatility and upward breakout"
        # abs(roc) would include coins in freefall with high volatility (shorting potential), but we only long
        # Here we only take roc_24h > 0, and use multiplication to amplify winner-take-all effect
        df_1h['score'] = df_1h['roc_24h'] * df_1h['natr']
        
        # --- UNIVERSAL FILTER ---
        # This is a very wide funnel, only filtering out zombie coins with terrible liquidity
        mask = (
            (df_1h['vol_24h'] >= min_volume) &
            (df_1h['roc_24h'] > 0) & # Only look at rising coins
            (~df_1h['score'].isna())
        )
        
        valid_df = df_1h[mask]
        
        for ts, row in valid_df.iterrows():
            ts_key = str(int(ts.value // 10**6))
            if ts_key not in hourly_candidates: hourly_candidates[ts_key] = []
            # Store symbol and score for subsequent sorting
            hourly_candidates[ts_key].append({'s': symbol, 'score': row['score']})
            
        processed += 1
        data_handler.clear_all_cache()
        del df, df_1h

    # Sort by Universal Score and Select Top N
    print(f"\n[Universal] Ranking candidates by (Momentum * Volatility)...")
    final_universe = {}
    for ts_key, candidates in hourly_candidates.items():
        # Sort by score descending (higher is better)
        candidates.sort(key=lambda x: x['score'], reverse=True)
        # Take Top N
        final_universe[ts_key] = [item['s'] for item in candidates[:top_n]]
        
    # Save
    output_file = CONFIG.get('universe_cache_file', 'universe_precomputed.json')
    with open(output_file, 'w') as f: json.dump(final_universe, f)
    print(f"\n[Universal] Done. Saved to {output_file}. Periods: {len(final_universe)}")

if __name__ == "__main__":
    run_precomputation()
