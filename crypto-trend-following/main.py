# main.py
# [MODIFIED] Assembles Mean Reversion Strategy + ADX Chop Filter

import traceback
from engine import BacktestEngine
from evaluate import evaluate_event_driven_performance
from config import CONFIG

# Import new components
from strategy.mean_revision import BollingerMeanReversion
from filters.adx_filter import ADXFilter

def run_phase(phase_name, start_date, end_date):
    print(f"\n\n{'='*20} RUNNING {phase_name} PHASE {'='*20}")
    
    # --- Architecture: Dependency Injection ---
    
    # 1. Create Filter: We want to trade when ADX is LOW (Weak Trend)
    active_filters = [
        ADXFilter(CONFIG, mode='weak') 
    ]
    
    # 2. Create Engine with Mean Reversion Strategy
    engine = BacktestEngine(
        config=CONFIG, 
        strategy_class=BollingerMeanReversion,
        start_date=start_date,
        end_date=end_date,
        filters=active_filters
    )
    
    try:
        trades_log, balance_history = engine.run()
        if trades_log is not None:
            evaluate_event_driven_performance(
                trades_log, 
                balance_history, 
                engine.df_master, 
                CONFIG['initial_capital']
            )
    except Exception as e:
        print(f"Error in {phase_name}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # 1. Run Training Phase
    run_phase("TRAINING", CONFIG['train_start_date'], CONFIG['train_end_date'])
    
    # 2. Run Testing Phase
    run_phase("TESTING", CONFIG['test_start_date'], CONFIG['test_end_date'])