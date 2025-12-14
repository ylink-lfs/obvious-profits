# filters/adx_filter.py
# [MODIFIED] Supports 'weak' mode for Chop/Sideways detection

import numpy as np

class ADXFilter:
    def __init__(self, config, mode='strong'):
        """
        Args:
            mode: 'strong' (ADX > Threshold) or 'weak' (ADX < Threshold)
        """
        self.adx_col = config['adx_col_name']
        
        # Determine threshold based on mode intent
        if mode == 'strong':
            self.threshold = config.get('adx_threshold', 20) # Default trend threshold
        else:
            self.threshold = config.get('adx_chop_threshold', 30) # Default chop threshold
            
        self.mode = mode
        print(f"[Filter] Initialized ADXFilter (Mode: {mode}, Threshold: {self.threshold})")

    def check(self, bar):
        try:
            current_adx = getattr(bar, self.adx_col)
            
            if np.isnan(current_adx):
                return False
            
            if self.mode == 'strong':
                # Pass if Trend is Strong (e.g., > 20)
                return current_adx > self.threshold
            else:
                # Pass if Trend is Weak/Choppy (e.g., < 30)
                return current_adx < self.threshold
            
        except AttributeError:
            print(f"[Filter] ERROR: ADX column '{self.adx_col}' not found.")
            return False