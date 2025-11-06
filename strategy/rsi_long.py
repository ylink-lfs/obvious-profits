# rsi_strategy.py
# [MODIFIED] To use dynamic ATR-based Stop Loss.

import numpy as np

class RSIStrategy:
    """
    Implements a stateful RSI Dip-Buying strategy.
    [MODIFIED] Uses a dynamic ATR stop loss.
    """
    def __init__(self, config):
        print("[Strategy] Initializing RSIStrategy...")
        
        # State: 'IDLE' (Can buy) or 'WAIT_RESET' (Waiting for RSI to go > reset level)
        self.state = 'IDLE' 
        self.config = config
        
        # Load parameters from config
        try:
            self.rsi_col_name = config['rsi_col_name']
            self.rsi_buy_threshold = config['rsi_buy_threshold']
            self.rsi_reset_threshold = config['rsi_reset_threshold']
            
            # [NEW] ATR parameters
            self.atr_col_name = config['atr_col_name']
            self.atr_sl_multiplier = config['atr_sl_multiplier']
            
        except KeyError as e:
            print(f"[Strategy] FATAL ERROR: Missing required key in CONFIG: {e}")
            raise

    def next(self, bar):
        """
        Receives a bar, updates state, and returns a signal.
        Signal: ('HOLD',) or ('BUY', entry_price, stop_loss_price)
        """
        
        # 1. Check Global Trend Filter
        # Only trade if the Daily Trend is 'Long'
        if bar.MA_TREND_DAILY == 'Short':
            self.state = 'IDLE' # Reset state if trend flips to short
            return ('HOLD',)

        # 2. Get current indicators
        try:
            current_rsi = getattr(bar, self.rsi_col_name)
            current_atr = getattr(bar, self.atr_col_name) # [NEW]
        except AttributeError as e:
            print(f"ERROR: Could not find indicator column in bar: {e}")
            return ('HOLD',)
            
        if np.isnan(current_rsi) or np.isnan(current_atr):
            return ('HOLD',)

        # --- RSI State Machine ---
        
        # 3. State: IDLE (Looking for a dip-buy signal)
        if self.state == 'IDLE':
            # Cond: 4H RSI < 30
            if current_rsi < self.rsi_buy_threshold:
                # print(f"DEBUG: RSIStrategy FIRED at {bar.Index}")
                
                # --- [MODIFIED] STOP LOSS CALCULATION ---
                entry_price = bar.close
                
                # SL = Entry - (ATR * Multiplier)
                stop_loss_price = entry_price - (current_atr * self.atr_sl_multiplier)
                # --- [END MODIFICATION] ---
                
                # Check for invalid SL (e.g., ATR was 0 or negative)
                if stop_loss_price >= entry_price:
                    print(f"[Strategy] WARNING: Invalid SL price {stop_loss_price} at {bar.Index}. Skipping trade.")
                    return ('HOLD',)

                # Change state to prevent re-buying on the next bar
                self.state = 'WAIT_RESET' 
                
                return ('BUY', entry_price, stop_loss_price)
            
            else:
                return ('HOLD',)
        
        # 4. State: WAIT_RESET (Already in a trade, waiting for RSI to reset)
        if self.state == 'WAIT_RESET':
            # Check if RSI has recovered above the reset level (e.g., 50)
            if current_rsi > self.rsi_reset_threshold:
                # print(f"DEBUG: RSIStrategy RESET at {bar.Index}")
                self.state = 'IDLE' # Can look for new trades again
            
            return ('HOLD',)
            
        return ('HOLD',)