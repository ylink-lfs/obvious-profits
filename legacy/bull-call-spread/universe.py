# Dynamic Universe Selection for Squeeze Entry Options Strategy
# Implements the "Coiled Spring" selection methodology - Math-Only Version
# No fundamental data dependency - all filtering done via technical indicators
from AlgorithmImports import *
from typing import List, Dict, Optional, Tuple
from datetime import timedelta
import numpy as np
import config


class CoiledSpringUniverseSelection:
    """
    Dynamic stock selection based on volatility compression ("Coiled Spring").
    
    Math-Only Pipeline (No Fine Selection):
    1. Coarse Selection: Price range, volume filters -> Top 100
    2. History Request: Get historical data for technical calculations
    3. Technical Filter: Beta > 1.0, IV Percentile < 30%, BB Width < 20%, Price > MA200
    4. Scoring & Ranking: Rank by (1/IV_Percentile) * (1/BB_Width_Percentile)
    5. Return: Top N symbols
    """
    
    def __init__(self, algorithm):
        self.algo = algorithm
        self.spy_symbol = None
        self.last_selection_time = None
        self.selection_interval = timedelta(days=config.SELECTION_INTERVAL_DAYS)
        self.selected_symbols: List[Symbol] = []
        
        # Historical data cache
        self._spy_returns: np.ndarray = None
        self._last_spy_update = None
        
        # Add SPY for beta calculation
        self._initialize_spy()
    
    def _initialize_spy(self):
        """Initialize SPY for beta calculations."""
        self.spy_symbol = self.algo.add_equity("SPY", Resolution.DAILY).symbol
        self.algo.log("SPY added for beta calculation reference")
    
    def select_coarse(self, coarse: List) -> List[Symbol]:
        """
        Coarse selection with integrated technical filtering.
        
        Pipeline:
        1. Filter by price, volume
        2. Take top 100 by volume
        3. Request history and calculate technical indicators
        4. Apply technical filters (Beta, IV, BB, MA200)
        5. Score and rank
        6. Return top N symbols
        """
        # Check if we need to re-select
        if self.last_selection_time is not None:
            days_since_selection = (self.algo.time - self.last_selection_time).days
            if days_since_selection < config.SELECTION_INTERVAL_DAYS:
                # Return previously selected symbols
                if self.selected_symbols:
                    return self.selected_symbols
        
        self.algo.log(f"Running Coarse Selection at {self.algo.time}")
        
        # Step 1: Basic filters (price, volume)
        filtered = [
            x for x in coarse
            if x.has_fundamental_data
            and config.SELECTION_MIN_PRICE <= x.price <= config.SELECTION_MAX_PRICE
            and x.dollar_volume > config.SELECTION_MIN_VOLUME
        ]
        
        # Step 2: Sort by dollar volume and take top 100
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        top_candidates = sorted_by_volume[:config.COARSE_SELECTION_COUNT]
        
        self.algo.log(f"Coarse Filter: {len(filtered)} passed basic filters, taking top {len(top_candidates)}")
        
        if not top_candidates:
            return []
        
        # Step 3: Get symbols for history request
        candidate_symbols = [x.symbol for x in top_candidates]
        
        # Step 4: Apply technical filters via history
        final_symbols = self._apply_technical_filters(candidate_symbols)
        
        # Update cache
        self.selected_symbols = final_symbols
        self.last_selection_time = self.algo.time
        
        return final_symbols
    
    def _apply_technical_filters(self, symbols: List[Symbol]) -> List[Symbol]:
        """
        Apply all technical filters using historical data.
        
        Filters:
        1. Beta > 1.0 (relative to SPY)
        2. Price > MA200 (uptrend)
        3. BB Width Percentile < 20% (squeeze)
        4. IV Percentile < 30% (optional, if IV data available)
        
        Returns scored and ranked symbols.
        """
        # Request historical data for all candidates + SPY
        lookback_days = max(config.MA200_PERIOD, config.IV_PERCENTILE_LOOKBACK) + 10
        
        all_symbols = symbols + [self.spy_symbol]
        history = self.algo.history(all_symbols, lookback_days, Resolution.DAILY)
        
        if history.empty:
            self.algo.log("No historical data available for technical filtering")
            return []
        
        # Calculate SPY returns for beta
        spy_returns = self._calculate_returns(history, self.spy_symbol)
        if spy_returns is None or len(spy_returns) < config.BETA_LOOKBACK_DAYS:
            self.algo.log("Insufficient SPY data for beta calculation")
            return []
        
        scored_candidates: List[Tuple[Symbol, float, dict]] = []
        
        for symbol in symbols:
            try:
                metrics = self._calculate_symbol_metrics(history, symbol, spy_returns)
                if metrics is None:
                    continue
                
                # Apply filters
                if not self._passes_filters(metrics):
                    continue
                
                # Calculate score (lower IV and BB width = higher score)
                score = self._calculate_score(metrics)
                scored_candidates.append((symbol, score, metrics))
                
            except Exception as e:
                self.algo.debug(f"Error processing {symbol}: {e}")
                continue
        
        self.algo.log(f"Technical Filter: {len(scored_candidates)} passed all filters")
        
        # Sort by score descending and take top N
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        top_n = scored_candidates[:config.FINAL_SELECTION_COUNT]
        
        # Log selected symbols
        for symbol, score, metrics in top_n:
            self.algo.log(
                f"Selected: {symbol.value} | Score={score:.2f} | "
                f"Beta={metrics['beta']:.2f} | IV%={metrics['iv_percentile']:.1f}% | "
                f"BB%={metrics['bb_percentile']:.1f}% | Price/MA200={metrics['price_ma200_ratio']:.2f}"
            )
        
        return [symbol for symbol, _, _ in top_n]
    
    def _calculate_returns(self, history, symbol: Symbol) -> Optional[np.ndarray]:
        """Calculate daily returns for a symbol from history DataFrame."""
        try:
            if symbol not in history.index.get_level_values('symbol'):
                return None
            
            closes = history.loc[symbol]['close'].values
            if len(closes) < 2:
                return None
            
            returns = np.diff(closes) / closes[:-1]
            return returns
        except:
            return None
    
    def _calculate_symbol_metrics(self, history, symbol: Symbol, spy_returns: np.ndarray) -> Optional[dict]:
        """
        Calculate all technical metrics for a symbol.
        
        Returns dict with: beta, iv_percentile, bb_percentile, price_ma200_ratio, current_price
        """
        try:
            if symbol not in history.index.get_level_values('symbol'):
                return None
            
            symbol_data = history.loc[symbol]
            closes = symbol_data['close'].values
            highs = symbol_data['high'].values
            lows = symbol_data['low'].values
            
            if len(closes) < config.MA200_PERIOD:
                return None
            
            current_price = closes[-1]
            
            # 1. Calculate Beta (90-day)
            beta = self._calculate_beta(closes, spy_returns)
            if beta is None:
                return None
            
            # 2. Calculate MA200 and trend
            ma200 = np.mean(closes[-config.MA200_PERIOD:])
            price_ma200_ratio = current_price / ma200 if ma200 > 0 else 0
            
            # 3. Calculate BB Width Percentile
            bb_percentile = self._calculate_bb_width_percentile(closes)
            
            # 4. Calculate IV Percentile (using ATR as proxy if no options data)
            # In real implementation, this would use actual IV from options
            # Here we use historical volatility as a proxy
            iv_percentile = self._calculate_hv_percentile(closes)
            
            return {
                'beta': beta,
                'iv_percentile': iv_percentile,
                'bb_percentile': bb_percentile,
                'price_ma200_ratio': price_ma200_ratio,
                'current_price': current_price,
                'ma200': ma200
            }
            
        except Exception as e:
            self.algo.debug(f"Error calculating metrics for {symbol}: {e}")
            return None
    
    def _calculate_beta(self, closes: np.ndarray, spy_returns: np.ndarray) -> Optional[float]:
        """Calculate beta relative to SPY using 90-day returns."""
        try:
            lookback = min(config.BETA_LOOKBACK_DAYS, len(closes) - 1, len(spy_returns))
            if lookback < 30:  # Need at least 30 days
                return None
            
            # Calculate stock returns
            stock_returns = np.diff(closes[-lookback-1:]) / closes[-lookback-1:-1]
            spy_ret = spy_returns[-lookback:]
            
            if len(stock_returns) != len(spy_ret):
                min_len = min(len(stock_returns), len(spy_ret))
                stock_returns = stock_returns[-min_len:]
                spy_ret = spy_ret[-min_len:]
            
            # Calculate beta: Cov(stock, spy) / Var(spy)
            covariance = np.cov(stock_returns, spy_ret)[0, 1]
            spy_variance = np.var(spy_ret)
            
            if spy_variance == 0:
                return None
            
            beta = covariance / spy_variance
            return beta
            
        except:
            return None
    
    def _calculate_bb_width_percentile(self, closes: np.ndarray) -> float:
        """
        Calculate current BB width percentile over lookback period.
        
        BB Width = (Upper - Lower) / Middle
        Percentile = % of days where BB Width was lower than current
        """
        lookback = min(config.BB_WIDTH_PERCENTILE_LOOKBACK, len(closes) - config.BB_PERIOD)
        if lookback < 20:
            return 50.0  # Default to middle if not enough data
        
        bb_widths = []
        for i in range(lookback):
            idx = len(closes) - lookback + i
            if idx < config.BB_PERIOD:
                continue
            
            window = closes[idx - config.BB_PERIOD:idx]
            sma = np.mean(window)
            std = np.std(window)
            
            if sma > 0:
                bb_width = (2 * config.BB_STD * std) / sma
                bb_widths.append(bb_width)
        
        if not bb_widths:
            return 50.0
        
        current_bb_width = bb_widths[-1]
        count_below = sum(1 for w in bb_widths if w < current_bb_width)
        percentile = (count_below / len(bb_widths)) * 100
        
        return percentile
    
    def _calculate_hv_percentile(self, closes: np.ndarray) -> float:
        """
        Calculate historical volatility percentile as IV proxy.
        
        Uses 20-day rolling HV, then calculates percentile over lookback period.
        """
        hv_period = 20
        lookback = min(config.IV_PERCENTILE_LOOKBACK, len(closes) - hv_period)
        if lookback < 50:
            return 50.0  # Default to middle if not enough data
        
        hv_values = []
        for i in range(lookback):
            idx = len(closes) - lookback + i
            if idx < hv_period:
                continue
            
            window = closes[idx - hv_period:idx]
            returns = np.diff(window) / window[:-1]
            hv = np.std(returns) * np.sqrt(252)  # Annualized
            hv_values.append(hv)
        
        if not hv_values:
            return 50.0
        
        current_hv = hv_values[-1]
        count_below = sum(1 for hv in hv_values if hv < current_hv)
        percentile = (count_below / len(hv_values)) * 100
        
        return percentile
    
    def _passes_filters(self, metrics: dict) -> bool:
        """Check if metrics pass all required filters."""
        # Beta > 1.0
        if metrics['beta'] <= config.SELECTION_MIN_BETA:
            return False
        
        # Price > MA200 (uptrend)
        if metrics['price_ma200_ratio'] <= 1.0:
            return False
        
        # BB Width Percentile < threshold (squeeze)
        if metrics['bb_percentile'] > config.BB_WIDTH_PERCENTILE_THRESHOLD:
            return False
        
        # IV/HV Percentile < threshold (low volatility)
        if metrics['iv_percentile'] > config.IV_PERCENTILE_THRESHOLD * 100:
            return False
        
        return True
    
    def _calculate_score(self, metrics: dict) -> float:
        """
        Calculate ranking score. Higher = better candidate.
        
        Score = (1 / IV_Percentile) * (1 / BB_Percentile)
        Lower IV and BB percentile = higher score
        """
        epsilon = 1.0  # Avoid division by zero
        iv_score = 1.0 / (metrics['iv_percentile'] + epsilon)
        bb_score = 1.0 / (metrics['bb_percentile'] + epsilon)
        return iv_score * bb_score
    
    def get_selected_symbols(self) -> List[Symbol]:
        """Get the currently selected symbols."""
        return self.selected_symbols.copy()


class ManualUniverseSelection:
    """
    Simplified universe selection using a manually defined symbol pool.
    
    Still applies technical ranking when multiple symbols pass criteria.
    Used when DYNAMIC_UNIVERSE_SELECTION = False.
    """
    
    def __init__(self, algorithm, symbol_pool: List[str]):
        self.algo = algorithm
        self.symbol_pool = symbol_pool
        self.selected_symbols: List[str] = symbol_pool.copy()
    
    def get_tradable_symbols(self) -> List[str]:
        """
        Get symbols from the pool that pass basic technical filters.
        
        For manual mode, we rely on the signal generator to do detailed
        filtering. This just returns symbols that are in an uptrend.
        """
        tradable = []
        
        for symbol_str in self.symbol_pool:
            if symbol_str not in self.algo.symbol_data:
                continue
            
            data = self.algo.symbol_data[symbol_str]
            
            # Check if indicators are ready
            if not self._indicators_ready(data):
                continue
            
            # Get current price
            if not self.algo.securities.contains_key(data.equity_symbol):
                continue
            
            current_price = self.algo.securities[data.equity_symbol].price
            if current_price <= 0:
                continue
            
            # Basic filter: Price > MA200 (uptrend)
            if data.sma200 is not None and data.sma200.is_ready:
                if current_price > data.sma200.current.value:
                    tradable.append(symbol_str)
        
        return tradable
    
    def _indicators_ready(self, data) -> bool:
        """Check if required indicators are ready."""
        if data.sma200 is None or not data.sma200.is_ready:
            return False
        if data.bb is None or not data.bb.is_ready:
            return False
        return True
    
    def get_selected_symbols(self) -> List[str]:
        """Get the symbol pool."""
        return self.symbol_pool.copy()
