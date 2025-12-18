# run_backtest.py
# Meme Coin Momentum Strategy - Backtest Entry Point
# 
# Usage:
#   python run_backtest.py                  # Auto-detect: use cache if exists, else precompute
#   python run_backtest.py --force          # Force regenerate all precomputed data
#   python run_backtest.py --skip-precompute # Skip precompute check (assume cache is valid)
#
# The script automatically discovers and runs prerequisite scripts:
#   1. scan_contracts - Scans contract listing times from data source
#   2. precompute_universe - Precomputes top gainers for each hour

import argparse
import io
import json
import os
import sys
import traceback
from datetime import datetime
from config import CONFIG, PROJECT_ROOT


class TeeOutput:
    """Capture stdout to a buffer while still printing to console."""
    
    def __init__(self):
        self.buffer = io.StringIO()
        self.original_stdout = sys.stdout
        self.capturing = False
    
    def start(self):
        """Start capturing output."""
        self.capturing = True
        sys.stdout = self
    
    def stop(self):
        """Stop capturing and restore original stdout."""
        self.capturing = False
        sys.stdout = self.original_stdout
    
    def write(self, text):
        """Write to both buffer and original stdout."""
        if self.capturing:
            self.buffer.write(text)
        self.original_stdout.write(text)
    
    def flush(self):
        """Flush both streams."""
        self.buffer.flush()
        self.original_stdout.flush()
    
    def get_captured(self) -> str:
        """Get all captured output."""
        return self.buffer.getvalue()
    
    def save_to_file(self, filepath: str):
        """Save captured output to a file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.get_captured())
        print(f"[Output] Log saved to: {filepath}")


def check_and_run_precompute(force: bool = False, skip: bool = False) -> bool:
    """
    Check if precomputed data exists and run precomputation if needed.
    
    Args:
        force: Force regeneration even if cache exists
        skip: Skip precompute entirely (assume cache is valid)
    
    Returns:
        True if precomputed data is available, False otherwise
    """
    if skip:
        print("[Precompute] Skipping precompute check (--skip-precompute)")
        return True
    
    listing_cache = CONFIG['listing_cache_file']
    universe_cache = CONFIG['universe_cache_file']
    
    # Ensure cache directory exists
    cache_dir = os.path.dirname(listing_cache)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    
    # Check what needs to be (re)generated
    need_scan_contracts = force or not os.path.exists(listing_cache)
    need_precompute_universe = force or not os.path.exists(universe_cache)
    
    if not need_scan_contracts and not need_precompute_universe:
        print("[Precompute] Cache files found, using existing precomputed data")
        print(f"  - Contract listings: {listing_cache}")
        print(f"  - Universe cache: {universe_cache}")
        return True
    
    # Import precompute modules
    print("\n" + "=" * 60)
    print("  PRECOMPUTATION PHASE")
    print("=" * 60)
    
    if need_scan_contracts:
        print(f"\n[Precompute] {'Force regenerating' if force else 'Generating'} contract listings...")
        try:
            from core.universe import ContractListingScanner
            scanner = ContractListingScanner(CONFIG)
            listings = scanner.scan_contracts(force_rescan=force)
            print(f"[Precompute] Contract scan complete: {len(listings)} contracts")
        except Exception as e:
            print(f"[Precompute] ERROR in contract scan: {e}")
            traceback.print_exc()
            return False
    
    if need_precompute_universe:
        print(f"\n[Precompute] {'Force regenerating' if force else 'Generating'} universe cache...")
        try:
            from backtest.precompute_universe import run_precomputation
            run_precomputation()
        except Exception as e:
            print(f"[Precompute] ERROR in universe precomputation: {e}")
            traceback.print_exc()
            return False
    
    print("\n[Precompute] All precomputation complete!")
    return True


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run Meme Coin Momentum Strategy Backtest',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_backtest.py                    # Auto: use cache or precompute if missing
  python run_backtest.py --force            # Force regenerate all precomputed data
  python run_backtest.py --skip-precompute  # Skip precompute (assume cache valid)
        """
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force regenerate all precomputed data from scratch'
    )
    parser.add_argument(
        '--skip-precompute', '-s',
        action='store_true',
        help='Skip precompute check entirely (assume cache is valid)'
    )
    return parser.parse_args()


# Import after config to ensure proper paths
from backtest import BacktestEngine, evaluate_performance


def save_results(trades_df, summary, log_capture: TeeOutput = None, output_dir='output'):
    """Save trades, summary, and log to files."""
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
    
    # Save log output
    if log_capture is not None:
        log_file = os.path.join(output_dir, f'output_{timestamp}.log')
        log_capture.save_to_file(log_file)
    
    return trades_file, summary_file


def main():
    """Run the meme coin momentum strategy backtest."""
    args = parse_args()
    
    # Step 1: Check and run precomputation if needed
    if not check_and_run_precompute(force=args.force, skip=args.skip_precompute):
        print("\n[ERROR] Precomputation failed. Cannot proceed with backtest.")
        return
    
    print("\n" + "=" * 60)
    print("  MEME COIN MOMENTUM STRATEGY BACKTEST")
    print("=" * 60)
    
    # Display configuration
    print("\n--- Configuration ---")
    print(f"Initial Capital: ${CONFIG['initial_capital']}")
    print(f"Position Size: ${CONFIG['position_size_usd']}")
    print(f"Fee Rate: {CONFIG['fee_rate'] * 100}%")
    print(f"Slippage Rate: {CONFIG['slippage_rate'] * 100}%")
    
    # Initialize log capture (will start capturing at PERFORMANCE EVALUATION)
    log_capture = TeeOutput()
    
    try:
        # Create and run engine
        engine = BacktestEngine(CONFIG)
        trades_df, balance_df = engine.run()
        
        # Start capturing output from PERFORMANCE EVALUATION section
        log_capture.start()
        
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
            
            # Stop capturing before saving (so save messages appear in console only)
            log_capture.stop()
            
            # Save results to files (including captured log)
            save_results(trades_df, stats, log_capture)
        else:
            log_capture.stop()
            print("\n[WARNING] No trades or balance data to evaluate.")
            
    except Exception as e:
        log_capture.stop()
        print(f"\n[ERROR] Backtest failed: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
