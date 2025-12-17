# strategy/top_gainer_selector.py
# Selects top gaining contracts from the available universe

import pandas as pd
from typing import List, Dict, Tuple


class TopGainerSelector:
    """
    Selects top gaining contracts from the available universe
    based on 24-hour performance with liquidity filter.
    
    Selection strategy:
    1. Filter by minimum 24h quote volume (liquidity)
    2. Rank by 24h price change
    3. Select Top X% of gainers with min/max bounds
    """
    
    def __init__(self, config, data_handler):
        self.config = config
        self.data_handler = data_handler
        self.top_pct = config['top_gainers_pct']
        self.min_count = config['top_gainers_min']
        self.max_count = config['top_gainers_max']
        # Minimum 24h quote volume in USDT (default 10M)
        self.min_liquidity = config.get('min_24h_quote_volume', 10_000_000)
    
    def select_top_gainers(
        self,
        available_symbols: List[str],
        current_time: pd.Timestamp,
        start_ts: int,
        end_ts: int
    ) -> List[str]:
        """
        Select top gainers from available symbols based on 24h performance.
        
        Selection logic:
        1. Filter by liquidity: 24h quote volume > min_liquidity (default 10M USDT)
        2. Rank remaining symbols by 24h price change
        3. Select Top X% of gainers, bounded by [min_count, max_count]
        
        For example, with 10% and bounds [5, 20]:
        - 30 symbols -> top 10% = 3, but min is 5, so select 5
        - 100 symbols -> top 10% = 10, within bounds, so select 10
        - 300 symbols -> top 10% = 30, but max is 20, so select 20
        
        Args:
            available_symbols: List of available contract symbols
            current_time: Current backtest timestamp
            start_ts: Start timestamp for data loading
            end_ts: End timestamp for data loading
            
        Returns:
            List of top gaining symbols
        """
        # Step 1: Load data and calculate metrics for all symbols
        symbol_metrics: Dict[str, Tuple[float, float]] = {}  # symbol -> (change_24h, volume_24h)
        
        for symbol in available_symbols:
            df = self.data_handler.load_contract_data(
                symbol, start_ts, end_ts, '1m'
            )
            
            if df is None or df.empty:
                continue
            
            change_24h = self.data_handler.calculate_24h_change(df, current_time)
            volume_24h = self.data_handler.calculate_24h_quote_volume(df, current_time)
            symbol_metrics[symbol] = (change_24h, volume_24h)
        
        # Step 2: Filter by liquidity (24h quote volume > threshold)
        liquid_symbols = {
            symbol: metrics[0]  # Keep only change_24h for ranking
            for symbol, metrics in symbol_metrics.items()
            if metrics[1] >= self.min_liquidity
        }
        
        # Step 3: Sort by 24h change (descending)
        sorted_symbols = sorted(
            liquid_symbols.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        # Step 4: Calculate selection count: Top X% with min/max bounds
        total_count = len(sorted_symbols)
        top_count = int(total_count * self.top_pct)
        
        # Apply min/max bounds
        select_count = max(self.min_count, min(self.max_count, top_count))
        
        # Don't select more than available
        select_count = min(select_count, total_count)
        
        return [s[0] for s in sorted_symbols[:select_count]]