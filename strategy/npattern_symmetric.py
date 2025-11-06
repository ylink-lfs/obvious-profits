# strategy.py
# [MODIFIED] Removed Cond_2 (low vol pullback) and Swapped SL to ATR

import numpy as np

class SymmetricNPatternStrategy:
    """
    Implements a Symmetrical N-Pattern Strategy (Long and Short).
    [MODIFIED] Now uses N-Pattern (vol=1.0) + KC Filter + ATR SL
    [MODIFIED] Short logic is DISABLED.
    """
    def __init__(self, config):
        print("[Strategy] Initializing SymmetricNPatternStrategy (KC Filter + ATR SL, Long-Only)...")
        self.config = config
        
        # --- State Machines ---
        self.state_long = 'IDLE' # 'IDLE' or 'WATCHING_CP_LONG'
        self.c1_bar_long = None
        self.state_short = 'IDLE' # (This state is no longer used)
        self.c1_bar_short = None
        
        # --- Load All Parameters ---
        try:
            # N-Pattern Params
            self.vol_avg_col = f"VOL_AVG_{self.config['vol_avg_period']}"
            self.vol_mult = self.config['vol_multiplier']
            
            # KC Filter Params
            self.kc_upper_col_name = self.config['kc_upper_col_name']
            
            # [NEW] ATR Stop Loss params
            self.atr_col_name = self.config['atr_col_name']
            self.atr_sl_multiplier = self.config['atr_sl_multiplier']
            
        except KeyError as e:
            print(f"[Strategy] FATAL ERROR: Missing required key in CONFIG: {e}")
            raise

    # --- LONG LOGIC ---
    def _is_c1_long(self, bar):
        # Cond_1 (放量阳线)
        is_bullish_candle = bar.close > bar.open
        
        if self.vol_mult > 0.0:
            is_high_volume = bar.volume > (getattr(bar, self.vol_avg_col) * self.vol_mult)
            return is_bullish_candle and is_high_volume
        else:
            return is_bullish_candle # Skip volume check

    def _run_long_logic(self, bar, current_kc_upper, current_atr):
        """ Runs the N-Pattern (vol=1.0 + KC Filter) logic. """
        
        # State: IDLE (Looking for C1)
        if self.state_long == 'IDLE':
            if self._is_c1_long(bar):
                self.state_long = 'WATCHING_CP_LONG'
                self.c1_bar_long = bar
            return ('HOLD',)
        
        # State: WATCHING_CP (Looking for pullback or breakout)
        if self.state_long == 'WATCHING_CP_LONG':
            
            # [REMOVED] Cond_2 (缩量回踩) Check
            # We removed this check as it hurt the win rate (28%) vs.
            # not having it (50%).
            
            # Failure (Cond_3: 不破阳脚)
            if bar.low < self.c1_bar_long.open:
                # print(f"DEBUG: N-Pattern FAILED (Broke C1 Open) at {bar.Index}")
                self.state_long = 'IDLE'
                self.c1_bar_long = None
                return ('HOLD',)
            
            # Breakout (Cond_4: 突破新高)
            if bar.high > self.c1_bar_long.high:
                
                # KC Confirmation Filter
                is_breakout_accelerating = self.c1_bar_long.high > current_kc_upper
                
                if is_breakout_accelerating:
                    # --- [MODIFIED] STOP LOSS CALCULATION ---
                    entry_price = self.c1_bar_long.high
                    
                    # SL = Entry - (ATR * Multiplier)
                    stop_loss_price = entry_price - (current_atr * self.atr_sl_multiplier)
                    
                    # Old SL logic:
                    # stop_loss_price = self.c1_bar_long.open
                    # --- [END MODIFICATION] ---
                    
                    if stop_loss_price >= entry_price:
                        print(f"[Strategy] WARNING: Invalid SL price {stop_loss_price} at {bar.Index}. Skipping trade.")
                        self.state_long = 'IDLE'
                        self.c1_bar_long = None
                        return ('HOLD',)
                    
                    self.state_long = 'IDLE'
                    self.c1_bar_long = None
                    return ('BUY', entry_price, stop_loss_price)
                else:
                    # Breakout inside chop, ignore and reset.
                    self.state_long = 'IDLE'
                    self.c1_bar_long = None
                    return ('HOLD',)
            
            # Check if pullback is another C1
            if self._is_c1_long(bar):
                self.state_long = 'WATCHING_CP_LONG'
                self.c1_bar_long = bar
                return ('HOLD',)

            return ('HOLD',)
            
        return ('HOLD',)

    # --- SHORT LOGIC (UNUSED) ---
    def _is_c1_short(self, bar):
        # (This logic is preserved but currently disabled)
        is_bearish_candle = bar.close < bar.open
        if self.vol_mult > 0.0:
            is_high_volume = bar.volume > (getattr(bar, self.vol_avg_col) * self.vol_mult)
            return is_bearish_candle and is_high_volume
        else:
            return is_bearish_candle

    def _run_short_logic(self, bar, current_kc_lower):
        # (This logic is preserved but currently disabled)
        return ('HOLD',)

    # --- [MODIFIED] MAIN NEXT FUNCTION ---
    def next(self, bar):
        """
        Receives a bar, checks the daily trend, and routes to the
        correct sub-strategy (Long-Only).
        """
        
        # 1. Check Global Trend Filter
        if bar.MA_TREND_DAILY == 'Short':
            # Do nothing in a downtrend.
            # Reset Long state machine just in case
            self.state_long = 'IDLE'
            self.c1_bar_long = None
            return ('HOLD',)

        # 2. Get indicator values
        try:
            current_kc_upper = getattr(bar, self.kc_upper_col_name)
            current_atr = getattr(bar, self.atr_col_name) # [NEW]
        except AttributeError as e:
            print(f"ERROR: Could not find KC or ATR column in bar: {e}")
            return ('HOLD',)
        if np.isnan(current_kc_upper) or np.isnan(current_atr):
            return ('HOLD',)

        # 3. Run Long Logic
        if bar.MA_TREND_DAILY == 'Long':
            return self._run_long_logic(bar, current_kc_upper, current_atr)
        
        # If trend is neither (e.g., NaN), hold
        return ('HOLD',)