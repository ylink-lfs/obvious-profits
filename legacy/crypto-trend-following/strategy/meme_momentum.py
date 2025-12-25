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
    side: str = 'LONG'  # 'LONG' or 'SHORT'
    highest_price: float = 0.0  # Track highest price for LONG trailing stop
    lowest_price: float = float('inf')  # Track lowest price for SHORT trailing stop


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
        prev_ema_60: float = np.nan,
        trade_direction: str = 'LONG',
        listing_time_ms: int = 0,
        current_time_ms: int = 0,
        listing_high_15m: float = 0.0,
        prev_ema_20: float = np.nan,
        prev_vwap: float = np.nan,
        prev_rsi: float = np.nan
    ) -> bool:
        """
        Fast version of check_entry_signal using scalar floats.
        Avoids pandas overhead inside the hot loop.
        
        Supports LONG (breakout), SHORT (reversion), and Day-1 Listing modes.
        """
        # =======================
        # [Day-1 Listing Mode] Strong Filter Channel
        # =======================
        # If listing_time is provided and coin is within Day-1 window
        if listing_time_ms > 0 and current_time_ms > 0:
            age_hours = (current_time_ms - listing_time_ms) / 3600_000
            day1_window = self.config.get('day1_listing_window_hours', 24)
            
            if 0 <= age_hours < day1_window:
                # 1. Opening volatility wait period (60 min)
                wait_mins = self.config.get('day1_wait_minutes', 60)
                if age_hours * 60 < wait_mins:
                    return False
                
                # 2. [3% Moat Filter] Must break above ORB high + 3% buffer
                # Only enter on strong body candle breakouts
                if listing_high_15m > 0:
                    breakout_buffer = self.config.get('day1_breakout_buffer', 0.03)
                    breakout_threshold = listing_high_15m * (1 + breakout_buffer)
                    if prev_close <= breakout_threshold:
                        return False
                
                # 3. [2x Volume Confirmation] Strict mode - require volume data
                # Must have 2x average volume for valid breakout
                vol_factor = self.config.get('day1_volume_factor', 2.0)
                if np.isnan(prev_vol_ma) or prev_vol_ma <= 0:
                    return False  # No volume data = No trade
                if prev_volume < prev_vol_ma * vol_factor:
                    return False
                
                # 4. Conditional Buy: All filters passed
                return prev_close > 0
        
        # =======================
        # [LONG Logic] Original breakout strategy
        # =======================
        if trade_direction == 'LONG':
            # 0. BTC Regime Filter
            if not btc_above_ema:
                return False
            
            # 1. EMA Deviation Filter: Don't chase overextended moves
            if not np.isnan(prev_ema_60):
                max_price = prev_ema_60 * (1 + self.max_ema_deviation)
                if prev_close > max_price:
                    return False
            
            # 2. Entry Filter: Close > Prev High
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
        
        # =======================
        # [SHORT Logic] Sniper Butcher Strategy v2
        # =======================
        elif trade_direction == 'SHORT':
            # Logic: Short pumped coins with "piercing" breakdown confirmation
            # Key: Must be a real breakdown candle, not just drifting below EMA
            
            # 1. Must be "pumped" context - price above long-term EMA 60
            # This means the coin had a pump, there are bag holders above
            if np.isnan(prev_ema_60) or prev_close < prev_ema_60:
                return False
            
            # 2. [Critical] Piercing Breakdown: Candle must CROSS the EMA 20
            # Open ABOVE EMA 20, Close BELOW EMA 20 AND VWAP
            # This is a real "air pocket" signal, not weak drift
            if np.isnan(prev_ema_20) or np.isnan(prev_vwap):
                return False
            
            is_piercing = (prev_open > prev_ema_20) and \
                          (prev_close < prev_ema_20) and \
                          (prev_close < prev_vwap)
            if not is_piercing:
                return False
            
            # 3. Red candle confirmation (real selling pressure)
            is_red_candle = prev_close < prev_open
            if not is_red_candle:
                return False
            
            # 4. RSI filter: Don't short oversold (risk of bounce)
            if not np.isnan(prev_rsi):
                if prev_rsi < 40:  # Already oversold, skip
                    return False
            
            return True
        
        return False
    
    def check_exit_signal_fast(
        self,
        curr_high: float,
        curr_low: float,
        prev_close: float,
        entry_price: float,
        highest_price: float,
        entry_time_ns: int,
        current_time_ns: int,
        current_atr: float,
        lowest_price: float = float('inf'),
        side: str = 'LONG',
        listing_time_ms: int = 0,
        current_time_ms: int = 0
    ) -> Tuple[bool, str, float, float]:
        """
        Fast version of check_exit_signal.
        Returns: (should_exit, reason, new_highest_price, new_lowest_price)
        
        Supports LONG, SHORT, and Day-1 Listing exit logic.
        """
        # Update price extremes
        new_highest = max(highest_price, curr_high)
        new_lowest = min(lowest_price, curr_low)
        
        # Calculate minutes held for grace period logic
        mins_held = (current_time_ns - entry_time_ns) / 60_000_000_000  # ns to minutes
        
        # =======================
        # [Day-1 Exit Logic] Stepped Risk Control (Three-Stage Rocket)
        # =======================
        # If within Day-1 window, use stepped trailing stop (ATR unreliable for new coins)
        if listing_time_ms > 0 and current_time_ms > 0:
            age_hours = (current_time_ms - listing_time_ms) / 3600_000
            day1_window = self.config.get('day1_listing_window_hours', 24)
            
            if 0 <= age_hours < day1_window:
                day1_disaster = self.config.get('day1_disaster_stop_pct', 0.04)  # 4% tight stop
                
                # Stalemate parameters (10-Minute Rule)
                stalemate_mins = self.config.get('day1_stalemate_mins', 10)
                
                # Time-Momentum parameters (Up-or-Out)
                time_stop_mins = self.config.get('day1_time_stop_mins', 15)
                time_stop_threshold = self.config.get('day1_time_stop_threshold', 0.01)
                
                # Staged triggers and trail percentages
                stage1_trigger = self.config.get('day1_stage1_trigger', 0.025)  # 2.5% (greedier BE)
                stage2_trigger = self.config.get('day1_stage2_trigger', 0.15)  # 15%
                stage2_trail = self.config.get('day1_stage2_trail', 0.10)      # 10%
                stage3_trigger = self.config.get('day1_stage3_trigger', 0.40)  # 40%
                stage3_trail = self.config.get('day1_stage3_trail', 0.05)      # 5%
                
                if side == 'LONG':
                    # --- PRIORITY 1: Tight Disaster Stop (4%) ---
                    # Catch fake breakouts early - if it drops 4%, it's not the one
                    disaster_stop_price = entry_price * (1 - day1_disaster)
                    if curr_low < disaster_stop_price:
                        return True, 'DisasterStop_Tight', new_highest, new_lowest
                    
                    current_profit_pct = (prev_close - entry_price) / entry_price
                    
                    # --- PRIORITY 2: Stalemate Exit (10-Minute Rule) ---
                    # Real moonshots are green immediately. If losing after 10 min, cut it.
                    if mins_held > stalemate_mins and current_profit_pct < 0:
                        return True, 'Stalemate_Exit', new_highest, new_lowest
                    
                    # --- PRIORITY 3: Time-Momentum Stop (Up-or-Out) ---
                    # 15 min + <1% profit = dead fish, exit immediately
                    if mins_held > time_stop_mins and current_profit_pct < time_stop_threshold:
                        return True, 'TimeStop_Momentum', new_highest, new_lowest
                    
                    # --- PRIORITY 4: Staged Trailing Stops (for profitable trades) ---
                    # High Water Mark profit percentage
                    max_profit_pct = (new_highest - entry_price) / entry_price
                    
                    # --- Stage 3: Mania phase (tight trailing) ---
                    if max_profit_pct > stage3_trigger:
                        # Use tight 5% trailing from highest
                        trail_stop = new_highest * (1 - stage3_trail)
                        if curr_low < trail_stop:
                            return True, 'Stage3_Tight', new_highest, new_lowest
                    
                    # --- Stage 2: Breakout phase (wide trailing) ---
                    elif max_profit_pct > stage2_trigger:
                        # Use wide 10% trailing from highest
                        trail_stop = new_highest * (1 - stage2_trail)
                        if curr_low < trail_stop:
                            return True, 'Stage2_Wide', new_highest, new_lowest
                    
                    # --- Stage 1: Growth phase (breakeven protection) ---
                    elif max_profit_pct > stage1_trigger:
                        # Move to breakeven + 0.5% fee buffer
                        be_price = entry_price * 1.005
                        if curr_low < be_price:
                            return True, 'Stage1_BE', new_highest, new_lowest
                    
                    return False, '', new_highest, new_lowest
                
                elif side == 'SHORT':
                    # [SHORT Exit Logic] Post-Hype Butcher
                    # Key: Shorts are dangerous, cut fast on any sign of reversal
                    
                    # 1. Hard Stop Loss (3%) - prevent squeeze
                    stop_loss_pct = self.config.get('short_stop_loss_pct', 0.03)
                    stop_loss_price = entry_price * (1 + stop_loss_pct)
                    if curr_high > stop_loss_price:
                        return True, 'StopLoss_Short', new_highest, new_lowest
                    
                    # 2. Take Profit (8%) - capture the dump
                    take_profit_pct = self.config.get('short_take_profit_pct', 0.08)
                    take_profit_price = entry_price * (1 - take_profit_pct)
                    if curr_low < take_profit_price:
                        return True, 'TakeProfit_Target', new_highest, new_lowest
                    
                    # 3. Trailing Stop (5% trigger, 2% distance)
                    current_profit_pct = (entry_price - new_lowest) / entry_price
                    trailing_trigger = self.config.get('short_trailing_trigger', 0.05)
                    trailing_dist = self.config.get('short_trailing_dist', 0.02)
                    
                    if current_profit_pct > trailing_trigger:
                        trailing_price = new_lowest * (1 + trailing_dist)
                        if curr_high > trailing_price:
                            return True, 'Trailing_Short', new_highest, new_lowest
                    
                    # 4. Time Stop (45 min) - shorts can't hold forever
                    time_stop_mins = self.config.get('short_time_stop_mins', 45)
                    if mins_held > time_stop_mins and current_profit_pct < 0.01:
                        return True, 'TimeStop_Stale', new_highest, new_lowest
                    
                    return False, '', new_highest, new_lowest
                    
                    # Time stop
                    if mins_held > self.time_stop_minutes:
                        return True, 'TimeStop', new_highest, new_lowest
                    
                    return False, '', new_highest, new_lowest
        
        # =======================
        # [Standard Exit Logic] ATR-based trailing stop for mature coins
        # =======================
        # Grace period: first 60 mins - give position breathing room
        trailing_stop_active = mins_held >= 60
        
        # Time stop: HARD exit after N minutes (applies to both directions)
        if mins_held > self.time_stop_minutes:
            return True, 'TimeStop', new_highest, new_lowest
        
        # =======================
        # [LONG Exit Logic]
        # =======================
        if side == 'LONG':
            # Intrabar profit check (use high for break-even trigger)
            intrabar_profit_pct = (curr_high - entry_price) / entry_price
            
            # 1. Disaster / BreakEven Stop (always active)
            if intrabar_profit_pct >= self.breakeven_trigger_pct:
                # Break-even triggered: protect capital
                stop_price = entry_price * (1 + self.breakeven_stop_offset)
                if curr_low < stop_price:
                    return True, 'BreakEven', new_highest, new_lowest
            else:
                # Disaster stop
                stop_price = entry_price * (1 - self.disaster_stop_pct)
                if curr_low < stop_price:
                    return True, 'DisasterStop', new_highest, new_lowest
            
            # 2. ATR Trailing Stop (only after grace period)
            if trailing_stop_active and current_atr > 0 and not np.isnan(current_atr):
                trailing_stop = new_highest - (self.atr_multiplier * current_atr)
                if prev_close < trailing_stop:
                    return True, 'TrailingStop', new_highest, new_lowest
        
        # =======================
        # [SHORT Exit Logic]
        # =======================
        elif side == 'SHORT':
            # For SHORT: profit when price drops, loss when price rises
            intrabar_profit_pct = (entry_price - curr_low) / entry_price
            
            # 1. Disaster Stop (price rises above threshold - CRITICAL for shorts!)
            # Meme coins can pump infinitely, must have hard stop
            stop_price = entry_price * (1 + self.disaster_stop_pct)
            if curr_high > stop_price:
                return True, 'DisasterStop', new_highest, new_lowest
            
            # 2. Break-even Stop (lock in profits once profitable)
            if intrabar_profit_pct >= self.breakeven_trigger_pct:
                # Move stop below entry to lock minimal profit
                breakeven_price = entry_price * (1 - self.breakeven_stop_offset)
                if curr_high > breakeven_price:
                    return True, 'BreakEven', new_highest, new_lowest
            
            # 3. ATR Trailing Stop (trail from lowest point)
            # For SHORT: stop is ABOVE the lowest price (price bouncing up = exit)
            if trailing_stop_active and current_atr > 0 and not np.isnan(current_atr):
                trailing_stop = new_lowest + (self.atr_multiplier * current_atr)
                if prev_close > trailing_stop:
                    return True, 'TrailingStop', new_highest, new_lowest
        
        return False, '', new_highest, new_lowest

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
