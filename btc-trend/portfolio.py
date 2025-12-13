# portfolio.py
# [MODIFIED] Fixed AttributeError by changing bar.Index to bar.name

import numpy as np

class Portfolio:
    """
    Handles all capital, risk, and position management.
    [MODIFIED] Adapted for MA/MACD Strategy (Long/Short/Flat).
    """
    def __init__(self, config):
        print("[Portfolio] Initializing Portfolio...")
        self.config = config
        self.balance = self.config['initial_capital']
        self.risk_pct = self.config['risk_per_trade_percent']
        
        # State: 0 = FLAT, 1 = LONG, -1 = SHORT
        self.state = 0
        self.trade_type = None
        
        self.position_size = 0.0
        self.entry_price = 0.0
        self.stop_loss_price = 0.0
        
        self.trades_log = []
        self.balance_history = []

    def check_for_exit(self, bar, fee_pct=0.001):
        """
        Checks exit conditions (SL) for an open position.
        Strategy exits (like Price < MA) are handled by the strategy logic itself.
        """
        if self.state == 0:
            return False

        # Universal Exit: Stop Loss
        # For Long: Low <= SL
        if self.state == 1:
            if bar.low <= self.stop_loss_price:
                self._execute_exit(bar, self.stop_loss_price, 'StopLoss', fee_pct)
                return True
        
        # For Short: High >= SL
        elif self.state == -1:
            if bar.high >= self.stop_loss_price:
                self._execute_exit(bar, self.stop_loss_price, 'StopLoss', fee_pct)
                return True
            
        return False
        
    def _execute_exit(self, bar, exit_price, reason, fee_pct):
        """ Internal function to close a position and log the trade. """
        
        # Calculate PnL
        if self.state == 1: # Long
            profit_amt = self.position_size * (exit_price - self.entry_price)
            entry_cost = self.position_size * self.entry_price
            exit_value = self.position_size * exit_price
        elif self.state == -1: # Short
            profit_amt = self.position_size * (self.entry_price - exit_price)
            entry_cost = self.position_size * self.entry_price
            exit_value = self.position_size * exit_price
        else:
            return

        # Apply fees
        total_fees = (entry_cost * fee_pct) + (exit_value * fee_pct)
        net_profit_amt = profit_amt - total_fees
        net_profit_pct = (net_profit_amt / entry_cost) * 100 
        
        self.balance += net_profit_amt
        
        # [FIX] Use bar.name instead of bar.Index
        print(f"--- [TRADE CLOSED] ---")
        print(f"     Time: {bar.name}") 
        print(f"     Type: {self.trade_type}")
        print(f"     Reason: {reason}")
        print(f"     Net Pct: {net_profit_pct:.2f}%")
        print(f"     Balance: {self.balance:.2f}")
        
        self.trades_log.append({
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'net_profit_pct': net_profit_pct,
            'exit_reason': reason,
            'type': self.trade_type
        })
        
        self.state = 0
        self.trade_type = None
        self.position_size = 0.0
        self.entry_price = 0.0
        self.stop_loss_price = 0.0

    def handle_entry_signal(self, bar, signal_type, entry_price, stop_loss_price, trade_type):
        """
        Calculates position size and executes a new entry.
        """
        if self.state != 0:
            return 

        # 1. Calculate Risk Per Unit
        if signal_type == 'BUY':
            risk_per_unit = entry_price - stop_loss_price
        elif signal_type == 'SELL':
            risk_per_unit = stop_loss_price - entry_price
        else:
            return

        if risk_per_unit <= 0:
            # [FIX] Use bar.name
            print(f"[Portfolio] WARNING: Invalid risk (SL check failed) at {bar.name}. Skipping.")
            return

        # 2. Calculate Position Size
        risk_per_trade_amount = self.balance * self.risk_pct
        position_size = risk_per_trade_amount / risk_per_unit
        
        self.state = 1 if signal_type == 'BUY' else -1
        self.trade_type = trade_type
        self.position_size = position_size
        self.entry_price = entry_price
        self.stop_loss_price = stop_loss_price
        
        # [FIX] Use bar.name
        print(f"--- [TRADE OPENED] ---")
        print(f"     Time: {bar.name}")
        print(f"     Type: {trade_type} ({signal_type})")
        print(f"     Size: {position_size:.4f}")
        print(f"    Entry: {entry_price:.2f}")
        print(f"       SL: {stop_loss_price:.2f}")

    def update_balance_history(self, bar):
        """ Updates the equity curve at each bar. """
        current_equity = self.balance
        
        # Mark-to-market valuation for open positions
        if self.state == 1: # Long
            unrealized_profit = self.position_size * (bar.close - self.entry_price)
            current_equity += unrealized_profit
        elif self.state == -1: # Short
            unrealized_profit = self.position_size * (self.entry_price - bar.close)
            current_equity += unrealized_profit
        
        # [FIX] Use bar.name for Series index
        self.balance_history.append({
            'timestamp': bar.name, 
            'balance': current_equity
        })