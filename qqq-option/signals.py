# Signal generation for QQQ Boost Options Strategy
from AlgorithmImports import *
from typing import Optional
import config


class SignalGenerator:
    """Generates entry and exit signals for the strategy."""
    
    def __init__(self, algorithm):
        self.algo = algorithm
    
    def calculate_ath_dist(self, signal_price: float, all_time_high: float) -> float:
        """Calculate distance from all-time high."""
        if all_time_high == 0:
            return 0
        return (signal_price - all_time_high) / all_time_high
    
    def get_triggered_layer(self, dd: float, rsi: float, current_price: float,
                           sma200, sma20, sma50, active_layers: dict) -> Optional[int]:
        """
        Determine which layer to trigger based on signals.
        
        Improvement B: Trend Following Entry
        - MA Support: Enter L1 when price bounces off 20/50 SMA without breaking
        - RSI Threshold: Raise to 50-55 when 200 SMA is trending up
        """
        # Check if 200 SMA is trending up (bullish trend)
        sma200_trending_up = False
        if sma200.is_ready:
            sma200_trending_up = sma200.current.value > 0 and current_price > sma200.current.value
        
        # Dynamic RSI threshold based on trend
        if sma200_trending_up:
            rsi_threshold = config.RSI_UPTREND_THRESHOLD
        else:
            rsi_threshold = config.RSI_DOWNTREND_THRESHOLD
        
        # Check MA support for L1 entry
        ma_support_signal = self._check_ma_support(current_price, sma20, sma50)
        
        # L1 can trigger on MA support OR original DD/RSI conditions
        if 1 not in active_layers:
            if ma_support_signal and rsi <= rsi_threshold:
                return 1
        
        # For all layers: check RSI threshold
        if rsi > rsi_threshold:
            return None
        
        triggered_layer = None
        for layer in sorted(config.LAYER_CONFIG.keys(), reverse=True):
            if layer in active_layers:
                continue
            
            if dd <= config.LAYER_CONFIG[layer]["dd_threshold"]:
                triggered_layer = layer
                break
        
        return triggered_layer
    
    def _check_ma_support(self, current_price: float, sma20, sma50) -> bool:
        """Check if price is bouncing off MA support."""
        if not sma20.is_ready or not sma50.is_ready:
            return False
        
        sma20_val = sma20.current.value
        sma50_val = sma50.current.value
        
        # Price touched SMA20 or SMA50 (within 1%) and is now above
        near_sma20 = current_price >= sma20_val * 0.99 and current_price <= sma20_val * 1.02
        near_sma50 = current_price >= sma50_val * 0.99 and current_price <= sma50_val * 1.02
        
        return (near_sma20 or near_sma50) and current_price > min(sma20_val, sma50_val)
    
    def check_exit_signal(self, rsi: float, ath_dist: float) -> bool:
        """
        Check if exit signal is triggered.
        
        Improvement C: Smart Hedging - Don't exit just because RSI is high
        Only exit when near ATH with moderate RSI (take profit)
        """
        if rsi >= config.EXIT_RSI_THRESHOLD and ath_dist >= config.EXIT_ATH_DIST_THRESHOLD:
            return True
        return False
    
    def check_hedge_signal(self, current_price: float, sma20) -> bool:
        """
        Check if hedge signal is triggered.
        
        Improvement C: Smart Hedging
        Buy protective put when price breaks below 20 SMA (trend weakening)
        """
        if not sma20.is_ready:
            return False
        
        sma20_val = sma20.current.value
        
        # Price breaks below 20 SMA (trend weakening)
        if current_price < sma20_val * config.HEDGE_SMA_BUFFER:
            return True
        
        return False
    
    def check_deep_drawdown(self, ath_dist: float, active_layers: dict) -> bool:
        """Check if deep drawdown signal is triggered."""
        return ath_dist <= config.DEEP_DRAWDOWN_THRESHOLD and 5 not in active_layers
