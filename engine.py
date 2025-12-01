# engine.py
# [MODIFIED] Added logic to force-close any open positions
# at the end of the backtest loop.

import pandas as pd
from data_handler import DataHandler
# strategy_class will be passed in
from portfolio import Portfolio

class BacktestEngine:
    """
    The main event loop that connects all components.
    """
    def __init__(self, config, strategy_class):
        print("[Engine] Initializing Backtest Engine...")
        self.config = config
        self.data_handler = DataHandler(config)
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
        
        # [NEW] Keep track of the last bar
        last_bar = None 
        
        # 2. Main Event Loop
        for bar in self.df_master.itertuples():
            
            # 2a. Update portfolio balance history (for equity curve)
            self.portfolio.update_balance_history(bar)
            
            # 2b. Check for exits (SL or Trend)
            self.portfolio.check_for_exit(bar)
            
            # 2c. Check for entries (if flat)
            if self.portfolio.state == 0:
                signal = self.strategy.next(bar)
                
                # Handle BUY or SELL signals
                if signal[0] == 'BUY':
                    entry_price, sl_price, trade_type = signal[1], signal[2], signal[3]
                    self.portfolio.handle_entry_signal(bar, 'BUY', entry_price, sl_price, trade_type)
                
                # (Short logic is currently disabled in strategy, but this is ready)
                elif signal[0] == 'SELL':
                    entry_price, sl_price, trade_type = signal[1], signal[2], signal[3]
                    self.portfolio.handle_entry_signal(bar, 'SELL', entry_price, sl_price, trade_type)

            # [NEW] Store the last bar
            last_bar = bar

        print("--- [Engine] Backtest Finished ---")
        
        # --- [NEW] Force close any open position at the end of the data ---
        if self.portfolio.state != 0 and last_bar is not None:
            print(f"[Engine] Force-closing open position at end of backtest: {last_bar.Index}")
            
            # We call _execute_exit directly using the last bar's data
            # We assume the default fee_pct (0.001) as it's hardcoded in check_for_exit
            self.portfolio._execute_exit(
                last_bar, 
                last_bar.close, 
                'EndOfBacktest', 
                0.001
            )
        # --- [END NEW BLOCK] ---
        
        # 3. Return results
        return self.portfolio.trades_log, pd.DataFrame(self.portfolio.balance_history).set_index('timestamp')