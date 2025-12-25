# Signal generation for Squeeze Entry Options Strategy
from AlgorithmImports import *
from typing import Optional, List, Tuple
import config
from models import SymbolData, EntryCandidate


class SignalGenerator:
    """Generates entry and exit signals for the Squeeze strategy."""
    
    def __init__(self, algorithm):
        self.algo = algorithm
    
    def check_squeeze_signal(self, symbol_data: SymbolData) -> bool:
        """
        Check if squeeze entry signal is triggered.
        
        The Squeeze Signal (OR relationship):
        1. BB width < 20th percentile of past 90 days BB width
        2. Close within 2% of MA20 AND recent 5-day ATR < 20-day ATR
        """
        # Condition 1: BB width squeeze
        bb_percentile = symbol_data.get_bb_width_percentile(config.BB_WIDTH_PERCENTILE_LOOKBACK)
        bb_squeeze = bb_percentile < config.BB_WIDTH_PERCENTILE_THRESHOLD
        
        # Condition 2: Close near MA20 AND ATR contracting
        close_near_ma20 = symbol_data.is_close_near_ma20(config.CLOSE_TO_MA20_THRESHOLD)
        atr_contracting = symbol_data.is_atr_contracting()
        consolidation = close_near_ma20 and atr_contracting
        
        return bb_squeeze or consolidation
    
    def check_iv_signal(self, symbol_data: SymbolData) -> bool:
        """
        Check if IV Percentile signal is triggered.
        
        IV Percentile < 30%
        """
        return symbol_data.iv_percentile < config.IV_PERCENTILE_THRESHOLD
    
    def check_trend_background(self, symbol_data: SymbolData) -> bool:
        """
        Check if trend background conditions are met.
        
        Trend Background (AND relationship):
        1. Previous Close > MA200
        2. 40 <= RSI(14) <= 55
        """
        above_ma200 = symbol_data.is_above_ma200()
        rsi_in_range = symbol_data.is_rsi_in_range(config.RSI_MIN, config.RSI_MAX)
        
        return above_ma200 and rsi_in_range
    
    def check_entry_signal(self, symbol_data: SymbolData) -> bool:
        """
        Check if all entry conditions are met for a symbol.
        
        Entry requires:
        1. Squeeze signal (OR conditions)
        2. IV Percentile signal
        3. Trend background (AND conditions)
        """
        squeeze = self.check_squeeze_signal(symbol_data)
        iv_signal = self.check_iv_signal(symbol_data)
        trend = self.check_trend_background(symbol_data)
        
        return squeeze and iv_signal and trend
    
    def get_entry_candidates(self, symbol_data_dict: dict) -> List[EntryCandidate]:
        """
        Get list of entry candidates sorted by score (lower is better).
        
        Score = IV Percentile * BB Width
        Select the one with lowest score if multiple symbols trigger.
        """
        candidates = []
        
        for symbol, data in symbol_data_dict.items():
            if self.check_entry_signal(data):
                candidate = EntryCandidate.create(symbol, data)
                candidates.append(candidate)
                self.algo.log(f"Entry candidate: {symbol}, IV Percentile: {candidate.iv_percentile:.2%}, "
                             f"BB Width: {candidate.bb_width:.4f}, Score: {candidate.score:.6f}")
        
        # Sort by score (lower is better)
        candidates.sort(key=lambda x: x.score)
        return candidates
    
    def check_rally_exit_signal(self, position, symbol_data: SymbolData, 
                                 current_open: float, current_high: float) -> Tuple[bool, str]:
        """
        Check if price rally exit signal is triggered.
        
        Precondition: Price (open or high) > Long strike + (Long strike - Short strike)
        Once this boundary is crossed, the state is remembered.
        
        Then check (OR):
        1. Current RSI(14) < Previous day RSI
        2. Previous day high > Bollinger Upper Band(20, 2)
        
        The position tracks whether price has crossed the max profit boundary.
        Once crossed, we keep checking exit conditions until they trigger.
        """
        max_profit_price = position.get_max_profit_price()
        
        # Check if price crosses max profit boundary (using open or high)
        price_now_crossing = current_open > max_profit_price or current_high > max_profit_price
        
        # Update state if price is crossing for the first time
        if price_now_crossing and not position.price_crossed_max_profit:
            position.price_crossed_max_profit = True
            self.algo.log(f"Price crossed max profit boundary for {position.symbol}: "
                         f"Open={current_open:.2f}, High={current_high:.2f}, Boundary={max_profit_price:.2f}")
        
        # If price has never crossed the boundary, no exit signal
        if not position.price_crossed_max_profit:
            return False, ""
        
        # Price has crossed boundary (now or before), check exit conditions
        
        # Check condition 1: RSI declining
        if symbol_data.rsi is not None and symbol_data.rsi.is_ready:
            current_rsi = symbol_data.rsi.current.value
            if current_rsi < symbol_data.prev_rsi:
                return True, f"Rally exit: RSI declining ({current_rsi:.2f} < {symbol_data.prev_rsi:.2f})"
        
        # Check condition 2: Previous high broke upper BB
        upper_bb = symbol_data.get_bollinger_upper()
        if symbol_data.prev_high > upper_bb:
            return True, f"Rally exit: High ({symbol_data.prev_high:.2f}) > Upper BB ({upper_bb:.2f})"
        
        return False, ""
    
    def check_drop_exit_signal(self, position, current_price: float) -> Tuple[bool, str]:
        """
        Check if price drop exit signal is triggered.
        
        Exit if price < 0.95 * short strike
        """
        stop_price = position.get_stop_loss_price()
        
        if current_price < stop_price:
            return True, f"Price ({current_price:.2f}) < Stop ({stop_price:.2f})"
        
        return False, ""
    
    def check_dte_exit_signal(self, position, current_time) -> Tuple[bool, str]:
        """
        Check if DTE exit signal is triggered.
        
        Exit when DTE <= 20
        """
        if position.long_call_symbol is None:
            return False, ""
        
        expiry = position.long_call_symbol.id.date
        dte = (expiry - current_time).days
        
        if dte <= config.DTE_EXIT_THRESHOLD:
            return True, f"DTE ({dte}) <= {config.DTE_EXIT_THRESHOLD}"
        
        return False, ""
    
    def check_exit_signals(self, position, symbol_data: SymbolData,
                           current_price: float, current_open: float,
                           current_high: float, current_time) -> Tuple[bool, str]:
        """
        Check all exit signals for a position.
        
        Returns (should_exit, reason)
        """
        # Check DTE exit first (highest priority)
        should_exit, reason = self.check_dte_exit_signal(position, current_time)
        if should_exit:
            return True, reason
        
        # Check price drop exit
        should_exit, reason = self.check_drop_exit_signal(position, current_price)
        if should_exit:
            return True, reason
        
        # Check rally exit (with state tracking)
        should_exit, reason = self.check_rally_exit_signal(
            position, symbol_data, current_open, current_high
        )
        if should_exit:
            return True, reason
        
        return False, ""
