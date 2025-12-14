# strategy.py
# [MODIFIED] Implements "Strict N-Pattern" (Rising Three Methods)
# Logic derived from provided article analysis.

import numpy as np

class StrictNPatternStrategy:
    """
    Implements the 'Rising Three Methods' logic:
    1. Trend: Daily > MA200
    2. C1: Big Bullish Candle (High Vol)
    3. Pullback: Series of small, low vol candles staying above 50% of C1
    4. Breakout: Close > C1 Close
    """
    def __init__(self, config):
        print("[Strategy] Initializing StrictNPatternStrategy (Rising Three Methods)...")
        self.config = config
        
        # State machine: IDLE -> WATCHING_PULLBACK
        self.state = 'IDLE'
        self.c1_bar = None
        
        # Load Params
        try:
            self.vol_avg_col = f"VOL_AVG_{self.config['vol_avg_period']}"
            self.c1_vol_mult = self.config['c1_vol_multiplier']
            self.pb_vol_mult = self.config['pullback_vol_multiplier']
            self.ret_depth = self.config['retracement_depth']
            self.pb_body_ratio = self.config['pullback_body_ratio']
        except KeyError as e:
            print(f"[Strategy] FATAL ERROR: Missing parameter {e} in CONFIG.")
            raise

    def _get_candle_body(self, bar):
        return abs(bar.close - bar.open)

    def _is_valid_c1(self, bar):
        # Rule 1: Must be a Bullish Candle
        if bar.close <= bar.open:
            return False
            
        # Rule 2: High Volume ("大成交量拉起")
        # Check if volume > Avg * 1.5
        avg_vol = getattr(bar, self.vol_avg_col)
        if bar.volume < (avg_vol * self.c1_vol_mult):
            return False
            
        return True

    def next(self, bar):
        """
        Main strategy loop called for every bar.
        """
        # 1. Global Trend Filter (Daily MA200)
        if bar.MA_TREND_DAILY == 'Short':
            self.state = 'IDLE'
            self.c1_bar = None
            return ('HOLD',)

        # --- State Machine ---
        
        # State: IDLE (Looking for the first big Yang candle)
        if self.state == 'IDLE':
            if self._is_valid_c1(bar):
                self.state = 'WATCHING_PULLBACK'
                self.c1_bar = bar
                # print(f"DEBUG: Found Potential C1 at {bar.Index}")
            return ('HOLD',)
        
        # State: WATCHING_PULLBACK (Monitoring the small corrective candles)
        if self.state == 'WATCHING_PULLBACK':
            
            # Calculate C1 properties for comparison
            c1_body = self._get_candle_body(self.c1_bar)
            c1_range = self.c1_bar.close - self.c1_bar.open
            
            # "50% Line": Price should ideally stay above this
            # limit_price = Open + (Body * 0.5)
            limit_price = self.c1_bar.open + (c1_range * self.ret_depth)
            
            avg_vol = getattr(bar, self.vol_avg_col)
            
            # --- Condition A: Breakout (Success) ---
            # "收线与第一根阳K收盘价之上"
            # We use Close > C1_Close for confirmation (stricter than High > High)
            if bar.close > self.c1_bar.close:
                
                entry_price = bar.close
                # Stop Loss: Placed at C1 Open (The "Yang Foot") 
                # This is the invalidation point of the whole pattern.
                stop_loss_price = self.c1_bar.open 
                
                self.state = 'IDLE'
                self.c1_bar = None
                return ('BUY', entry_price, stop_loss_price, 'STRICT_N_PATTERN')

            # --- Condition B: Pattern Failure Checks ---
            
            # 1. Retracement too deep ("停止与50%线之上")
            if bar.low < limit_price:
                # print(f"DEBUG: Failed - Retracement too deep at {bar.Index}")
                self.state = 'IDLE'
                self.c1_bar = None
                return ('HOLD',)
            
            # 2. Volume too high ("最好是成交量递减")
            if bar.volume > (avg_vol * self.pb_vol_mult):
                # print(f"DEBUG: Failed - Pullback volume too high at {bar.Index}")
                self.state = 'IDLE'
                self.c1_bar = None
                return ('HOLD',)
                
            # 3. Candle body too large ("波动率逐渐缩的一连串小K")
            current_body = self._get_candle_body(bar)
            if current_body > (c1_body * self.pb_body_ratio):
                # print(f"DEBUG: Failed - Pullback candle too big at {bar.Index}")
                self.state = 'IDLE'
                self.c1_bar = None
                return ('HOLD',)
            
            # --- Condition C: Check for new C1 ---
            # If we get ANOTHER massive green candle during pullback, it might be a new C1
            if self._is_valid_c1(bar):
                # Reset start point to this new candle
                self.c1_bar = bar
                return ('HOLD',)
            
            # If passed all checks, we are still in a valid pullback. Wait for next bar.
            return ('HOLD',)
            
        return ('HOLD',)