# strategy/top_gainer_selector.py
# Selects top gaining contracts from the available universe

import pandas as pd
from typing import List, Dict


class TopGainerSelector:
    """
    Selects top gaining contracts from the available universe
    based on 24-hour performance.
    """
    
    def __init__(self, config, data_handler):
        self.config = config
        self.data_handler = data_handler
        self.top_n = config['top_gainers_count']
    
    def select_top_gainers(
        self,
        available_symbols: List[str],
        current_time: pd.Timestamp,
        start_ts: int,
        end_ts: int
    ) -> List[str]:
        """
        Select top N gainers from available symbols based on 24h performance.
        
        Args:
            available_symbols: List of available contract symbols
            current_time: Current backtest timestamp
            start_ts: Start timestamp for data loading
            end_ts: End timestamp for data loading
            
        Returns:
            List of top N gaining symbols
        """
        performance: Dict[str, float] = {}
        
        for symbol in available_symbols:
            df = self.data_handler.load_contract_data(
                symbol, start_ts, end_ts, '1m'
            )
            
            if df is None or df.empty:
                continue
            
            change_24h = self.data_handler.calculate_24h_change(df, current_time)
            performance[symbol] = change_24h
        
        # Sort by 24h change (descending) and take top N
        sorted_symbols = sorted(
            performance.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        return [s[0] for s in sorted_symbols[:self.top_n]]