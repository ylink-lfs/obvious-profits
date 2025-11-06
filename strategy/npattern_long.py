# strategy.py
# [MODIFIED] NPatternStrategy now uses dynamic ATR for Stop Loss.

import numpy as np

class NPatternStrategy:
    """
    Implements the N-Pattern state machine logic.
    [MODIFIED] Now includes a Keltner Channel breakout filter
    [MODIFIED] Now uses dynamic ATR Stop Loss
    """
    def __init__(self, config):
        print("[Strategy] Initializing N-Pattern Strategy...")
        # State machine: IDLE -> WATCHING_CP
        self.state = 'IDLE'
        self.c1_bar = None
        self.config = config
        
        # N-Pattern params
        self.vol_avg_col = f"VOL_AVG_{self.config['vol_avg_period']}"
        self.vol_mult = self.config['vol_multiplier']
        
        # KC Filter params
        self.kc_upper_col_name = self.config['kc_upper_col_name']
        
        # [NEW] ATR Stop Loss params
        self.atr_col_name = self.config['atr_col_name']
        self.atr_sl_multiplier = self.config['atr_sl_multiplier']

    def _is_c1(self, bar):
        # Cond_1 (放量阳线)
        is_bullish_candle = bar.close > bar.open
        
        # Check vol_mult. If 0.0, skip volume check.
        if self.vol_mult > 0.0:
            is_high_volume = bar.volume > (getattr(bar, self.vol_avg_col) * self.vol_mult)
            return is_bullish_candle and is_high_volume
        else:
            return is_bullish_candle # Skip volume check

    def next(self, bar):
        """
        Receives a bar, updates state, and returns a signal.
        Signal: ('HOLD',) or ('BUY', entry_price, stop_loss_price)
        """
        
        # 1. Check Global Trend Filter
        if bar.MA_TREND_DAILY == 'Short':
            self.state = 'IDLE'
            self.c1_bar = None
            return ('HOLD',)
            
        # 2. Get KC and ATR values
        try:
            current_kc_upper = getattr(bar, self.kc_upper_col_name)
            current_atr = getattr(bar, self.atr_col_name) # [NEW]
        except AttributeError as e:
            print(f"ERROR: Could not find KC or ATR column in bar: {e}")
            return ('HOLD',)
        
        if np.isnan(current_kc_upper) or np.isnan(current_atr):
            return ('HOLD',)

        # --- N-Pattern State Machine ---
        
        # 3. State: IDLE (Looking for C1)
        if self.state == 'IDLE':
            if self._is_c1(bar):
                # Found C1, transition to WATCHING_CP
                self.state = 'WATCHING_CP'
                self.c1_bar = bar # Store the C1 bar
            return ('HOLD',)
        
        # 4. State: WATCHING_CP (Looking for pullback or breakout)
        if self.state == 'WATCHING_CP':
            
            # 4a. Check for Failure (Cond_3: 不破阳脚)
            if bar.low < self.c1_bar.open:
                self.state = 'IDLE'
                self.c1_bar = None
                return ('HOLD',)
            
            # 4b. Check for Breakout (Cond_4: 突破新高)
            if bar.high > self.c1_bar.high:
                
                # [Filter 1] KC Confirmation Filter
                is_breakout_accelerating = self.c1_bar.high > current_kc_upper
                
                if is_breakout_accelerating:
                    # --- [MODIFIED] STOP LOSS CALCULATION ---
                    entry_price = self.c1_bar.high
                    
                    # SL = Entry - (ATR * Multiplier)
                    # We use the ATR value *at the time of the breakout (current bar)*
                    stop_loss_price = entry_price - (current_atr * self.atr_sl_multiplier)
                    
                    # Old SL logic:
                    # stop_loss_price = self.c1_bar.open 
                    # --- [END MODIFICATION] ---

                    # Check for invalid SL (e.g., ATR was 0 or negative)
                    if stop_loss_price >= entry_price:
                        print(f"[Strategy] WARNING: Invalid SL price {stop_loss_price} at {bar.Index}. Skipping trade.")
                        self.state = 'IDLE'
                        self.c1_bar = None
                        return ('HOLD',)

                    # Reset state and fire signal
                    self.state = 'IDLE'
                    self.c1_bar = None
                    return ('BUY', entry_price, stop_loss_price)
                else:
                    # Breakout happened, but *inside* the channel (chop).
                    self.state = 'IDLE'
                    self.c1_bar = None
                    return ('HOLD',)
            
            # 4c. Check if pullback is another C1 (resets pattern)
            if self._is_c1(bar):
                self.state = 'WATCHING_CP'
                self.c1_bar = bar # Store the *new* C1 bar
                return ('HOLD',)

            # 4d. Otherwise, pullback is continuing
            return ('HOLD',)
            
        return ('HOLD',)