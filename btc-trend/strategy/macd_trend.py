# strategy/macd_trend.py
# [MODIFIED] Accepts a list of Filter objects (Plugins)

import numpy as np

class MACDTrendStrategy:
    """
    - Long Entry: Price > MA20 AND MACD Golden Cross AND No Divergence
    - Filters: Checks all injected filters (e.g., ADX) before entry
    """
    def __init__(self, config, filters=None):
        print("[Strategy] Initializing MACDTrendStrategy...")
        self.config = config
        
        # [NEW] Store the list of filter plugins
        self.filters = filters if filters else []
        
        self.ma_col = config['ma_col_name']
        self.macd_col = config['macd_col_name']
        self.signal_col = config['macd_signal_col_name']
        self.atr_col = config['atr_col_name']
        self.div_lookback = config['divergence_lookback']
        
        self.prev_macd = None
        self.prev_signal = None

    def _check_filters(self, bar):
        """ Returns True if ALL filters pass, False otherwise """
        for f in self.filters:
            if not f.check(bar):
                return False
        return True

    def _check_bearish_divergence(self, bar, df_history):
        # (Same logic as before...)
        if len(df_history) < self.div_lookback:
            return False
        window = df_history.iloc[-self.div_lookback:]
        max_price = window['high'].max()
        max_macd = window[self.macd_col].max()
        current_price = bar.close
        current_macd = getattr(bar, self.macd_col)
        price_is_high = current_price >= (max_price * 0.995)
        macd_is_weak = current_macd < (max_macd * 0.95) 
        if price_is_high and macd_is_weak:
            return True
        return False

    def next(self, bar, df_history):
        curr_macd = getattr(bar, self.macd_col)
        curr_signal = getattr(bar, self.signal_col)
        curr_ma = getattr(bar, self.ma_col)
        curr_atr = getattr(bar, self.atr_col)
        
        if np.isnan(curr_ma) or np.isnan(curr_macd) or np.isnan(curr_signal):
             return ('HOLD',)

        signal = ('HOLD',)

        # 1. Check Exit (Price < MA20)
        if bar.close < curr_ma:
            self.prev_macd = curr_macd
            self.prev_signal = curr_signal
            return ('SELL', bar.close, 0.0, 'MA_BREAK')

        # 2. Check Entry (Price > MA20)
        if bar.close > curr_ma:
            if self.prev_macd is not None:
                is_golden_cross = (curr_macd > curr_signal) and (self.prev_macd <= self.prev_signal)
                
                if is_golden_cross:
                    # --- [NEW] CHECK PLUG-IN FILTERS ---
                    if self._check_filters(bar):
                        
                        # Check Divergence (Built-in logic)
                        has_divergence = self._check_bearish_divergence(bar, df_history)
                        
                        if not has_divergence:
                            entry_price = bar.close
                            sl_price = entry_price - (curr_atr * self.config['atr_sl_multiplier'])
                            signal = ('BUY', entry_price, sl_price, 'MACD_TREND')
        
        self.prev_macd = curr_macd
        self.prev_signal = curr_signal
        return signal