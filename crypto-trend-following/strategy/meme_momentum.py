# strategy/meme_momentum.py
# Meme Coin Momentum Strategy - Entry/Exit Signal Logic

import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass

from .base_strategy import BaseStrategy

if TYPE_CHECKING:
    from core.interfaces import ITradingContext
    from core.types import Bar


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    entry_price: float
    entry_time: pd.Timestamp
    size_usd: float
    size_units: float
    highest_price: float = 0.0  # Track highest price for trailing stop


class MemeStrategy(BaseStrategy):
    """
    Meme Coin Momentum Strategy
    
    Entry Conditions (ALL must be met):
    1. System Circuit Breaker: BTC 1h change > -1.5%
    2. Volatility Breakout: Close > Bollinger Upper Band (20, 2.0)
    3. Volume Confirmation: Volume > 2x Volume_MA(20) AND Close > Open
    4. Relative Strength: Coin 1h change > BTC 1h change
    
    Exit Conditions (ANY triggers exit):
    1. Disaster Stop: Current Low < Entry * 0.96 (-4%)
    2. Structural Exit: Previous Close < Lowest_Low(20 candles)
    3. Time Stop: Holding > 45 min AND profit < 1.5%
    
    Two modes of operation:
    - Context mode: Uses ITradingContext for live trading (on_bar, check_entry_signal, check_exit_signal)
    - Fast mode: Direct numpy calls for backtest performance (*_fast methods)
    """
    
    def __init__(self, config: Dict[str, Any], context: Optional['ITradingContext'] = None):
        """
        Initialize MemeStrategy.
        
        Args:
            config: Strategy configuration dictionary
            context: Optional ITradingContext for live trading mode
        """
        super().__init__(config, context)
        print("[Strategy] Initializing MemeStrategy...")
        
        # Entry parameters
        self.btc_drop_threshold = config['btc_hourly_drop_threshold']
        self.volume_multiplier = config['volume_multiplier']
        self.adx_threshold = config.get('adx_threshold', 25)  # ADX trend filter
        
        # EMA deviation filter parameters
        self.max_ema_deviation = config.get('max_ema_deviation', 0.03)  # Max 3% above EMA60
        
        # Exit parameters
        self.disaster_stop_pct = config['disaster_stop_pct']
        self.time_stop_minutes = config['time_stop_minutes']
        self.time_stop_profit_threshold = config['time_stop_min_profit_pct']
        
        # ATR trailing stop parameters
        self.atr_multiplier = config.get('atr_multiplier', 3.5)  # Chandelier exit multiplier
        
        # Break-even mechanism
        self.breakeven_trigger_pct = config.get('breakeven_trigger_pct', 0.015)  # +1.5% profit
        self.breakeven_stop_offset = config.get('breakeven_stop_offset', 0.001)  # +0.1% above entry
    
    def check_circuit_breaker(self, btc_1h_change: float) -> bool:
        """
        Check if the system circuit breaker is triggered.
        Returns True if safe to trade (circuit breaker NOT triggered).
        """
        return btc_1h_change > self.btc_drop_threshold
    
    # ============================================================
    # FAST METHODS: Pure numpy/float operations for hot loop
    # These avoid pandas Series creation overhead (20-50x faster)
    # ============================================================
    
    def check_entry_signal_fast(
        self,
        prev_close: float,
        prev_open: float,
        prev_high: float,
        prev_volume: float,
        prev_vol_ma: float,
        prev_bb_upper: float,
        prev_adx: float,
        bar_before_prev_high: float,
        coin_1h_change: float,
        btc_1h_change: float,
        btc_above_ema: bool,
        prev_ema_60: float = np.nan
    ) -> bool:
        """
        Fast version of check_entry_signal using scalar floats.
        Avoids pandas overhead inside the hot loop.
        """
        # 0. BTC Regime Filter
        if not btc_above_ema:
            return False
        
        # 1. EMA Deviation Filter: Don't chase overextended moves
        # Close must be < EMA60 * (1 + max_deviation)
        if not np.isnan(prev_ema_60):
            max_price = prev_ema_60 * (1 + self.max_ema_deviation)
            if prev_close > max_price:
                return False  # Too extended above EMA, likely to pullback
        
        # 2. Entry Filter: Close > Prev High (avoid long-wick fake breakouts)
        if not np.isnan(bar_before_prev_high):
            if prev_close <= bar_before_prev_high:
                return False
        
        # 3. Volatility Breakout: Close > BB Upper
        if np.isnan(prev_bb_upper):
            return False
        if prev_close <= prev_bb_upper:
            return False
        
        # 4. Volume Confirmation: Volume > N*MA AND Close > Open
        if np.isnan(prev_vol_ma):
            return False
        if prev_volume <= (prev_vol_ma * self.volume_multiplier):
            return False
        if prev_close <= prev_open:  # Must be green candle
            return False
        
        # 5. ADX Trend Filter
        if not np.isnan(prev_adx):
            if prev_adx <= self.adx_threshold:
                return False
        
        # 6. Relative Strength: Coin outperforming BTC
        if coin_1h_change <= btc_1h_change:
            return False
        
        return True
    
    def check_exit_signal_fast(
        self,
        curr_high: float,
        curr_low: float,
        prev_close: float,
        entry_price: float,
        highest_price: float,
        entry_time_ns: int,
        current_time_ns: int,
        current_atr: float
    ) -> Tuple[bool, str, float]:
        """
        Fast version of check_exit_signal.
        Returns: (should_exit, reason, new_highest_price)
        """
        # Update highest price
        new_highest = max(highest_price, curr_high)
        
        # Intrabar profit check (use high for break-even trigger)
        intrabar_profit_pct = (curr_high - entry_price) / entry_price
        
        # Calculate minutes held for grace period logic
        mins_held = (current_time_ns - entry_time_ns) / 60_000_000_000  # ns to minutes
        
        # Grace period: first 60 mins - give position breathing room
        # Only use hard disaster stop, no trailing stop to avoid shake-outs
        trailing_stop_active = mins_held >= 60
        
        # 1. Disaster / BreakEven Stop (always active)
        if intrabar_profit_pct >= self.breakeven_trigger_pct:
            # Break-even triggered: protect capital
            stop_price = entry_price * (1 + self.breakeven_stop_offset)
            if curr_low < stop_price:
                return True, 'BreakEven', new_highest
        else:
            # Disaster stop
            stop_price = entry_price * (1 - self.disaster_stop_pct)
            if curr_low < stop_price:
                return True, 'DisasterStop', new_highest
        
        # 2. ATR Trailing Stop (only after grace period)
        if trailing_stop_active and current_atr > 0 and not np.isnan(current_atr):
            trailing_stop = new_highest - (self.atr_multiplier * current_atr)
            if prev_close < trailing_stop:
                return True, 'TrailingStop', new_highest
        
        # 3. Time Stop: HARD exit after N minutes (regardless of profit)
        if mins_held > self.time_stop_minutes:
            # Hard time stop: Meme coins either moon fast or die slow
            return True, 'TimeStop', new_highest
        
        return False, '', new_highest

    # ============================================================
    # ABSTRACT METHOD IMPLEMENTATIONS (BaseStrategy interface)
    # These are used in live trading mode with ITradingContext
    # ============================================================
    
    def on_bar(self, symbol: str, bar: 'Bar') -> None:
        """
        Process a new bar for the given symbol.
        Called by the trading context (live engine) for each new bar.
        
        In live mode, this is the main entry point for strategy logic.
        """
        if self.context is None:
            raise RuntimeError("on_bar requires ITradingContext. Use *_fast methods for backtest.")
        
        # Get BTC regime for circuit breaker
        btc_regime = self.context.get_btc_regime()
        
        # Check circuit breaker first
        if not self.check_circuit_breaker(btc_regime['roc_1h']):
            return  # Circuit breaker triggered, don't trade
        
        # Check if we have a position
        position = self.context.get_position(symbol)
        
        if position is not None:
            # Check exit signal
            should_exit, reason = self.check_exit_signal(symbol, bar)
            if should_exit:
                self.context.sell(symbol, bar.close, reason)
        else:
            # Check entry signal
            if self.check_entry_signal(symbol, bar):
                position_size = self.config.get('position_size_usd', 500)
                self.context.buy(symbol, bar.close, position_size)
    
    def check_entry_signal(self, symbol: str, bar: 'Bar') -> bool:
        """
        Check if entry conditions are met using ITradingContext.
        
        Note: This is a simplified version for live trading.
        The full logic with all indicators should be computed by the context
        and passed via the bar object or fetched from the data feed.
        """
        if self.context is None:
            raise RuntimeError("check_entry_signal requires ITradingContext. Use check_entry_signal_fast for backtest.")
        
        # In live mode, bar should contain pre-computed indicators
        # The live engine is responsible for computing these
        btc_regime = self.context.get_btc_regime()
        
        # Delegate to the pandas-based method if bar is a Series
        if hasattr(bar, 'close'):
            # Assume bar has necessary indicator fields
            return self._check_entry_from_bar(bar, btc_regime)
        
        return False
    
    def _check_entry_from_bar(self, bar: 'Bar', btc_regime: Dict[str, Any]) -> bool:
        """Helper to check entry from a bar with indicators."""
        # This would need the bar to have bb_upper, volume_ma, adx, etc.
        # For now, return False - live engine should use check_entry_signal_fast
        # with pre-extracted float values for consistency
        return False
    
    def check_exit_signal(self, symbol: str, bar: 'Bar') -> Tuple[bool, str]:
        """
        Check if exit conditions are met using ITradingContext.
        
        Returns:
            Tuple of (should_exit, reason)
        """
        if self.context is None:
            raise RuntimeError("check_exit_signal requires ITradingContext. Use check_exit_signal_fast for backtest.")
        
        position = self.context.get_position(symbol)
        if position is None:
            return False, ''
        
        # Get current time from context
        current_time_ms = self.context.get_current_time()
        current_time_ns = current_time_ms * 1_000_000  # Convert ms to ns
        
        # Extract position data (assuming core.types.Position structure)
        entry_price = position.entry_price
        entry_time_ns = position.entry_time  # Assuming stored as ns or convert
        highest_price = getattr(position, 'highest_price', entry_price)
        
        # Get ATR from bar if available, else use 0
        current_atr = getattr(bar, 'atr', 0.0)
        
        # Delegate to fast method
        should_exit, reason, _ = self.check_exit_signal_fast(
            curr_high=bar.high,
            curr_low=bar.low,
            prev_close=bar.close,  # Using current close as prev for simplicity
            entry_price=entry_price,
            highest_price=highest_price,
            entry_time_ns=entry_time_ns,
            current_time_ns=current_time_ns,
            current_atr=current_atr
        )
        
        return should_exit, reason
