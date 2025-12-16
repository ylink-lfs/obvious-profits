# main.py
# Meme Coin Momentum Strategy - Main Entry Point

import traceback
from config import CONFIG
from engine import MemeBacktestEngine
from evaluate import evaluate_performance


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
    print(f"Top Gainers Count: {CONFIG['top_gainers_count']}")
    
    try:
        # Create and run engine
        engine = MemeBacktestEngine(CONFIG)
        trades_df, balance_df = engine.run()
        
        # Evaluate results
        if trades_df is not None and balance_df is not None:
            evaluate_performance(
                trades_df,
                balance_df,
                CONFIG['initial_capital']
            )
            
            # Get portfolio summary
            summary = engine.portfolio.get_summary()
            
            print("\n" + "=" * 60)
            print("  FINAL SUMMARY")
            print("=" * 60)
            print(f"Total Trades: {summary['total_trades']}")
            print(f"Win Rate: {summary['win_rate']:.2f}%")
            print(f"Total PnL: ${summary['total_pnl']:.2f}")
            print(f"Final Balance: ${summary['final_balance']:.2f}")
            print(f"Return: {summary['return_pct']:.2f}%")
            
    except Exception as e:
        print(f"\n[ERROR] Backtest failed: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()