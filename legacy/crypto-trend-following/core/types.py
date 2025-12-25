# core/types.py
# Common data structures shared between backtest and live trading

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd


class OrderSide(Enum):
    """Order side: BUY or SELL."""
    BUY = 'BUY'
    SELL = 'SELL'


class OrderType(Enum):
    """Order type."""
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'


class OrderStatus(Enum):
    """Order status."""
    PENDING = 'PENDING'
    FILLED = 'FILLED'
    CANCELLED = 'CANCELLED'
    REJECTED = 'REJECTED'


@dataclass
class Bar:
    """
    Single OHLCV bar.
    Unified structure for both backtest (from CSV) and live (from Websocket).
    """
    symbol: str
    timestamp: int  # milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0
    
    # Optional pre-calculated indicators (set by data loader)
    bb_upper: Optional[float] = None
    adx: Optional[float] = None
    atr: Optional[float] = None
    volume_ma: Optional[float] = None
    ema_60: Optional[float] = None
    roc_1h: Optional[float] = None


@dataclass
class Order:
    """
    Order object representing a trading order.
    """
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: float
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float = 0.0
    filled_quantity: float = 0.0
    timestamp: int = 0  # Creation time in ms
    fill_timestamp: int = 0  # Fill time in ms
    fees: float = 0.0


@dataclass
class Position:
    """
    Open position.
    Compatible with existing strategy/meme_momentum.py Position class.
    """
    symbol: str
    entry_price: float
    entry_time: pd.Timestamp
    size_usd: float
    size_units: float
    highest_price: float = 0.0  # For trailing stop
    
    def update_highest(self, current_high: float) -> None:
        """Update highest price for trailing stop."""
        self.highest_price = max(self.highest_price, current_high)


@dataclass
class Trade:
    """
    Completed trade record.
    Compatible with existing portfolio.py Trade class.
    """
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


@dataclass
class BtcRegime:
    """
    BTC market regime for circuit breaker decisions.
    """
    timestamp: int
    price: float
    roc_1h: float  # 1-hour change percentage
    above_ema_24h: bool  # Price above 24h EMA
    
    def is_safe_to_trade(self, drop_threshold: float = -0.015) -> bool:
        """
        Check if it's safe to trade meme coins.
        Returns False if BTC dropping hard or in downtrend.
        """
        return self.roc_1h > drop_threshold and self.above_ema_24h
