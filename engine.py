# engine.py
# [MODIFIED] To handle 'BUY' and 'SELL' signals from strategy.

import pandas as pd
from data_handler import DataHandler
from portfolio import Portfolio
# Import strategy_class from main.py
# from strategy import NPatternStrategy 

class BacktestEngine:
    """
    The main event loop that connects all components.
    """
    def __init__(self, config, strategy_class): # [MODIFIED]
        print("[Engine] Initializing Backtest Engine...")
        self.config = config
        self.data_handler = DataHandler(config)
        
        # [MODIFIED] Instantiate the strategy passed from main.py
        self.strategy = strategy_class(config) 
        
        self.portfolio = Portfolio(config)
        
        self.df_master = None
        self.results = {}

    def run(self):
        """
        Runs the full backtest.
        """
        # 1. Prepare data
        self.df_master = self.data_handler.prepare_master_dataframe()
        if self.df_master is None or self.df_master.empty:
            print("[Engine] ERROR: No data to backtest. Exiting.")
            return None, None
            
        print("\n--- [Engine] Backtest Started ---")
        
        # 2. Main Event Loop
        for bar in self.df_master.itertuples():
            
            # 2a. Update portfolio balance history (for equity curve)
            self.portfolio.update_balance_history(bar)
            
            # 2b. Check for exits (SL or Trend)
            self.portfolio.check_for_exit(bar)
            
            # 2c. Check for entries (if flat)
            if self.portfolio.state == 0:
                signal = self.strategy.next(bar)
                
                # [MODIFIED] Handle BUY or SELL signals
                if signal[0] == 'BUY':
                    entry_price, sl_price = signal[1], signal[2]
                    self.portfolio.handle_entry_signal(bar, 'BUY', entry_price, sl_price)
                elif signal[0] == 'SELL':
                    entry_price, sl_price = signal[1], signal[2]
                    self.portfolio.handle_entry_signal(bar, 'SELL', entry_price, sl_price)

        print("--- [Engine] Backtest Finished ---")
        
        # 3. Return results
        return self.portfolio.trades_log, pd.DataFrame(self.portfolio.balance_history).set_index('timestamp')