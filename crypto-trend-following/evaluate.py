# evaluate.py
# Meme Coin Strategy Performance Evaluation

import numpy as np

__all__ = ['evaluate_performance']


def evaluate_performance(trades_df, balance_df, initial_capital):
    """
    Evaluate backtest performance.
    
    Args:
        trades_df: DataFrame with trade records
        balance_df: DataFrame with balance history
        initial_capital: Starting capital
    """
    print("\n" + "=" * 60)
    print("  PERFORMANCE EVALUATION")
    print("=" * 60)
    
    # --- Equity Curve Metrics ---
    max_drawdown = 0.0
    sharpe_ratio = 0.0
    
    if balance_df is not None and not balance_df.empty:
        equity_curve = balance_df['balance']
        
        # 1. Maximum Drawdown
        rolling_peak = equity_curve.cummax()
        drawdown = (equity_curve - rolling_peak) / rolling_peak
        max_drawdown = drawdown.min()
        
        # 2. Sharpe Ratio (annualized)
        periodic_returns = equity_curve.pct_change().dropna()
        
        if len(periodic_returns) > 1:
            try:
                # Assume 1-minute bars
                periods_per_year = 365 * 24 * 60
                
                mean_return_annual = periodic_returns.mean() * periods_per_year
                std_dev_annual = periodic_returns.std() * np.sqrt(periods_per_year)
                
                if std_dev_annual > 0:
                    sharpe_ratio = mean_return_annual / std_dev_annual
                else:
                    sharpe_ratio = np.inf
                    
            except Exception as e:
                print(f"[Evaluate] Warning: Could not calculate Sharpe Ratio: {e}")
                sharpe_ratio = np.nan
    
    # --- Trade Metrics ---
    if trades_df is None or trades_df.empty:
        print("\n[Evaluate] No trades generated during backtest period.")
        return
    
    total_trades = len(trades_df)
    
    # Win/Loss Analysis
    wins = (trades_df['pnl_usd'] > 0).sum()
    losses = (trades_df['pnl_usd'] <= 0).sum()
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    
    # Profit/Loss
    total_profit = trades_df[trades_df['pnl_usd'] > 0]['pnl_usd'].sum()
    total_loss = abs(trades_df[trades_df['pnl_usd'] <= 0]['pnl_usd'].sum())
    net_pnl = total_profit - total_loss
    
    # Average Trade
    avg_win = trades_df[trades_df['pnl_usd'] > 0]['pnl_pct'].mean() if wins > 0 else 0
    avg_loss = trades_df[trades_df['pnl_usd'] <= 0]['pnl_pct'].mean() if losses > 0 else 0
    
    # Profit Factor
    profit_factor = total_profit / total_loss if total_loss > 0 else np.inf
    
    # Final Balance
    final_balance = balance_df['balance'].iloc[-1] if not balance_df.empty else initial_capital
    total_return = ((final_balance - initial_capital) / initial_capital) * 100
    
    # Print Results
    print("\n--- Trade Statistics ---")
    print(f"Total Trades: {total_trades}")
    print(f"Winning Trades: {wins}")
    print(f"Losing Trades: {losses}")
    print(f"Win Rate: {win_rate:.2f}%")
    
    print("\n--- Profit/Loss ---")
    print(f"Total Profit: ${total_profit:.2f}")
    print(f"Total Loss: ${total_loss:.2f}")
    print(f"Net P&L: ${net_pnl:.2f}")
    print(f"Profit Factor: {profit_factor:.2f}")
    
    print("\n--- Average Trade ---")
    print(f"Average Win: {avg_win:.2f}%")
    print(f"Average Loss: {avg_loss:.2f}%")
    
    print("\n--- Portfolio Metrics ---")
    print(f"Initial Capital: ${initial_capital:.2f}")
    print(f"Final Balance: ${final_balance:.2f}")
    print(f"Total Return: {total_return:.2f}%")
    print(f"Max Drawdown: {max_drawdown * 100:.2f}%")
    print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
    
    # Exit Reason Breakdown
    print("\n--- Exit Reason Breakdown ---")
    exit_counts = trades_df['exit_reason'].value_counts()
    for reason, count in exit_counts.items():
        pct = (count / total_trades) * 100
        print(f"  {reason}: {count} ({pct:.1f}%)")
    
    # Top/Bottom Trades
    print("\n--- Best Trades ---")
    best_trades = trades_df.nlargest(3, 'pnl_pct')
    for _, trade in best_trades.iterrows():
        print(f"  {trade['symbol']}: +{trade['pnl_pct']:.2f}%")
    
    print("\n--- Worst Trades ---")
    worst_trades = trades_df.nsmallest(3, 'pnl_pct')
    for _, trade in worst_trades.iterrows():
        print(f"  {trade['symbol']}: {trade['pnl_pct']:.2f}%")