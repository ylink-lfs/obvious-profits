# strategy/base_strategy.py
# Base Strategy class that all strategies inherit from
# Uses ITradingContext interface for backtest/live compatibility

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.interfaces import ITradingContext
    from core.types import Bar


class BaseStrategy(ABC):
    """
    Base class for all trading strategies.
    
    Strategies inherit from this class and implement the abstract methods.
    The strategy interacts with the trading context (ITradingContext) which
    abstracts away whether we're running in backtest or live mode.
    
    Two modes of operation:
    1. Context mode (live trading): Strategy uses ITradingContext for all operations
    2. Fast mode (backtest): Strategy exposes *_fast() methods for direct numpy calls
    
    Usage (Context mode - Live):
        class MemeStrategy(BaseStrategy):
            def on_bar(self, symbol: str, bar: Bar) -> None:
                if self.check_entry_signal(symbol, bar):
                    self.context.buy(symbol, bar.close, self.position_size)
    
    Usage (Fast mode - Backtest):
        strategy = MemeStrategy(config=CONFIG)  # No context
        if strategy.check_entry_signal_fast(...float args...):
            portfolio.open_position(...)
    """
    
    def __init__(self, config: Dict[str, Any], context: Optional['ITradingContext'] = None):
        """
        Initialize strategy with configuration and optional trading context.
        
        Args:
            config: Strategy configuration dictionary
            context: ITradingContext implementation (BacktestEngine or LiveEngine)
                     None for backtest fast mode where engine calls *_fast() methods directly
        """
        self.config = config
        self.context = context
        self.name = self.__class__.__name__
    
    @abstractmethod
    def on_bar(self, symbol: str, bar: 'Bar') -> None:
        """
        Called when a new bar is received for a symbol.
        Strategy should implement entry/exit logic here.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            bar: OHLCV bar data
        """
        pass
    
    @abstractmethod
    def check_entry_signal(self, symbol: str, bar: 'Bar') -> bool:
        """
        Check if entry conditions are met.
        
        Args:
            symbol: Trading pair symbol
            bar: Current bar data
            
        Returns:
            True if entry signal is triggered
        """
        pass
    
    @abstractmethod
    def check_exit_signal(self, symbol: str, bar: 'Bar') -> tuple[bool, str]:
        """
        Check if exit conditions are met for an existing position.
        
        Args:
            symbol: Trading pair symbol
            bar: Current bar data
            
        Returns:
            Tuple of (should_exit: bool, reason: str)
        """
        pass
    
    def on_start(self) -> None:
        """
        Called when strategy starts.
        Override for initialization logic.
        """
        pass
    
    def on_stop(self) -> None:
        """
        Called when strategy stops.
        Override for cleanup logic.
        """
        pass
    
    def on_position_opened(self, symbol: str, price: float, size: float) -> None:
        """
        Called when a new position is opened.
        Override to add custom logic after entry.
        
        Args:
            symbol: Trading pair symbol
            price: Entry price
            size: Position size in USD
        """
        pass
    
    def on_position_closed(self, symbol: str, entry_price: float, 
                           exit_price: float, pnl: float, reason: str) -> None:
        """
        Called when a position is closed.
        Override to add custom logic after exit.
        
        Args:
            symbol: Trading pair symbol
            entry_price: Entry price
            exit_price: Exit price
            pnl: Realized P&L
            reason: Exit reason
        """
        pass
    
    def log(self, message: str, level: str = 'INFO') -> None:
        """
        Log a message through the trading context.
        
        Args:
            message: Log message
            level: Log level ('INFO', 'WARNING', 'ERROR')
        """
        self.context.log(f"[{self.name}] {message}", level)
