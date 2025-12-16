# strategy/meme_momentum.py
# Meme Coin Momentum Strategy - Entry/Exit Signal Logic

import pandas as pd
from typing import Tuple
from dataclasses import dataclass


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    entry_price: float
    entry_time: pd.Timestamp
    size_usd: float
    size_units: float


class MemeStrategy:
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
    """
    
    def __init__(self, config):
        print("[Strategy] Initializing MemeStrategy...")
        self.config = config
        
        # Entry parameters
        self.btc_drop_threshold = config['btc_hourly_drop_threshold']
        self.volume_multiplier = config['volume_multiplier']
        
        # Exit parameters
        self.disaster_stop_pct = config['disaster_stop_pct']
        self.structural_lookback = config['structural_exit_lookback']
        self.time_stop_minutes = config['time_stop_minutes']
        self.time_stop_profit_threshold = config['time_stop_min_profit_pct']
    
    def check_circuit_breaker(self, btc_1h_change: float) -> bool:
        """
        Check if the system circuit breaker is triggered.
        Returns True if safe to trade (circuit breaker NOT triggered).
        """
        return btc_1h_change > self.btc_drop_threshold
    
    def check_entry_signal(
        self,
        prev_bar: pd.Series,
        coin_1h_change: float,
        btc_1h_change: float
    ) -> bool:
        """
        Check if all entry conditions are met based on previous bar.
        Returns True if entry signal is generated.
        """
        # 1. Volatility Breakout: Close > Bollinger Upper Band
        if 'bb_upper' not in prev_bar.index or pd.isna(prev_bar['bb_upper']):
            return False
        
        if prev_bar['close'] <= prev_bar['bb_upper']:
            return False
        
        # 2. Volume Confirmation: Volume > 2x MA AND Close > Open
        if 'volume_ma' not in prev_bar.index or pd.isna(prev_bar['volume_ma']):
            return False
        
        volume_threshold = prev_bar['volume_ma'] * self.volume_multiplier
        if prev_bar['volume'] <= volume_threshold:
            return False
        
        if prev_bar['close'] <= prev_bar['open']:
            return False
        
        # 3. Relative Strength: Coin outperforming BTC
        if coin_1h_change <= btc_1h_change:
            return False
        
        return True
    
    def check_exit_signal(
        self,
        current_bar: pd.Series,
        prev_bar: pd.Series,
        position: Position,
        lowest_low: float,
        current_time: pd.Timestamp
    ) -> Tuple[bool, str]:
        """
        Check if any exit condition is met.
        Returns Tuple of (should_exit, exit_reason).
        """
        # 1. Disaster Stop Loss: Current Low < Entry * 0.96 (-4%)
        disaster_price = position.entry_price * (1 - self.disaster_stop_pct)
        if current_bar['low'] < disaster_price:
            return True, 'DisasterStop'
        
        # 2. Structural Exit: Previous Close < Lowest Low of last N candles
        if prev_bar['close'] < lowest_low:
            return True, 'StructuralExit'
        
        # 3. Time Stop: Holding > 45 minutes AND profit < 1.5%
        holding_minutes = (current_time - position.entry_time).total_seconds() / 60
        
        if holding_minutes > self.time_stop_minutes:
            current_profit_pct = (prev_bar['close'] - position.entry_price) / position.entry_price
            if current_profit_pct < self.time_stop_profit_threshold:
                return True, 'TimeStop'
        
        return False, ''
    
    def calculate_entry_price(self, bar: pd.Series) -> float:
        """Calculate entry price with slippage (pay more)."""
        slippage_rate = self.config['slippage_rate']
        return bar['close'] * (1 + slippage_rate)
    
    def calculate_exit_price(self, bar: pd.Series, exit_reason: str) -> float:
        """Calculate exit price with slippage (receive less)."""
        slippage_rate = self.config['slippage_rate']
        
        if exit_reason == 'DisasterStop':
            base_price = bar['low']
        else:
            base_price = bar['close']
        
        return base_price * (1 - slippage_rate)
