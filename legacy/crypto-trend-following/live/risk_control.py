# live/risk_control.py
# Risk Control - Trading limits and circuit breakers (skeleton)
#
# This will handle:
# - Daily loss limits
# - Per-symbol trade limits
# - Global circuit breakers
# - Position sizing validation

from typing import Dict, Optional
from datetime import datetime, date


class RiskControl:
    """
    Risk control for live trading.
    Enforces trading limits and circuit breakers.
    
    SKELETON - To be implemented with actual risk logic.
    """
    
    def __init__(self, config):
        print("[RiskControl] Initializing RiskControl (SKELETON)...")
        self.config = config
        
        # Daily limits
        self.max_daily_loss = config.get('max_daily_loss', 100)  # USD
        self.max_daily_trades = config.get('max_daily_trades', 10)
        self.max_daily_trades_per_symbol = config.get('max_daily_trades_per_symbol', 1)
        
        # Position limits
        self.max_position_size = config.get('max_position_size', 500)  # USD
        self.max_open_positions = config.get('max_open_positions', 5)
        
        # Daily tracking
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_trades_by_symbol: Dict[str, int] = {}
        self.last_reset_date: date = date.today()
        
        print("[RiskControl] WARNING: This is a skeleton - no real risk controls active!")
    
    def can_trade(self, symbol: str, size_usd: float) -> tuple[bool, str]:
        """
        Check if a trade is allowed by risk controls.
        
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        self._maybe_reset_daily()
        
        # Check daily loss limit
        if self.daily_pnl <= -self.max_daily_loss:
            return False, f"Daily loss limit reached: ${abs(self.daily_pnl):.2f}"
        
        # Check daily trade count
        if self.daily_trades >= self.max_daily_trades:
            return False, f"Daily trade limit reached: {self.daily_trades}"
        
        # Check per-symbol daily limit
        symbol_trades = self.daily_trades_by_symbol.get(symbol, 0)
        if symbol_trades >= self.max_daily_trades_per_symbol:
            return False, f"Daily limit for {symbol} reached: {symbol_trades}"
        
        # Check position size
        if size_usd > self.max_position_size:
            return False, f"Position size ${size_usd:.2f} exceeds max ${self.max_position_size}"
        
        return True, ""
    
    def record_trade(self, symbol: str, pnl: float):
        """Record a completed trade."""
        self._maybe_reset_daily()
        
        self.daily_pnl += pnl
        self.daily_trades += 1
        self.daily_trades_by_symbol[symbol] = self.daily_trades_by_symbol.get(symbol, 0) + 1
    
    def _maybe_reset_daily(self):
        """Reset daily counters if it's a new day."""
        today = date.today()
        if today != self.last_reset_date:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.daily_trades_by_symbol = {}
            self.last_reset_date = today
    
    def is_circuit_breaker_triggered(self) -> bool:
        """Check if global circuit breaker is triggered."""
        return self.daily_pnl <= -self.max_daily_loss
    
    def get_daily_summary(self) -> Dict:
        """Get daily risk metrics summary."""
        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'trades_by_symbol': dict(self.daily_trades_by_symbol),
            'loss_limit_remaining': self.max_daily_loss + self.daily_pnl,
            'trades_remaining': self.max_daily_trades - self.daily_trades
        }
