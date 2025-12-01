# strategy.py (or strategy/npattern_symmetric.py)
# [MODIFIED] This is the clean NPatternStrategy for the R:R test.
# It has NO ADX logic.

import numpy as np

class NPatternStrategy:
    """
    Implements the Long-Only N-Pattern Strategy
    - TIMEFRAME: 4H
    - FILTER 1: Daily > MA(200)
    - FILTER 2: C1 Volume (vol_multiplier=0.0)
    - SL: C1_Open
    """
    def __init__(self, config):
        print(f"[Strategy] Initializing NPatternStrategy (Long-Only, vol={config['vol_multiplier']}, R:R_Exit=ON)...")
        self.config = config
        
        # --- State Machines ---
        self.state_n_pattern = 'IDLE' # 'IDLE' or 'WATCHING_CP'
        self.c1_bar = None
        
        # --- Load All Parameters ---
        try:
            # N-Pattern Params
            self.vol_avg_col = f"VOL_AVG_{self.config['vol_avg_period']}"
            self.vol_mult = self.config['vol_multiplier']
            
        except KeyError as e:
            print(f"[Strategy] FATAL ERROR: Missing required key in CONFIG: {e}")
            raise

    # --- LONG LOGIC ---
    def _is_c1_long(self, bar):
        # N-Pattern Cond_1 (放量阳线)
        is_bullish_candle = bar.close > bar.open
        
        # Check vol_mult. If 0.0, skip volume check.
        if self.vol_mult > 0.0:
            is_high_volume = bar.volume > (getattr(bar, self.vol_avg_col) * self.vol_mult)
            return is_bullish_candle and is_high_volume
        else:
            return is_bullish_candle # vol_mult=0.0 means skip check

    def _run_long_logic(self, bar):
        """ Runs the N-Pattern (vol-filtered) logic. """

        # --- N-Pattern State Machine ---
        if self.state_n_pattern == 'IDLE':
            if self._is_c1_long(bar):
                self.state_n_pattern = 'WATCHING_CP'
                self.c1_bar = bar
            return ('HOLD',)
        
        if self.state_n_pattern == 'WATCHING_CP':
            # Failure (Cond_3: 不破阳脚)
            if bar.low < self.c1_bar.open:
                self.state_n_pattern = 'IDLE'
                self.c1_bar = None
                return ('HOLD',)
            
            # Breakout (Cond_4: 突破新高)
            if bar.high > self.c1_bar.high:
                
                # Signal confirmed, use C1_Open as SL
                entry_price = self.c1_bar.high
                stop_loss_price = self.c1_bar.open 
                
                self.state_n_pattern = 'IDLE'
                self.c1_bar = None
                return ('BUY', entry_price, stop_loss_price, 'N_PATTERN')
            
            # Check if pullback is another C1
            if self._is_c1_long(bar):
                self.state_n_pattern = 'WATCHING_CP'
                self.c1_bar = bar
                return ('HOLD',)
            return ('HOLD',)
        return ('HOLD',)


    def next(self, bar):
        """
        Receives a bar, checks the daily trend, and routes to the
        correct sub-strategy (Long-Only).
        """
        
        # 1. Check Global Trend Filter
        if bar.MA_TREND_DAILY == 'Short':
            # Do nothing in a downtrend.
            self.state_n_pattern = 'IDLE'
            self.c1_bar = None
            return ('HOLD',)

        # 2. Run Long Logic (if trend is Long)
        if bar.MA_TREND_DAILY == 'Long':
            return self._run_long_logic(bar)
        
        # If trend is neither, hold
        return ('HOLD',)