# engine.py
# Meme Coin Strategy Backtest Engine
# Orchestrates the backtest loop across multiple contracts

import pandas as pd
from typing import Dict, List, Optional
from data_handler import MemeDataHandler
from portfolio import MemePortfolio
from universe import UniverseManager
from strategy.meme_momentum import MemeStrategy
from strategy.top_gainer_selector import TopGainerSelector


class MemeBacktestEngine:
    """
    Backtest engine for meme coin momentum strategy.
    
    Features:
    - Multi-contract universe management
    - Hourly universe refresh (top gainers selection)
    - Per-minute entry/exit signal evaluation
    - BTC circuit breaker integration
    """
    
    def __init__(self, config):
        print("[Engine] Initializing MemeBacktestEngine...")
        self.config = config
        
        # Core components
        self.data_handler = MemeDataHandler(config)
        self.portfolio = MemePortfolio(config)
        self.universe_manager = UniverseManager(config)
        self.strategy = MemeStrategy(config)
        self.gainer_selector = TopGainerSelector(config, self.data_handler)
        
        # State
        self.current_universe: List[str] = []
        self.contract_data_cache: Dict[str, pd.DataFrame] = {}
        self.btc_spot_data: Optional[pd.DataFrame] = None
        
        # Timing
        self.start_ts = config['backtest_start_date']
        self.end_ts = config['backtest_end_date']
        self.universe_check_interval = config['universe_check_interval_minutes']
    
    def run(self):
        """Run the full backtest."""
        print(f"\n{'='*50}")
        print("[Engine] Starting Meme Coin Strategy Backtest")
        print(f"{'='*50}")
        
        # 1. Initialize universe
        print("\n[Engine] Step 1: Scanning contract universe...")
        self.universe_manager.initialize()
        
        # 2. Load BTC spot data for circuit breaker
        print("\n[Engine] Step 2: Loading BTC spot data...")
        self.btc_spot_data = self.data_handler.load_btc_spot_data(
            self.start_ts, self.end_ts
        )
        
        if self.btc_spot_data is None or self.btc_spot_data.empty:
            print("[Engine] ERROR: Could not load BTC spot data")
            return None, None
        
        # 3. Generate time index (1-minute intervals)
        print("\n[Engine] Step 3: Generating backtest timeline...")
        timeline = pd.date_range(
            start=pd.to_datetime(self.start_ts, unit='ms'),
            end=pd.to_datetime(self.end_ts, unit='ms'),
            freq='1min'
        )
        
        print(f"[Engine] Backtest period: {timeline[0]} to {timeline[-1]}")
        print(f"[Engine] Total bars: {len(timeline)}")
        
        # 4. Main backtest loop
        print("\n[Engine] Step 4: Running backtest loop...")
        last_universe_update = None
        total_bars = len(timeline)
        
        # Progress tracking
        import time
        start_time = time.time()
        
        for i, current_time in enumerate(timeline):
            # Progress indicator with percentage and speed
            if i % 10000 == 0 and i > 0:
                elapsed = time.time() - start_time
                bars_per_sec = i / elapsed if elapsed > 0 else 0
                pct = (i / total_bars) * 100
                eta_secs = (total_bars - i) / bars_per_sec if bars_per_sec > 0 else 0
                eta_mins = eta_secs / 60
                print(f"[Engine] Progress: {pct:.1f}% ({i:,}/{total_bars:,}) | Speed: {bars_per_sec:,.0f} bars/s | ETA: {eta_mins:.1f} min")
            
            current_time_ms = int(current_time.value // 10**6)
            
            # 4a. Update universe hourly
            if self._should_update_universe(current_time, last_universe_update):
                self._update_universe(current_time, current_time_ms)
                last_universe_update = current_time
            
            # 4b. Get BTC 1h change for circuit breaker
            btc_1h_change = self.data_handler.calculate_hourly_change(
                self.btc_spot_data, current_time
            )
            
            # 4c. Check circuit breaker
            if not self.strategy.check_circuit_breaker(btc_1h_change):
                # Update balance history and skip
                self._update_balance_history(current_time)
                continue
            
            # 4d. Process each symbol in current universe
            for symbol in self.current_universe:
                self._process_symbol(symbol, current_time, current_time_ms, btc_1h_change)
            
            # 4e. Update balance history
            self._update_balance_history(current_time)
        
        # 5. Force close any remaining positions
        print("\n[Engine] Step 5: Closing remaining positions...")
        self._close_all_positions(timeline[-1])
        
        print("\n[Engine] Backtest complete!")
        
        # Return results
        trades_df = self._get_trades_dataframe()
        balance_df = pd.DataFrame(self.portfolio.balance_history).set_index('timestamp')
        
        return trades_df, balance_df
    
    def _should_update_universe(
        self, 
        current_time: pd.Timestamp, 
        last_update: Optional[pd.Timestamp]
    ) -> bool:
        """Check if universe should be updated."""
        if last_update is None:
            return True
        
        minutes_since_update = (current_time - last_update).total_seconds() / 60
        return minutes_since_update >= self.universe_check_interval
    
    def _update_universe(self, current_time: pd.Timestamp, current_time_ms: int):
        """Update the trading universe with top gainers."""
        # Get available contracts
        available = self.universe_manager.get_available_contracts(current_time_ms)
        
        if not available:
            self.current_universe = []
            return
        
        # Select top gainers
        # Use fixed backtest time range to ensure DataHandler cache hits
        # (The calculate_24h_change function uses searchsorted internally,
        # so it only needs data that "contains" the time point, not exact 24h slice)
        self.current_universe = self.gainer_selector.select_top_gainers(
            available, current_time, self.start_ts, self.end_ts
        )
    
    def _process_symbol(
        self, 
        symbol: str, 
        current_time: pd.Timestamp,
        current_time_ms: int,
        btc_1h_change: float
    ):
        """Process entry/exit logic for a single symbol."""
        # Load/get contract data
        df = self._get_contract_data(symbol, current_time_ms)
        if df is None or df.empty:
            return
        
        # Get current and previous bars using O(log N) binary search
        # searchsorted with side='right' finds the insertion point after any existing entries
        idx = df.index.searchsorted(current_time, side='right') - 1
        
        # Need at least 2 bars (current + previous)
        if idx < 1:
            return
        
        # Direct O(1) access by index position - no memory copy
        current_bar = df.iloc[idx]
        prev_bar = df.iloc[idx - 1]
        
        # Check if we have a position in this symbol
        position = self.portfolio.get_position(symbol)
        
        if position is not None:
            # Check exit conditions
            # For structural exit, we compare prev_bar's close against lowest_low
            # of the 20 candles BEFORE prev_bar (excluding current and prev bars)
            lowest_low = self.data_handler.get_lowest_low(
                df, current_time, self.config['structural_exit_lookback'], exclude_last=1
            )
            
            should_exit, exit_reason = self.strategy.check_exit_signal(
                current_bar, prev_bar, position, lowest_low, current_time
            )
            
            if should_exit:
                exit_price = self.strategy.calculate_exit_price(current_bar, exit_reason)
                self.portfolio.close_position(symbol, exit_price, current_time, exit_reason)
        
        else:
            # Check entry conditions (only if we can open a position)
            if not self.portfolio.can_open_position():
                return
            
            # Get coin's 1h change
            coin_1h_change = self.data_handler.calculate_hourly_change(df, current_time)
            
            # Check entry signal
            if self.strategy.check_entry_signal(prev_bar, coin_1h_change, btc_1h_change):
                entry_price = self.strategy.calculate_entry_price(prev_bar)
                self.portfolio.open_position(symbol, entry_price, current_time)
    
    def _get_contract_data(self, symbol: str, current_time_ms: int = 0) -> Optional[pd.DataFrame]:
        """Get contract data with indicators, using cache."""
        _ = current_time_ms  # Reserved for future use
        if symbol in self.contract_data_cache:
            return self.contract_data_cache[symbol]
        
        # Load data for this contract
        # Use full backtest range
        df = self.data_handler.load_contract_data(
            symbol, self.start_ts, self.end_ts, '1m'
        )
        
        if df is not None and not df.empty:
            # Add indicators
            df = self.data_handler.prepare_indicators(df)
            self.contract_data_cache[symbol] = df
        
        return df
    
    def _update_balance_history(self, current_time: pd.Timestamp):
        """Update portfolio balance history."""
        current_prices = {}
        
        for symbol in self.portfolio.positions:
            df = self.contract_data_cache.get(symbol)
            if df is not None and len(df) > 0:
                # O(log N) binary search instead of O(N) boolean mask
                idx = df.index.searchsorted(current_time, side='right') - 1
                if idx >= 0:
                    current_prices[symbol] = df['close'].iloc[idx]
        
        self.portfolio.update_balance_history(current_time, current_prices)
    
    def _close_all_positions(self, end_time: pd.Timestamp):
        """Force close all remaining positions at end of backtest."""
        symbols_to_close = list(self.portfolio.positions.keys())
        
        for symbol in symbols_to_close:
            df = self.contract_data_cache.get(symbol)
            if df is not None and len(df) > 0:
                # O(log N) binary search instead of O(N) boolean mask
                idx = df.index.searchsorted(end_time, side='right') - 1
                if idx >= 0:
                    exit_price = df['close'].iloc[idx]
                    # Apply slippage
                    exit_price = exit_price * (1 - self.config['slippage_rate'])
                    self.portfolio.close_position(symbol, exit_price, end_time, 'EndOfBacktest')
    
    def _get_trades_dataframe(self) -> pd.DataFrame:
        """Convert trades log to DataFrame."""
        if not self.portfolio.trades_log:
            return pd.DataFrame()
        
        trades_data = []
        for trade in self.portfolio.trades_log:
            trades_data.append({
                'symbol': trade.symbol,
                'entry_time': trade.entry_time,
                'exit_time': trade.exit_time,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'size_usd': trade.size_usd,
                'pnl_usd': trade.pnl_usd,
                'pnl_pct': trade.pnl_pct,
                'exit_reason': trade.exit_reason,
                'fees_paid': trade.fees_paid
            })
        
        return pd.DataFrame(trades_data)