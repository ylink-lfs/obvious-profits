# main.py
# Meme Coin Momentum Strategy - Main Entry Point

import json
import os
import traceback
from datetime import datetime
from config import CONFIG
from engine import MemeBacktestEngine
from evaluate import evaluate_performance


def save_results(trades_df, summary, output_dir='output'):
    """Save trades and summary to files."""
    # Create output directory if not exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate timestamp for filenames
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save trades to CSV
    trades_file = os.path.join(output_dir, f'trades_{timestamp}.csv')
    if trades_df is not None and not trades_df.empty:
        trades_df.to_csv(trades_file, index=False)
        print(f"[Output] Trades saved to: {trades_file}")
    else:
        print("[Output] No trades to save")
    
    # Save summary to JSON
    summary_file = os.path.join(output_dir, f'summary_{timestamp}.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"[Output] Summary saved to: {summary_file}")
    
    return trades_file, summary_file


def main():
    """Run the meme coin momentum strategy backtest."""
    print("\n" + "=" * 60)
    print("  MEME COIN MOMENTUM STRATEGY BACKTEST")
    print("=" * 60)
    
    # Display configuration
    print("\n--- Configuration ---")
    print(f"Initial Capital: ${CONFIG['initial_capital']}")
    print(f"Position Size: ${CONFIG['position_size_usd']}")
    print(f"Fee Rate: {CONFIG['fee_rate'] * 100}%")
    print(f"Slippage Rate: {CONFIG['slippage_rate'] * 100}%")
    
    try:
        # Create and run engine
        engine = MemeBacktestEngine(CONFIG)
        trades_df, balance_df = engine.run()
        
        # Evaluate results
        if trades_df is not None and balance_df is not None:
            # Get comprehensive statistics from evaluate_performance
            stats = evaluate_performance(
                trades_df,
                balance_df,
                CONFIG['initial_capital'],
                slippage_rate=CONFIG['slippage_rate'],
                fee_rate=CONFIG['fee_rate']
            )
            
            print("\n" + "=" * 60)
            print("  FINAL SUMMARY")
            print("=" * 60)
            print(f"Total Trades: {stats.get('total_trades', 0)}")
            print(f"Win Rate: {stats.get('win_rate', 0):.2f}%")
            print(f"Profit Factor: {stats.get('profit_factor', 0):.2f}")
            print(f"Risk/Reward: {stats.get('risk_reward_ratio', 0):.2f}")
            print(f"Max Drawdown: {stats.get('max_drawdown', 0):.2f}%")
            print(f"Sharpe Ratio: {stats.get('sharpe_ratio', 0):.2f}")
            print(f"Total PnL: ${stats.get('total_pnl', 0):.2f}")
            print(f"Final Balance: ${stats.get('final_balance', CONFIG['initial_capital']):.2f}")
            print(f"Return: {stats.get('return_pct', 0):.2f}%")
            
            print("\n--- Gross PnL (Friction-Free) ---")
            print(f"Friction per Trade: {stats.get('friction_pct', 0):.2f}%")
            print(f"Gross PnL: ${stats.get('gross_pnl', 0):.2f}")
            print(f"Gross Win Rate: {stats.get('gross_win_rate', 0):.2f}%")
            print(f"Gross Profit Factor: {stats.get('gross_profit_factor', 0):.2f}")
            
            # Save results to files
            save_results(trades_df, stats)
            
    except Exception as e:
        print(f"\n[ERROR] Backtest failed: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()