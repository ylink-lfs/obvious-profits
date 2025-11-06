# main.py
# The main entry point to run the backtest.

import traceback
from engine import BacktestEngine
from evaluate import evaluate_event_driven_performance
from config import CONFIG

# --- [STRATEGY SELECTION] ---
# Import the strategies you want to test
from strategy import npattern_symmetric
# from rsi_strategy import RSIStrategy
# ------------------------------


if __name__ == "__main__":
    
    # --- [NEW] Set the active strategy here ---
    ACTIVE_STRATEGY = npattern_symmetric.SymmetricNPatternStrategy
    # ------------------------------------------

    # 1. Initialize the Engine with our config and selected strategy
    print(f"[Main] Initializing engine with strategy: {ACTIVE_STRATEGY.__name__}")
    engine = BacktestEngine(config=CONFIG, strategy_class=ACTIVE_STRATEGY)
    
    # 2. Run the backtest
    try:
        trades_log, balance_history = engine.run()
        
        # 3. Evaluate results
        if trades_log is not None and balance_history is not None:
            evaluate_event_driven_performance(
                trades_log, 
                balance_history, 
                engine.df_master, # Pass the master df for B&H comparison
                CONFIG['initial_capital']
            )
        
        # (Optional) Plotting the equity curve
        # import matplotlib.pyplot as plt
        # if balance_history is not None:
        #     balance_history['balance'].plot(title='Equity Curve')
        #     plt.show()
        
    except Exception as e:
        print(f"\n--- [FATAL ERROR] ---")
        print(f"An error occurred during the backtest: {e}")
        traceback.print_exc()