# evaluate.py
# [MODIFIED] Added Long/Short performance breakdown.

import pandas as pd
import numpy as np

def evaluate_event_driven_performance(trades_log, balance_history, df_market, initial_capital):
    """
    Evaluate event-driven backtest results
    """
    
    # --- Calculate Advanced Metrics from Equity Curve ---
    max_drawdown = 0.0
    sharpe_ratio = 0.0
    
    if balance_history is not None and not balance_history.empty:
        equity_curve = balance_history['balance']
        
        # 1. Calculate Maximum Drawdown (MDD)
        print("[Evaluate] Calculating Max Drawdown...")
        rolling_peak = equity_curve.cummax()
        drawdown = (equity_curve - rolling_peak) / rolling_peak
        max_drawdown = drawdown.min()
        
        # 2. Calculate Annualized Sharpe Ratio
        print("[Evaluate] Calculating Annualized Sharpe Ratio...")
        periodic_returns = equity_curve.pct_change().dropna()
        
        if len(periodic_returns) > 1:
            try:
                # Infer timeframe
                time_delta = balance_history.index[1] - balance_history.index[0]
                periods_per_day = pd.Timedelta('1D') / time_delta
                periods_per_year = periods_per_day * 365 
                
                print(f"[Evaluate] Inferred {periods_per_year:.0f} periods per year for annualization.")
                
                mean_return_annual = periodic_returns.mean() * periods_per_year
                std_dev_annual = periodic_returns.std() * np.sqrt(periods_per_year)
                
                if std_dev_annual > 0:
                    sharpe_ratio = mean_return_annual / std_dev_annual
                else:
                    sharpe_ratio = np.inf
                    
            except Exception as e:
                print(f"[Evaluate] WARNING: Could not calculate Sharpe Ratio. Error: {e}")
                sharpe_ratio = np.nan
        else:
            sharpe_ratio = np.nan
    
    # --- Original Report ---
    if not trades_log:
        print("\n--- [Evaluate] Strategy Performance Evaluation ---")
        print("[Evaluate] No trades generated during backtest period.")
        strategy_total_return = 0.0
    else:
        print("\n--- [Evaluate] Strategy Performance Evaluation ---")
        total_trades = len(trades_log)
        trades_df = pd.DataFrame(trades_log)
        
        wins = (trades_df['net_profit_pct'] > 0).sum()
        win_rate = (wins / total_trades) * 100
        
        avg_profit = trades_df[trades_df['net_profit_pct'] > 0]['net_profit_pct'].mean()
        avg_loss = trades_df[trades_df['net_profit_pct'] <= 0]['net_profit_pct'].mean()
        profit_loss_ratio = abs(avg_profit / avg_loss) if (avg_loss != 0 and not np.isnan(avg_loss)) else np.inf
        
        strategy_total_return = (balance_history['balance'].iloc[-1] / initial_capital) - 1
        
        print(f"[Evaluate] Total trades: {total_trades}")
        print(f"[Evaluate] Win Rate: {win_rate:.2f}%")
        print(f"[Evaluate] Average profit: {avg_profit:.2f}%")
        print(f"[Evaluate] Average loss: {avg_loss:.2f}%")
        print(f"[Evaluate] Profit/Loss Ratio: {profit_loss_ratio:.2f}")

        # --- [NEW] Break down by Long/Short trades ---
        if 'type' in trades_df.columns:
            print("\n--- Trade Type Breakdown ---")
            long_trades = trades_df[trades_df['type'] == 'Long']
            short_trades = trades_df[trades_df['type'] == 'Short']
            
            print(f"Total Long Trades: {len(long_trades)}")
            if not long_trades.empty:
                print(f"  Long Win Rate: {(long_trades['net_profit_pct'] > 0).sum() / len(long_trades) * 100:.2f}%")
            
            print(f"Total Short Trades: {len(short_trades)}")
            if not short_trades.empty:
                print(f"  Short Win Rate: {(short_trades['net_profit_pct'] > 0).sum() / len(short_trades) * 100:.2f}%")

    # Market return (Buy & Hold)
    market_return = (df_market['close'].iloc[-1] / df_market['close'].iloc[0]) - 1
    
    print("\n--- [Portfolio & Risk Metrics] ---")
    print(f"[Evaluate] Strategy total return: {strategy_total_return * 100:.2f}%")
    print(f"[Evaluate] Market total return (Buy & Hold): {market_return * 100:.2f}%")
    print(f"[Evaluate] Max Drawdown (MDD): {max_drawdown * 100:.2f}%")
    print(f"[Evaluate] Sharpe Ratio (Annualized): {sharpe_ratio:.2f}")


    if strategy_total_return > market_return:
        print("\n[Evaluate] Conclusion: Strategy outperforms the market (Buy & Hold).")
    else:
        print("\n[Evaluate] Conclusion: Strategy underperforms the market (Buy &Hold).")