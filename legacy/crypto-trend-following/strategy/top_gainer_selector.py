# strategy/top_gainer_selector.py
# Selects top gaining contracts from the available universe
# Using Dynamic Trinity filters: Liquidity, Volatility (NATR), Trend (EMA)

import pandas as pd
from typing import List, Tuple, Optional


class TopGainerSelector:
    """
    Selects top gaining contracts using the Dynamic Trinity filter system:
    
    1. Liquidity Filter (Anti-Pump): 24h volume > 50M USDT
       - Ensures the coin is "globally hot", not a single-player pump
    
    2. Volatility Filter (Anti-Major): NATR > 5%
       - Filters out low-volatility "dead fish" like LTC, EOS
       - Meme coins need high volatility to cover trading friction
    
    3. Trend Filter (Anti-Zombie): Price > EMA(96h)
       - Filters out bottom-fishing "zombie" coins in deep downtrend
       - Only trade "strong gets stronger" breakouts
    
    After filtering, rank by 24h change and select top performers.
    """
    
    def __init__(self, config, data_handler):
        self.config = config
        self.data_handler = data_handler
        self.top_pct = config['top_gainers_pct']
        self.min_count = config['top_gainers_min']
        self.max_count = config['top_gainers_max']
        # Dynamic Trinity thresholds
        self.min_liquidity = config.get('min_24h_quote_volume', 50_000_000)  # 50M USDT
        self.min_natr = config.get('min_natr', 0.05)  # 5% daily range
        self.ema_span = config.get('ema_trend_span', 96 * 60)  # 96 hours in minutes
    
    def _calculate_natr(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """
        Calculate Normalized ATR (24h High-Low range / Close).
        This measures daily volatility as a percentage.
        
        High NATR (>5%) = Meme coin territory (PEPE, WIF, DOGE)
        Low NATR (<3%) = Dead fish territory (LTC, XRP, EOS)
        """
        if df is None or df.empty:
            return 0.0
        
        try:
            # Get index for current time
            idx = df.index.searchsorted(current_time, side='right') - 1
            if idx < 1440:  # Need at least 24h of data
                return 0.0
            
            # Get 24h high and low
            start_idx = max(0, idx - 1440)
            high_24h = df['high'].iloc[start_idx:idx + 1].max()
            low_24h = df['low'].iloc[start_idx:idx + 1].min()
            current_close = df['close'].iloc[idx]
            
            if current_close <= 0:
                return 0.0
            
            # NATR = (High - Low) / Close
            natr = (high_24h - low_24h) / current_close
            return float(natr)
            
        except Exception:
            return 0.0
    
    def _calculate_ema(self, df: pd.DataFrame, current_time: pd.Timestamp, span: int) -> Optional[float]:
        """
        Calculate EMA at current time with given span (in minutes).
        Uses fast ewm calculation.
        """
        if df is None or df.empty:
            return None
        
        try:
            idx = df.index.searchsorted(current_time, side='right') - 1
            if idx < span:
                return None  # Not enough data for EMA
            
            # Calculate EMA up to current index
            # For efficiency, we use a pre-sliced series
            close_series = df['close'].iloc[:idx + 1]
            ema = close_series.ewm(span=span, adjust=False).mean().iloc[-1]
            return float(ema)
            
        except Exception:
            return None
    
    def _get_current_close(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """Get current close price."""
        if df is None or df.empty:
            return 0.0
        
        try:
            idx = df.index.searchsorted(current_time, side='right') - 1
            if idx < 0:
                return 0.0
            return float(df['close'].iloc[idx])
        except Exception:
            return 0.0
    
    def select_top_gainers(
        self,
        available_symbols: List[str],
        current_time: pd.Timestamp,
        start_ts: int,
        end_ts: int
    ) -> List[str]:
        """
        Select top gainers using Dynamic Trinity filter system.
        
        Filter Pipeline:
        1. Liquidity: 24h volume > 50M USDT (anti-pump filter)
        2. Volatility: NATR > 5% (anti-major filter, kills LTC/EOS)
        3. Trend: Close > EMA(96h) (anti-zombie filter)
        4. Rank by 24h change, select top performers
        
        Args:
            available_symbols: List of available contract symbols
            current_time: Current backtest timestamp
            start_ts: Start timestamp for data loading
            end_ts: End timestamp for data loading
            
        Returns:
            List of top gaining symbols that pass all filters
        """
        candidates: List[Tuple[str, float]] = []  # (symbol, change_24h)
        
        for symbol in available_symbols:
            df = self.data_handler.load_contract_data(
                symbol, start_ts, end_ts, '1m'
            )
            
            if df is None or df.empty:
                continue
            
            # --- Filter I: Liquidity (Anti-Pump) ---
            volume_24h = self.data_handler.calculate_24h_quote_volume(df, current_time)
            if volume_24h < self.min_liquidity:
                continue
            
            # --- Filter II: Volatility (Anti-Major) ---
            # NATR > 5% filters out dead fish like LTC, XRP, EOS
            natr = self._calculate_natr(df, current_time)
            if natr < self.min_natr:
                continue
            
            # --- Filter III: Trend Structure (Anti-Zombie) ---
            # Price > EMA(96h) filters out bottom-fishing zombie coins
            current_close = self._get_current_close(df, current_time)
            ema_96h = self._calculate_ema(df, current_time, self.ema_span)
            
            if ema_96h is not None and current_close < ema_96h:
                continue  # Skip coins in downtrend
            
            # --- Passed all filters, add to candidates ---
            change_24h = self.data_handler.calculate_24h_change(df, current_time)
            candidates.append((symbol, change_24h))
        
        # Rank by 24h change (strongest first)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Calculate selection count: Top X% with min/max bounds
        total_count = len(candidates)
        top_count = int(total_count * self.top_pct)
        
        # Apply min/max bounds
        select_count = max(self.min_count, min(self.max_count, top_count))
        
        # Don't select more than available
        select_count = min(select_count, total_count)
        
        return [c[0] for c in candidates[:select_count]]