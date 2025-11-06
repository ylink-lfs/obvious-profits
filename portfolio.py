# portfolio.py
# [MODIFIED] Upgraded to handle symmetrical trend exits.

import numpy as np

class Portfolio:
    """
    Handles all capital, risk, and position management.
    [MODIFIED] Now handles Long (1), Short (-1), and Flat (0) states.
    """
    def __init__(self, config):
        print("[Portfolio] Initializing Portfolio...")
        self.config = config
        self.balance = self.config['initial_capital']
        self.risk_pct = self.config['risk_per_trade_percent']
        
        # State: 0 = FLAT, 1 = LONG, -1 = SHORT
        self.state = 0
        self.position_size = 0.0 # In units (e.g., 1.5 BTC)
        self.entry_price = 0.0
        self.stop_loss_price = 0.0
        
        self.trades_log = []
        self.balance_history = []

    def check_for_exit(self, bar, fee_pct=0.001):
        """
        Checks exit conditions (SL or Trend) for an open position.
        Returns True if a trade was closed.
        """
        if self.state == 0:
            return False

        # --- Check LONG position exits ---
        if self.state == 1:
            # 1. Check for Stop Loss
            if bar.low <= self.stop_loss_price:
                exit_price = self.stop_loss_price
                self._execute_exit(bar, exit_price, 'StopLoss', fee_pct)
                return True
                
            # 2. Check for Trend Exit (Daily Exit Signal)
            if bar.DAILY_EXIT_SIGNAL == True:
                exit_price = bar.close 
                self._execute_exit(bar, exit_price, 'TrendExit', fee_pct)
                return True
        
        # --- [MODIFIED] Check SHORT position exits ---
        elif self.state == -1:
            # 1. Check for Stop Loss (price moved AGAINST us)
            if bar.high >= self.stop_loss_price:
                exit_price = self.stop_loss_price
                self._execute_exit(bar, exit_price, 'StopLoss', fee_pct)
                return True
            
            # 2. [MODIFIED] Check for Trend Exit (Daily COVER Signal)
            if bar.DAILY_COVER_SIGNAL == True:
                exit_price = bar.close
                self._execute_exit(bar, exit_price, 'TrendExit', fee_pct)
                return True
            
        return False
        
    def _execute_exit(self, bar, exit_price, reason, fee_pct):
        """ Internal function to close a position and log the trade. """
        
        # Calculate PnL
        if self.state == 1: # Long
            profit_amt = self.position_size * (exit_price - self.entry_price)
            entry_cost = self.position_size * self.entry_price
            exit_value = self.position_size * exit_price
            trade_type = 'Long'
        elif self.state == -1: # Short
            profit_amt = self.position_size * (self.entry_price - exit_price)
            entry_cost = self.position_size * self.entry_price # Cost is still based on entry
            exit_value = self.position_size * exit_price
            trade_type = 'Short'
        else:
            return # Should not happen

        # Apply fees (on entry and exit)
        total_fees = (entry_cost * fee_pct) + (exit_value * fee_pct)
        
        net_profit_amt = profit_amt - total_fees
        net_profit_pct = (net_profit_amt / entry_cost) * 100 # Net Pct
        
        # Update balance
        self.balance += net_profit_amt
        
        print(f"--- [TRADE CLOSED] ---")
        print(f"     Time: {bar.Index}")
        print(f"     Type: {trade_type}")
        print(f"     Reason: {reason}")
        print(f"     Net Pct: {net_profit_pct:.2f}%")
        print(f"     Balance: {self.balance:.2f}")
        
        # Log trade
        self.trades_log.append({
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'net_profit_pct': net_profit_pct,
            'exit_reason': reason,
            'type': trade_type
        })
        
        # Reset state
        self.state = 0
        self.position_size = 0.0
        self.entry_price = 0.0
        self.stop_loss_price = 0.0

    def handle_entry_signal(self, bar, signal_type, entry_price, stop_loss_price):
        """
        Calculates position size and executes a new entry (Long or Short).
        """
        if self.state != 0:
            return # Already in a position

        # 1. Calculate Risk Per Unit
        if signal_type == 'BUY':
            risk_per_unit = entry_price - stop_loss_price
        elif signal_type == 'SELL':
            risk_per_unit = stop_loss_price - entry_price
        else:
            return

        if risk_per_unit <= 0:
            print(f"[Portfolio] ERROR: Invalid risk per unit (SL check failed). Skipping trade.")
            return

        # 2. Calculate Position Size
        risk_per_trade_amount = self.balance * self.risk_pct
        position_size = risk_per_trade_amount / risk_per_unit
        
        # 3. Set position state
        self.state = 1 if signal_type == 'BUY' else -1
        self.position_size = position_size
        self.entry_price = entry_price
        self.stop_loss_price = stop_loss_price
        
        print(f"--- [TRADE OPENED] ---")
        print(f"     Time: {bar.Index}")
        print(f"     Type: {'LONG' if self.state == 1 else 'SHORT'}")
        print(f"     Size: {position_size:.4f} units")
        print(f"    Entry: {entry_price:.2f}")
        print(f"       SL: {stop_loss_price:.2f}")

    def update_balance_history(self, bar):
        """ Updates the equity curve at each bar. """
        current_equity = self.balance
        if self.state == 1: # Long
            unrealized_profit = self.position_size * (bar.close - self.entry_price)
            current_equity += unrealized_profit
        elif self.state == -1: # Short
            unrealized_profit = self.position_size * (self.entry_price - bar.close)
            current_equity += unrealized_profit
        
        self.balance_history.append({
            'timestamp': bar.Index,
            'balance': current_equity
        })