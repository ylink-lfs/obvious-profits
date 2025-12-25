# core/interfaces.py
# Abstract interfaces for trading context
# Both BacktestEngine and LiveEngine implement these interfaces

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from .types import Bar, Order, Position


class IDataFeed(ABC):
    """
    Abstract interface for market data feed.
    Implemented by:
    - backtest/data_loader.py (reads historical CSV/ZIP files)
    - live/data_feed.py (Websocket real-time K-line)
    """
    
    @abstractmethod
    def get_bar(self, symbol: str, timestamp: int) -> Optional[Bar]:
        """Get a single bar at specific timestamp."""
        pass
    
    @abstractmethod
    def get_history(self, symbol: str, lookback: int) -> List[Bar]:
        """Get historical bars for lookback period."""
        pass
    
    @abstractmethod
    def subscribe(self, symbols: List[str]) -> None:
        """Subscribe to market data for symbols (no-op in backtest)."""
        pass


class IOrderManager(ABC):
    """
    Abstract interface for order/position management.
    Implemented by:
    - backtest/portfolio.py (simulated fills with slippage)
    - live/order_manager.py (real API orders)
    """
    
    @abstractmethod
    def buy(self, symbol: str, price: float, size_usd: float) -> Optional[Order]:
        """Place a buy order. Returns Order object."""
        pass
    
    @abstractmethod
    def sell(self, symbol: str, price: float, reason: str = '') -> Optional[Order]:
        """Close position with sell order. Returns Order object."""
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for symbol."""
        pass
    
    @abstractmethod
    def get_all_positions(self) -> Dict[str, Position]:
        """Get all open positions."""
        pass
    
    @abstractmethod
    def can_open_position(self) -> bool:
        """Check if we have capital for new position."""
        pass
    
    @abstractmethod
    def get_balance(self) -> float:
        """Get current account balance."""
        pass


class ITradingContext(ABC):
    """
    Main trading context interface.
    Strategy interacts with this interface, unaware of backtest vs live.
    
    Usage in strategy:
        class MemeStrategy:
            def __init__(self, context: ITradingContext, config):
                self.context = context
            
            def on_bar(self, bar: Bar):
                if self.check_entry_signal(bar):
                    self.context.buy(bar.symbol, bar.close, size)
    """
    
    @abstractmethod
    def get_current_time(self) -> int:
        """
        Get current timestamp in milliseconds.
        - Backtest: returns simulated time from loop
        - Live: returns real system time
        """
        pass
    
    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Get current/latest price for symbol."""
        pass
    
    @abstractmethod
    def get_btc_regime(self) -> Dict[str, Any]:
        """
        Get BTC market regime data for circuit breaker.
        Returns: {
            'roc_1h': float,      # 1-hour change %
            'above_ema': bool,    # Above 24h EMA
            'price': float        # Current BTC price
        }
        """
        pass
    
    @abstractmethod
    def buy(self, symbol: str, price: float, size_usd: float) -> Optional[Order]:
        """Open long position."""
        pass
    
    @abstractmethod
    def sell(self, symbol: str, price: float, reason: str = '') -> Optional[Order]:
        """Close position."""
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol."""
        pass
    
    @abstractmethod
    def get_universe(self) -> List[str]:
        """Get current tradeable universe (top gainers)."""
        pass
    
    @abstractmethod
    def log(self, message: str, level: str = 'INFO') -> None:
        """Log message (console in backtest, file/webhook in live)."""
        pass
