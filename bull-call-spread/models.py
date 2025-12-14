# Models for Squeeze Entry Options Strategy
from AlgorithmImports import *
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

import config


class CustomOptionFeeModel(FeeModel):
    """Custom fee model for options trading."""
    
    def __init__(self, commission_per_contract: float = 0.45, 
                 minimum_commission: float = 1.49,
                 platform_fee_per_order: float = 0.54):
        self.commission_per_contract = commission_per_contract
        self.minimum_commission = minimum_commission
        self.platform_fee_per_order = platform_fee_per_order
    
    def get_order_fee(self, parameters: OrderFeeParameters) -> OrderFee:
        """Calculate the fee for an option order."""
        order = parameters.order
        quantity = abs(order.quantity)
        commission = max(self.minimum_commission, quantity * self.commission_per_contract)
        total_fee = commission + self.platform_fee_per_order
        return OrderFee(CashAmount(total_fee, "USD"))


@dataclass
class SymbolData:
    """Stores indicator data and historical values for a symbol."""
    symbol: str
    equity_symbol: object = None
    option_symbol: object = None
    
    # Indicators
    rsi: object = None
    sma20: object = None
    sma200: object = None
    bb: object = None  # Bollinger Bands
    atr_short: object = None  # 5-day ATR
    atr_long: object = None   # 20-day ATR
    
    # IV indicator (for calculating IV Percentile)
    iv_indicator: object = None  # ImpliedVolatility indicator
    
    # Historical data for BB width percentile
    bb_width_history: List[float] = field(default_factory=list)
    
    # Historical IV data for IV Percentile calculation (252 trading days = ~1 year)
    iv_history: List[float] = field(default_factory=list)
    
    # Previous day data
    prev_close: float = 0
    prev_high: float = 0
    prev_rsi: float = 0
    
    # IV Percentile calculated from historical IV (52-week lookback)
    iv_percentile: float = 0.5  # Default to middle if not enough data
    current_iv: float = 0
    
    def get_bb_width(self) -> float:
        """Calculate current Bollinger Band width."""
        if self.bb is None or not self.bb.is_ready:
            return 0
        upper = self.bb.upper_band.current.value
        lower = self.bb.lower_band.current.value
        middle = self.bb.middle_band.current.value
        if middle == 0:
            return 0
        return (upper - lower) / middle
    
    def get_bb_width_percentile(self, lookback: int = 90) -> float:
        """Calculate percentile of current BB width over lookback period."""
        if len(self.bb_width_history) < lookback:
            return 100  # Not enough data, return high percentile to avoid triggering
        
        current_width = self.get_bb_width()
        recent_widths = self.bb_width_history[-lookback:]
        count_below = sum(1 for w in recent_widths if w < current_width)
        return (count_below / len(recent_widths)) * 100
    
    def is_close_near_ma20(self, threshold: float = 0.02) -> bool:
        """Check if previous close is within threshold of MA20."""
        if self.sma20 is None or not self.sma20.is_ready:
            return False
        ma20_val = self.sma20.current.value
        if ma20_val == 0:
            return False
        distance = abs(self.prev_close - ma20_val) / ma20_val
        return distance < threshold
    
    def is_atr_contracting(self) -> bool:
        """Check if recent ATR is less than longer-term ATR."""
        if self.atr_short is None or self.atr_long is None:
            return False
        if not self.atr_short.is_ready or not self.atr_long.is_ready:
            return False
        return self.atr_short.current.value < self.atr_long.current.value
    
    def is_above_ma200(self) -> bool:
        """Check if previous close is above MA200."""
        if self.sma200 is None or not self.sma200.is_ready:
            return False
        return self.prev_close > self.sma200.current.value
    
    def is_rsi_in_range(self, rsi_min: float, rsi_max: float) -> bool:
        """Check if RSI is within the specified range."""
        if self.rsi is None or not self.rsi.is_ready:
            return False
        rsi_val = self.rsi.current.value
        return rsi_min <= rsi_val <= rsi_max
    
    def get_bollinger_upper(self) -> float:
        """Get the upper Bollinger Band value."""
        if self.bb is None or not self.bb.is_ready:
            return float('inf')
        return self.bb.upper_band.current.value
    
    def update_iv(self, iv_value: float):
        """
        Update current IV and add to history for IV Percentile calculation.
        
        Args:
            iv_value: Current implied volatility value
        """
        if iv_value <= 0:
            return
        
        self.current_iv = iv_value
        self.iv_history.append(iv_value)
        
        # Keep only configured lookback period
        lookback = config.IV_PERCENTILE_LOOKBACK
        if len(self.iv_history) > lookback:
            self.iv_history = self.iv_history[-lookback:]
        
        # Recalculate IV Percentile
        self._calculate_iv_percentile()
    
    def _calculate_iv_percentile(self):
        """
        Calculate IV Percentile based on 52-week (252 trading days) historical IV data.
        
        IV Percentile = Percentage of days in the past year where IV was lower than current IV
        
        For example, if current IV is higher than 80% of the historical values,
        the IV Percentile is 0.80 (80%).
        
        Returns value between 0 and 1 (0% to 100%)
        """
        if len(self.iv_history) < 20:  # Need at least 20 days of data
            self.iv_percentile = 0.5  # Default to middle if not enough data
            return
        
        # Count how many days in the 52-week history had IV lower than current IV
        count_below = sum(1 for iv in self.iv_history if iv < self.current_iv)
        
        # Calculate percentile using full history (up to 252 days)
        self.iv_percentile = count_below / len(self.iv_history)
    
    def get_iv_percentile(self) -> float:
        """Get current IV Percentile (0 to 1 scale, representing 0% to 100%)."""
        return self.iv_percentile
    
    def has_valid_iv_data(self) -> bool:
        """Check if we have enough IV data to calculate a meaningful IV Percentile."""
        return len(self.iv_history) >= 20


@dataclass
class SqueezePosition:
    """Represents an active squeeze spread position."""
    symbol: str
    entry_date: datetime
    entry_price: float
    
    # Option contracts
    long_call_symbol: object = None
    long_call_strike: float = 0
    long_call_quantity: int = 0
    
    short_call_symbol: object = None
    short_call_strike: float = 0
    short_call_quantity: int = 0
    
    # Cost basis
    total_premium_paid: float = 0
    total_premium_received: float = 0
    
    # Rally exit state tracking
    # Once price crosses max profit boundary, this flag is set to True
    # and subsequent exit conditions are checked until position is closed
    price_crossed_max_profit: bool = False
    
    def get_max_profit_price(self) -> float:
        """Calculate the price level for maximum profit potential.
        
        This is the price above which the position reaches max profit:
        Long strike + (Long strike - Short strike)
        """
        return self.long_call_strike + (self.long_call_strike - self.short_call_strike)
    
    def get_stop_loss_price(self) -> float:
        """Calculate the stop loss price level.
        
        Exit if price < 0.95 * short strike
        """
        return 0.95 * self.short_call_strike
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date,
            "entry_price": self.entry_price,
            "long_call_symbol": self.long_call_symbol,
            "long_call_strike": self.long_call_strike,
            "long_call_quantity": self.long_call_quantity,
            "short_call_symbol": self.short_call_symbol,
            "short_call_strike": self.short_call_strike,
            "short_call_quantity": self.short_call_quantity,
            "total_premium_paid": self.total_premium_paid,
            "total_premium_received": self.total_premium_received,
            "price_crossed_max_profit": self.price_crossed_max_profit,
        }


@dataclass
class EntryCandidate:
    """Represents a potential entry candidate with ranking score."""
    symbol: str
    symbol_data: SymbolData
    iv_percentile: float
    bb_width: float
    score: float  # IV Percentile * BB Width - lower is better
    
    @classmethod
    def create(cls, symbol: str, symbol_data: SymbolData):
        iv_percentile = symbol_data.iv_percentile
        bb_width = symbol_data.get_bb_width()
        score = iv_percentile * bb_width
        return cls(
            symbol=symbol,
            symbol_data=symbol_data,
            iv_percentile=iv_percentile,
            bb_width=bb_width,
            score=score
        )
