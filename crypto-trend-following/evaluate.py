# evaluate.py
# Meme Coin Strategy Performance Evaluation

import numpy as np
import pandas as pd

__all__ = ['evaluate_performance']


def calculate_sortino_ratio(returns, periods_per_year=365*24*60):
    """
    Calculate Sortino Ratio (uses downside deviation instead of std dev).
    More suitable for crypto strategies with asymmetric returns.
    """
    if len(returns) < 2:
        return 0.0
    
    mean_return = returns.mean() * periods_per_year
    
    # Downside deviation: only consider negative returns
    downside_returns = returns[returns < 0]
    if len(downside_returns) == 0:
        return np.inf
    
    downside_std = downside_returns.std() * np.sqrt(periods_per_year)
    
    if downside_std > 0:
        return mean_return / downside_std
    return np.inf


def calculate_max_consecutive_losses(pnl_series):
    """
    Calculate maximum consecutive losing trades.
    """
    if len(pnl_series) == 0:
        return 0
    
    max_consecutive = 0
    current_consecutive = 0
    
    for pnl in pnl_series:
        if pnl <= 0:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    
    return max_consecutive


def evaluate_performance(trades_df, balance_df, initial_capital, slippage_rate=0.005, fee_rate=0.0005):
    """
    Evaluate backtest performance and return comprehensive statistics.
    
    Args:
        trades_df: DataFrame with trade records
        balance_df: DataFrame with balance history
        initial_capital: Starting capital
        slippage_rate: Slippage rate per side (default 0.5%)
        fee_rate: Fee rate per side (default 0.05%)
        
    Returns:
        dict: Comprehensive statistics dictionary
    """
    print("\n" + "=" * 60)
    print("  PERFORMANCE EVALUATION")
    print("=" * 60)
    
    # Initialize statistics with defaults
    stats = {
        # Basic data
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'initial_capital': initial_capital,
        'final_balance': initial_capital,
        'return_pct': 0.0,
        'total_pnl': 0.0,
        'total_profit': 0.0,
        'total_loss': 0.0,
        
        # Core quality metrics
        'win_rate': 0.0,
        'profit_factor': 0.0,
        'risk_reward_ratio': 0.0,
        'expectancy': 0.0,
        'avg_win_pct': 0.0,
        'avg_loss_pct': 0.0,
        'avg_win_usd': 0.0,
        'avg_loss_usd': 0.0,
        
        # Risk control metrics
        'max_drawdown': 0.0,
        'sharpe_ratio': 0.0,
        'sortino_ratio': 0.0,
        
        # Cost and efficiency metrics
        'total_fees': 0.0,
        'fee_ratio': 0.0,
        'avg_holding_time_mins': 0.0,
        'max_consecutive_losses': 0,
        
        # Gross PnL (friction-free) metrics
        'friction_pct': 0.0,
        'gross_pnl': 0.0,
        'gross_profit_factor': 0.0,
        'gross_win_rate': 0.0,
        'gross_expectancy': 0.0,
        'friction_cost_total': 0.0,
        
        # Exit reason breakdown
        'exit_reasons': {}
    }
    
    # --- Equity Curve Metrics ---
    if balance_df is not None and not balance_df.empty:
        equity_curve = balance_df['balance']
        stats['final_balance'] = float(equity_curve.iloc[-1])
        stats['return_pct'] = ((stats['final_balance'] - initial_capital) / initial_capital) * 100
        
        # Maximum Drawdown
        rolling_peak = equity_curve.cummax()
        drawdown = (equity_curve - rolling_peak) / rolling_peak
        stats['max_drawdown'] = float(drawdown.min()) * 100  # Convert to percentage
        
        # Sharpe Ratio (annualized)
        periodic_returns = equity_curve.pct_change().dropna()
        
        if len(periodic_returns) > 1:
            try:
                periods_per_year = 365 * 24 * 60  # 1-minute bars
                
                mean_return_annual = periodic_returns.mean() * periods_per_year
                std_dev_annual = periodic_returns.std() * np.sqrt(periods_per_year)
                
                if std_dev_annual > 0:
                    stats['sharpe_ratio'] = float(mean_return_annual / std_dev_annual)
                else:
                    stats['sharpe_ratio'] = float('inf')
                
                # Sortino Ratio
                stats['sortino_ratio'] = float(calculate_sortino_ratio(periodic_returns, periods_per_year))
                    
            except Exception as e:
                print(f"[Evaluate] Warning: Could not calculate risk ratios: {e}")
    
    # --- Trade Metrics ---
    if trades_df is None or trades_df.empty:
        print("\n[Evaluate] No trades generated during backtest period.")
        return stats
    
    total_trades = len(trades_df)
    stats['total_trades'] = total_trades
    
    # Win/Loss Analysis
    winning_trades = trades_df[trades_df['pnl_usd'] > 0]
    losing_trades = trades_df[trades_df['pnl_usd'] <= 0]
    
    wins = len(winning_trades)
    losses = len(losing_trades)
    
    stats['winning_trades'] = wins
    stats['losing_trades'] = losses
    stats['win_rate'] = (wins / total_trades) * 100 if total_trades > 0 else 0
    
    # Profit/Loss
    total_profit = winning_trades['pnl_usd'].sum() if wins > 0 else 0
    total_loss = abs(losing_trades['pnl_usd'].sum()) if losses > 0 else 0
    net_pnl = total_profit - total_loss
    
    stats['total_profit'] = float(total_profit)
    stats['total_loss'] = float(total_loss)
    stats['total_pnl'] = float(net_pnl)
    
    # Average Trade
    avg_win_pct = winning_trades['pnl_pct'].mean() if wins > 0 else 0
    avg_loss_pct = losing_trades['pnl_pct'].mean() if losses > 0 else 0
    avg_win_usd = winning_trades['pnl_usd'].mean() if wins > 0 else 0
    avg_loss_usd = abs(losing_trades['pnl_usd'].mean()) if losses > 0 else 0
    
    stats['avg_win_pct'] = float(avg_win_pct)
    stats['avg_loss_pct'] = float(avg_loss_pct)
    stats['avg_win_usd'] = float(avg_win_usd)
    stats['avg_loss_usd'] = float(avg_loss_usd)
    
    # Profit Factor
    stats['profit_factor'] = float(total_profit / total_loss) if total_loss > 0 else float('inf')
    
    # Risk/Reward Ratio (average win / average loss)
    stats['risk_reward_ratio'] = float(avg_win_usd / avg_loss_usd) if avg_loss_usd > 0 else float('inf')
    
    # Expectancy (expected profit per trade)
    stats['expectancy'] = float(net_pnl / total_trades) if total_trades > 0 else 0
    
    # Total fees
    if 'fees_paid' in trades_df.columns:
        total_fees = trades_df['fees_paid'].sum()
        stats['total_fees'] = float(total_fees)
        stats['fee_ratio'] = float(total_fees / total_profit * 100) if total_profit > 0 else 0
    
    # Average holding time (in minutes)
    if 'entry_time' in trades_df.columns and 'exit_time' in trades_df.columns:
        trades_df_copy = trades_df.copy()
        trades_df_copy['entry_time'] = pd.to_datetime(trades_df_copy['entry_time'])
        trades_df_copy['exit_time'] = pd.to_datetime(trades_df_copy['exit_time'])
        holding_times = (trades_df_copy['exit_time'] - trades_df_copy['entry_time']).dt.total_seconds() / 60
        stats['avg_holding_time_mins'] = float(holding_times.mean())
    
    # Max consecutive losses
    stats['max_consecutive_losses'] = calculate_max_consecutive_losses(trades_df['pnl_usd'].values)
    
    # Exit reason breakdown
    if 'exit_reason' in trades_df.columns:
        exit_counts = trades_df['exit_reason'].value_counts().to_dict()
        stats['exit_reasons'] = {str(k): int(v) for k, v in exit_counts.items()}
    
    # --- Gross PnL Analysis (Friction-Free Metrics) ---
    # Total friction per round-trip: 2 * slippage + 2 * fee
    friction_pct = 2 * slippage_rate + 2 * fee_rate  # e.g., 0.011 = 1.1%
    stats['friction_pct'] = float(friction_pct * 100)  # Store as percentage
    
    # Restore gross PnL by adding back friction cost
    # Each trade's gross_pnl_pct = net_pnl_pct + friction_pct
    trades_df_analysis = trades_df.copy()
    trades_df_analysis['gross_pnl_pct'] = trades_df_analysis['pnl_pct'] + (friction_pct * 100)
    
    # Gross profit/loss
    gross_winning = trades_df_analysis[trades_df_analysis['gross_pnl_pct'] > 0]
    gross_losing = trades_df_analysis[trades_df_analysis['gross_pnl_pct'] <= 0]
    
    gross_wins = len(gross_winning)
    gross_losses = len(gross_losing)
    
    stats['gross_win_rate'] = (gross_wins / total_trades) * 100 if total_trades > 0 else 0
    
    # Calculate gross PnL in USD
    # Approximate: gross_pnl_usd = net_pnl_usd + (position_size * friction_pct)
    # Since we don't have position_size directly, use pnl_pct relationship
    avg_position_size = stats['total_profit'] / (avg_win_pct / 100) if avg_win_pct != 0 else 500
    friction_cost_per_trade = avg_position_size * friction_pct
    total_friction_cost = friction_cost_per_trade * total_trades
    
    stats['friction_cost_total'] = float(total_friction_cost)
    stats['gross_pnl'] = float(net_pnl + total_friction_cost)
    
    # Gross profit factor
    gross_profit = gross_winning['gross_pnl_pct'].sum() * avg_position_size / 100 if gross_wins > 0 else 0
    gross_loss = abs(gross_losing['gross_pnl_pct'].sum()) * avg_position_size / 100 if gross_losses > 0 else 0
    stats['gross_profit_factor'] = float(gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    
    # Gross expectancy
    stats['gross_expectancy'] = float(stats['gross_pnl'] / total_trades) if total_trades > 0 else 0
    
    # Print Results
    print("\n--- Trade Statistics ---")
    print(f"Total Trades: {total_trades}")
    print(f"Winning Trades: {wins}")
    print(f"Losing Trades: {losses}")
    print(f"Win Rate: {stats['win_rate']:.2f}%")
    
    print("\n--- Profit/Loss ---")
    print(f"Total Profit: ${total_profit:.2f}")
    print(f"Total Loss: ${total_loss:.2f}")
    print(f"Net P&L: ${net_pnl:.2f}")
    print(f"Profit Factor: {stats['profit_factor']:.2f}")
    
    print("\n--- Core Quality ---")
    print(f"Risk/Reward Ratio: {stats['risk_reward_ratio']:.2f}")
    print(f"Expectancy: ${stats['expectancy']:.2f}")
    print(f"Average Win: {avg_win_pct:.2f}% (${avg_win_usd:.2f})")
    print(f"Average Loss: {avg_loss_pct:.2f}% (${avg_loss_usd:.2f})")
    
    print("\n--- Risk Control ---")
    print(f"Max Drawdown: {stats['max_drawdown']:.2f}%")
    print(f"Sharpe Ratio: {stats['sharpe_ratio']:.2f}")
    print(f"Sortino Ratio: {stats['sortino_ratio']:.2f}")
    
    print("\n--- Cost & Efficiency ---")
    print(f"Total Fees: ${stats['total_fees']:.2f}")
    print(f"Fee Ratio: {stats['fee_ratio']:.2f}%")
    print(f"Avg Holding Time: {stats['avg_holding_time_mins']:.1f} mins")
    print(f"Max Consecutive Losses: {stats['max_consecutive_losses']}")
    
    print("\n--- Gross PnL Analysis (Friction-Free) ---")
    print(f"Friction per Trade: {stats['friction_pct']:.2f}%")
    print(f"Total Friction Cost: ${stats['friction_cost_total']:.2f}")
    print(f"Gross PnL (No Friction): ${stats['gross_pnl']:.2f}")
    print(f"Gross Win Rate: {stats['gross_win_rate']:.2f}%")
    print(f"Gross Profit Factor: {stats['gross_profit_factor']:.2f}")
    print(f"Gross Expectancy: ${stats['gross_expectancy']:.2f}")
    
    # Strategy Health Check
    if stats['gross_pnl'] > 0 and stats['total_pnl'] < 0:
        print("\n*** DIAGNOSIS: Strategy has ALPHA but friction is killing it! ***")
        print("    Consider reducing slippage assumption or improving execution.")
    elif stats['gross_pnl'] < 0:
        print("\n*** DIAGNOSIS: Strategy has NO edge even without friction. ***")
        print("    Need to revise entry/exit logic.")
    
    print("\n--- Portfolio Metrics ---")
    print(f"Initial Capital: ${initial_capital:.2f}")
    print(f"Final Balance: ${stats['final_balance']:.2f}")
    print(f"Total Return: {stats['return_pct']:.2f}%")
    
    # Exit Reason Breakdown
    print("\n--- Exit Reason Breakdown ---")
    for reason, count in stats['exit_reasons'].items():
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
    
    return stats