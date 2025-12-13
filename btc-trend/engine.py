# engine.py
# [MODIFIED] Supports filters injection and history passing.

import pandas as pd
from data_handler import DataHandler
from portfolio import Portfolio

class BacktestEngine:
    """
    The main event loop that connects all components.
    """
    # [FIXED] Added 'filters' argument to __init__
    def __init__(self, config, strategy_class, start_date, end_date, filters=None):
        print(f"[Engine] Initializing for range: {start_date} to {end_date}")
        self.config = config
        self.data_handler = DataHandler(config)
        
        # [MODIFIED] Instantiate strategy with filters
        # We use a try-except block to support strategies that might not accept 'filters'
        try:
            self.strategy = strategy_class(config, filters=filters) 
        except TypeError:
            # Fallback for older strategies (like NPatternStrategy) that don't use filters
            self.strategy = strategy_class(config)

        self.portfolio = Portfolio(config)
        
        # Store the date range for this specific run (Train or Test)
        self.start_date = start_date
        self.end_date = end_date
        
        self.df_master = None

    def run(self):
        """
        Runs the full backtest for the configured date range.
        """
        # 1. Prepare data
        self.df_master = self.data_handler.prepare_data(self.start_date, self.end_date)
        
        if self.df_master is None or self.df_master.empty:
            print("[Engine] ERROR: No data to backtest. Exiting.")
            return None, None
            
        print(f"\n--- [Engine] Backtest Started ({self.start_date} -> {self.end_date}) ---")
        
        last_bar = None
        
        # 2. Main Event Loop
        for i in range(len(self.df_master)):
            bar = self.df_master.iloc[i]
            
            # [NEW] Prepare history slice (needed for MeanReversion strategy)
            # Passes data up to the current bar
            df_history = self.df_master.iloc[:i+1]
            
            # 2a. Update portfolio balance history (for equity curve)
            self.portfolio.update_balance_history(bar)
            
            # 2b. Check for exits (SL or Trend)
            self.portfolio.check_for_exit(bar)
            
            # 2c. Check for entries (if flat)
            if self.portfolio.state == 0:
                # [MODIFIED] Pass df_history to strategy.next()
                # Most robust way is to handle potential TypeError if old strategies don't accept it
                try:
                    signal = self.strategy.next(bar, df_history)
                except TypeError:
                    signal = self.strategy.next(bar)
                
                # Handle BUY signals (Open Long Position)
                if signal[0] == 'BUY':
                    entry_price, sl_price, trade_type = signal[1], signal[2], signal[3]
                    self.portfolio.handle_entry_signal(bar, 'BUY', entry_price, sl_price, trade_type)
                
                # [FIX] Only handle SELL as short-entry if sl_price > 0
                # This prevents treating Take-Profit SELL signals (sl=0) as short entries
                elif signal[0] == 'SELL' and signal[2] > 0:
                    entry_price, sl_price, trade_type = signal[1], signal[2], signal[3]
                    self.portfolio.handle_entry_signal(bar, 'SELL', entry_price, sl_price, trade_type)
            
            # [NEW] Check Strategy-Initiated Exits (e.g. Mean Reversion TP at Middle Band)
            elif self.portfolio.state != 0:
                 try:
                    signal = self.strategy.next(bar, df_history)
                 except TypeError:
                    signal = self.strategy.next(bar)
                 
                 # If we are Long and get a Sell signal (TP)
                 if self.portfolio.state == 1 and signal[0] == 'SELL':
                     self.portfolio._execute_exit(bar, bar.close, signal[3], 0.001)

            # Store the last bar for force-close logic
            last_bar = bar

        print("--- [Engine] Backtest Finished ---")
        
        # --- Force close any open position at the end of the data ---
        if self.portfolio.state != 0 and last_bar is not None:
            print(f"[Engine] Force-closing open position at end of backtest: {last_bar.name}")
            self.portfolio._execute_exit(
                last_bar, 
                last_bar.close, 
                'EndOfBacktest', 
                0.001
            )
        
        # 3. Return results
        return self.portfolio.trades_log, pd.DataFrame(self.portfolio.balance_history).set_index('timestamp')