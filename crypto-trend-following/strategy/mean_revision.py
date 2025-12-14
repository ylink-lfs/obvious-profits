# strategy/mean_reversion.py
# [NEW] Bollinger Band Mean Reversion Strategy
# Logic: Buy when price dips below Lower Band and closes back inside.

import numpy as np

class BollingerMeanReversion:
    """
    - Entry: Low < Lower Band AND Close > Lower Band (Rejection)
    - Filter: Injected filters (e.g., ADX < 30)
    - Exit: Price touches Middle Band (Mean Reversion)
    - Stop Loss: ATR based
    """
    def __init__(self, config, filters=None):
        print("[Strategy] Initializing BollingerMeanReversion...")
        self.config = config
        self.filters = filters if filters else []
        
        self.bb_lower = config['bb_lower_col']
        self.bb_middle = config['bb_middle_col']
        self.atr_col = config['atr_col_name']
        
    def _check_filters(self, bar):
        for f in self.filters:
            if not f.check(bar):
                return False
        return True

    def next(self, bar, df_history):
        # Get indicator values
        try:
            lower_band = getattr(bar, self.bb_lower)
            middle_band = getattr(bar, self.bb_middle)
            curr_atr = getattr(bar, self.atr_col)
        except AttributeError:
             return ('HOLD',)

        # 1. Check Strategy Exits (Take Profit at Mean)
        # If we are Long, and price hits Middle Band, we want to exit.
        # Note: The engine handles SL, but Strategy handles TP/Logic exits.
        # Since we don't track state here (Engine tracks state), we return a SELL signal
        # if price is favorable. The engine will ignore SELL if we are not in a position.
        if bar.high >= middle_band:
            return ('SELL', middle_band, 0.0, 'BB_MEAN_REVERT')

        # 2. Check Entry
        # Logic: Price dipped below lower band (Low < Lower) 
        # BUT closed back above/near it (Close > Lower). 
        # This implies a "rejection" of lower prices.
        if bar.low < lower_band and bar.close > lower_band:
            
            # Check Filters (Is market Choppy?)
            if self._check_filters(bar):
                
                entry_price = bar.close
                # Stop Loss: Below the lower band spike
                sl_price = entry_price - (curr_atr * self.config['atr_sl_multiplier'])
                
                return ('BUY', entry_price, sl_price, 'BB_DIP')

        return ('HOLD',)