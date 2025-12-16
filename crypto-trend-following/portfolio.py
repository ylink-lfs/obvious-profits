# portfolio.py
# Meme Coin Strategy Portfolio Management
# Handles position sizing, trade execution, and PnL tracking

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import pandas as pd


@dataclass
class Trade:
    """Completed trade record."""
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    size_usd: float
    size_units: float
    pnl_usd: float
    pnl_pct: float
    exit_reason: str
    fees_paid: float


class MemePortfolio:
    """
    Portfolio manager for meme coin strategy.
    
    Features:
    - Fixed position sizing (500 USD per trade)
    - Fee and slippage handling
    - Trade logging and balance tracking
    """
    
    def __init__(self, config):
        print("[Portfolio] Initializing MemePortfolio...")
        self.config = config
        
        self.initial_capital = config['initial_capital']
        self.position_size_usd = config['position_size_usd']
        self.fee_rate = config['fee_rate']
        self.slippage_rate = config['slippage_rate']
        
        # Current state
        self.balance = self.initial_capital
        self.positions: Dict[str, Any] = {}  # symbol -> Position
        
        # History
        self.trades_log: List[Trade] = []
        self.balance_history: List[Dict] = []
    
    def can_open_position(self) -> bool:
        """Check if we have enough capital for a new position."""
        return self.balance >= self.position_size_usd
    
    def has_position(self, symbol: str) -> bool:
        """Check if we have an open position for this symbol."""
        return symbol in self.positions
    
    def get_position(self, symbol: str) -> Optional[Any]:
        """Get position for a symbol if exists."""
        return self.positions.get(symbol)
    
    def open_position(
        self,
        symbol: str,
        entry_price: float,
        entry_time: pd.Timestamp
    ) -> bool:
        """
        Open a new position.
        
        Args:
            symbol: Contract symbol
            entry_price: Entry price (already includes slippage)
            entry_time: Entry timestamp
            
        Returns:
            True if position was opened successfully
        """
        if not self.can_open_position():
            print("[Portfolio] Cannot open position: insufficient balance")
            return False
        
        if self.has_position(symbol):
            print(f"[Portfolio] Cannot open position: already have {symbol}")
            return False
        
        # Calculate position size
        size_usd = self.position_size_usd
        size_units = size_usd / entry_price
        
        # Deduct entry fee and position capital from balance
        entry_fee = size_usd * self.fee_rate
        self.balance -= size_usd  # Lock the capital for the position
        
        # Create position
        from strategy.meme_momentum import Position
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            entry_time=entry_time,
            size_usd=size_usd,
            size_units=size_units
        )
        
        self.positions[symbol] = position
        
        print("--- [TRADE OPENED] ---")
        print(f"     Symbol: {symbol}")
        print(f"     Time: {entry_time}")
        print(f"     Price: {entry_price:.6f}")
        print(f"     Size: {size_units:.4f} units (${size_usd})")
        print(f"     Fee: ${entry_fee:.4f}")
        
        return True
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_time: pd.Timestamp,
        exit_reason: str
    ) -> Optional[Trade]:
        """
        Close an existing position.
        
        Args:
            symbol: Contract symbol
            exit_price: Exit price (already includes slippage)
            exit_time: Exit timestamp
            exit_reason: Reason for exit
            
        Returns:
            Trade record if successful, None otherwise
        """
        if not self.has_position(symbol):
            return None
        
        position = self.positions[symbol]
        
        # Calculate PnL
        price_change = exit_price - position.entry_price
        gross_pnl = position.size_units * price_change
        
        # Calculate fees (entry + exit)
        entry_value = position.size_usd
        exit_value = position.size_units * exit_price
        total_fees = (entry_value * self.fee_rate) + (exit_value * self.fee_rate)
        
        # Net PnL
        net_pnl = gross_pnl - total_fees
        pnl_pct = (net_pnl / position.size_usd) * 100
        
        # Update balance: add back the locked capital plus net PnL
        self.balance += position.size_usd + net_pnl
        
        # Create trade record
        trade = Trade(
            symbol=symbol,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size_usd=position.size_usd,
            size_units=position.size_units,
            pnl_usd=net_pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            fees_paid=total_fees
        )
        
        self.trades_log.append(trade)
        
        # Remove position
        del self.positions[symbol]
        
        print("--- [TRADE CLOSED] ---")
        print(f"     Symbol: {symbol}")
        print(f"     Time: {exit_time}")
        print(f"     Reason: {exit_reason}")
        print(f"     Entry: {position.entry_price:.6f}")
        print(f"     Exit: {exit_price:.6f}")
        print(f"     PnL: ${net_pnl:.2f} ({pnl_pct:.2f}%)")
        print(f"     Balance: ${self.balance:.2f}")
        
        return trade
    
    def update_balance_history(self, timestamp: pd.Timestamp, current_prices: Dict[str, float]):
        """
        Update balance history with current equity (including unrealized PnL).
        
        Args:
            timestamp: Current timestamp
            current_prices: Dict of symbol -> current price
        """
        equity = self.balance
        
        # Add current value of open positions (capital is already deducted from balance)
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                current_price = current_prices[symbol]
                # Position value at current price
                current_value = position.size_units * current_price
                equity += current_value
            else:
                # If no current price, use entry value
                equity += position.size_usd
        
        self.balance_history.append({
            'timestamp': timestamp,
            'balance': equity,
            'open_positions': len(self.positions)
        })
    
    def get_summary(self) -> Dict:
        """Get portfolio summary statistics."""
        if not self.trades_log:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'final_balance': self.balance
            }
        
        wins = sum(1 for t in self.trades_log if t.pnl_usd > 0)
        total = len(self.trades_log)
        total_pnl = sum(t.pnl_usd for t in self.trades_log)
        
        return {
            'total_trades': total,
            'win_rate': (wins / total) * 100,
            'total_pnl': total_pnl,
            'final_balance': self.balance,
            'return_pct': ((self.balance - self.initial_capital) / self.initial_capital) * 100
        }