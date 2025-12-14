# strategy.py
# [MODIFIED] Implements "Fuzzy N-Pattern" (Approximation Logic)
# 1. Checks AVERAGE volume of pullback, not individual bars.
# 2. Checks AVERAGE body size of pullback.
# 3. Checks CLOSE price for support, ignoring wicks (Low).

import numpy as np

class FuzzyNPatternStrategy: # Renamed to reflect logic change
    def __init__(self, config):
        print("[Strategy] Initializing FuzzyNPatternStrategy (Human-like Approximation)...")
        self.config = config
        
        # State machine
        self.state = 'IDLE'
        self.c1_bar = None
        
        # [NEW] List to store pullback bars for averaging
        self.pullback_bars = [] 
        
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
        # Rule 1: Must be Bullish
        if bar.close <= bar.open:
            return False
        # Rule 2: High Volume
        avg_vol = getattr(bar, self.vol_avg_col)
        if bar.volume < (avg_vol * self.c1_vol_mult):
            return False
        return True

    def _check_pullback_quality(self, current_avg_vol, c1_body):
        """
        [NEW] Checks the collective quality of the pullback phase.
        Returns True if the 'Cluster' of pullback bars looks good.
        """
        if not self.pullback_bars:
            return True

        # 1. Calculate Average Volume of the pullback cluster
        pb_vols = [b.volume for b in self.pullback_bars]
        avg_pb_vol = sum(pb_vols) / len(pb_vols)
        
        # Rule: Cluster Average Volume must be low
        if avg_pb_vol > (current_avg_vol * self.pb_vol_mult):
            # print(f"DEBUG: Pullback avg vol {avg_pb_vol} > limit {current_avg_vol}")
            return False

        # 2. Calculate Average Body Size of the pullback cluster
        pb_bodies = [self._get_candle_body(b) for b in self.pullback_bars]
        avg_pb_body = sum(pb_bodies) / len(pb_bodies)
        
        # Rule: Cluster Average Body must be small relative to C1
        if avg_pb_body > (c1_body * self.pb_body_ratio):
            # print(f"DEBUG: Pullback avg body {avg_pb_body} > limit {c1_body * self.pb_body_ratio}")
            return False
            
        return True

    def next(self, bar):
        # 1. Global Trend Filter
        if bar.MA_TREND_DAILY == 'Short':
            self.state = 'IDLE'
            self.c1_bar = None
            self.pullback_bars = []
            return ('HOLD',)

        # --- State Machine ---
        
        # State: IDLE
        if self.state == 'IDLE':
            if self._is_valid_c1(bar):
                self.state = 'WATCHING_PULLBACK'
                self.c1_bar = bar
                self.pullback_bars = [] # Reset list
            return ('HOLD',)
        
        # State: WATCHING_PULLBACK
        if self.state == 'WATCHING_PULLBACK':
            
            c1_range = self.c1_bar.close - self.c1_bar.open
            limit_price = self.c1_bar.open + (c1_range * self.ret_depth)
            
            # --- [FUZZY CHECK 1] Retracement Depth ---
            # Use CLOSE price instead of LOW. Allow wicks to pierce support.
            if bar.close < limit_price:
                self.state = 'IDLE'
                self.c1_bar = None
                self.pullback_bars = []
                return ('HOLD',)
            
            # --- [FUZZY CHECK 2] Breakout ---
            # If price breaks C1 Close (confirmed breakout)
            if bar.close > self.c1_bar.close:
                
                # Before firing BUY, check the "Gestalt" quality of the pullback
                # We pass the current bar's avg vol environment for comparison
                current_market_avg_vol = getattr(bar, self.vol_avg_col)
                c1_body = self._get_candle_body(self.c1_bar)
                
                is_quality_pullback = self._check_pullback_quality(current_market_avg_vol, c1_body)
                
                if is_quality_pullback:
                    entry_price = bar.close
                    stop_loss_price = self.c1_bar.open 
                    
                    self.state = 'IDLE'
                    self.c1_bar = None
                    self.pullback_bars = []
                    return ('BUY', entry_price, stop_loss_price, 'FUZZY_N_PATTERN')
                else:
                    # Pullback structure was too messy/volatile, skip this breakout
                    self.state = 'IDLE'
                    self.c1_bar = None
                    self.pullback_bars = []
                    return ('HOLD',)

            # --- Accumulate Pullback Data ---
            # If not failed and not broken out, we are still pulling back.
            # Add this bar to our "memory" to evaluate the cluster later.
            self.pullback_bars.append(bar)
            
            # --- Condition C: Check for new C1 ---
            # If a new strong candle appears inside the pullback that qualifies as C1,
            # we reset the pattern to start from this new candle.
            if self._is_valid_c1(bar):
                self.c1_bar = bar
                self.pullback_bars = [] # Clear previous pullback history
                return ('HOLD',)
            
            return ('HOLD',)
            
        return ('HOLD',)