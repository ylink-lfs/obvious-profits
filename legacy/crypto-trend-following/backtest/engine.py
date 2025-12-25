# backtest/engine.py
# Backtest Engine - Orchestrates historical simulation
# Migrated from engine.py with updated imports

import json
import os
import gc
import time
import psutil
import numpy as np
import pandas as pd
from typing import Dict, List, Optional

from .data_loader import BacktestDataLoader
from .portfolio import BacktestPortfolio
from core.universe import UniverseManager
from strategy.meme_momentum import MemeStrategy
from strategy.top_gainer_selector import TopGainerSelector


class BacktestEngine:
    """
    Backtest engine for meme coin momentum strategy.
    
    Features:
    - Multi-contract universe management
    - Hourly universe refresh (top gainers selection)
    - Per-minute entry/exit signal evaluation
    - BTC circuit breaker integration
    
    Performance optimizations:
    - Numpy arrays for BTC data (avoid pandas overhead)
    - Pre-extracted numpy timestamps for O(log N) searchsorted
    - Cached index positions to avoid redundant lookups
    """
    
    def __init__(self, config):
        print("[Engine] Initializing BacktestEngine...")
        self.config = config
        
        # Core components
        self.data_handler = BacktestDataLoader(config)
        self.portfolio = BacktestPortfolio(config)
        self.universe_manager = UniverseManager(config)
        self.strategy = MemeStrategy(config)
        self.gainer_selector = TopGainerSelector(config, self.data_handler)
        
        # State
        self.current_universe: List[str] = []
        self.contract_data_cache: Dict[str, pd.DataFrame] = {}
        self.btc_spot_data: Optional[pd.DataFrame] = None
        
        # Performance: Numpy array caches for fast lookups
        self.contract_timestamps: Dict[str, np.ndarray] = {}  # symbol -> int64 timestamps
        self.contract_arrays: Dict[str, Dict[str, np.ndarray]] = {}  # symbol -> {col: array}
        self.btc_timestamps: Optional[np.ndarray] = None  # BTC int64 timestamps
        self.btc_close: Optional[np.ndarray] = None  # BTC close prices
        self.btc_ema_24h: Optional[np.ndarray] = None  # BTC 24h EMA
        self.btc_roc_1h: Optional[np.ndarray] = None  # BTC 1h change
        
        # Timing
        self.start_ts = config['backtest_start_date']
        self.end_ts = config['backtest_end_date']
        self.universe_check_interval = config['universe_check_interval_minutes']
        
        # PERFORMANCE: Load precomputed universe (if available)
        self.precomputed_universe: Dict[str, List[str]] = {}
        self.use_precomputed = self._load_precomputed_universe()
        
        # Daily trade limit tracking: {symbol: [list of trade dates]}
        self.daily_trades: Dict[str, List[str]] = {}  # symbol -> list of date strings
        self.max_daily_trades = config.get('max_daily_trades_per_symbol', 1)
        
        # [Cooldown] Track last exit time to prevent churn
        self.cooldown_tracker: Dict[str, int] = {}  # symbol -> last_exit_time_ms
        
        # [Rolling Window] Track loaded time ranges for each symbol
        # symbol -> (loaded_start_ms, loaded_end_ms)
        self.contract_loaded_ranges: Dict[str, tuple] = {}
        
        # Configuration for rolling window (memory optimization)
        # Keep 3 days history for indicators (24h EMA needs 1 day, giving 3x buffer)
        self.history_buffer_days = 3
        # Load 7 days of future data at a time to reduce IO frequency
        self.future_buffer_days = 7
    
    def _load_precomputed_universe(self) -> bool:
        """Load precomputed universe from JSON file if available."""
        universe_file = self.config.get('universe_cache_file', 'universe_precomputed.json')
        
        if not os.path.exists(universe_file):
            print(f"[Engine] WARNING: {universe_file} not found.")
            print("[Engine] Run 'python -m backtest.precompute_universe' first for 10x faster backtest!")
            print("[Engine] Falling back to real-time universe selection (slow)...")
            return False
        
        try:
            with open(universe_file, 'r', encoding='utf-8') as f:
                self.precomputed_universe = json.load(f)
            print(f"[Engine] Loaded precomputed universe: {len(self.precomputed_universe)} time periods")
            return True
        except Exception as e:
            print(f"[Engine] Failed to load precomputed universe: {e}")
            return False
    
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
        
        # 2b. Add indicators to BTC data (needed for regime filter)
        self.btc_spot_data = self.data_handler.prepare_indicators(self.btc_spot_data)
        
        # 2c. PERFORMANCE: Extract BTC data to numpy arrays for O(1) access
        print("[Engine] Step 2c: Converting BTC data to numpy arrays...")
        self._prepare_btc_numpy_arrays()
        
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
        
        # PERFORMANCE: Pre-convert timeline to numpy int64 for fast comparisons
        timeline_ns = timeline.values.astype('datetime64[ns]').astype(np.int64)
        
        start_time = time.time()

        # Use these thresholds for personal laptop with 8GB Memory
        RSS_THRESHOLD_GB = 6.0
        SYSTEM_MEM_PERCENT_THRESHOLD = 95.0
        SWAP_THRESHOLD_GB = 33.8
        CHECK_INTERVAL = 500
        process = psutil.Process(os.getpid())
        
        for i, current_time in enumerate(timeline):
            # Progress indicator with percentage and speed
            if i % 10000 == 0 and i > 0:
                elapsed = time.time() - start_time
                bars_per_sec = i / elapsed if elapsed > 0 else 0
                pct = (i / total_bars) * 100
                eta_secs = (total_bars - i) / bars_per_sec if bars_per_sec > 0 else 0
                eta_mins = eta_secs / 60
                print(f"[Engine] Progress: {pct:.1f}% ({i:,}/{total_bars:,}) | Speed: {bars_per_sec:,.0f} bars/s | ETA: {eta_mins:.1f} min")
            
            # [Memory Guard] Three-dimensional check
            if i % CHECK_INTERVAL == 0 and i > 0:
                mem_info = process.memory_info()
                rss_gb = mem_info.rss / (1024 ** 3)
                sys_mem = psutil.virtual_memory()
                swap_mem = psutil.swap_memory()
                swap_used_gb = swap_mem.used / (1024 ** 3)
                
                # Check all three conditions
                should_dump = False
                trigger_reason = ""
                
                if rss_gb > RSS_THRESHOLD_GB:
                    should_dump = True
                    trigger_reason = f"RSS ({rss_gb:.1f}GB > {RSS_THRESHOLD_GB}GB)"
                elif sys_mem.percent > SYSTEM_MEM_PERCENT_THRESHOLD:
                    should_dump = True
                    trigger_reason = f"System ({sys_mem.percent:.0f}% > {SYSTEM_MEM_PERCENT_THRESHOLD}%)"
                elif swap_used_gb > SWAP_THRESHOLD_GB:
                    should_dump = True
                    trigger_reason = f"Swap ({swap_used_gb:.1f}GB > {SWAP_THRESHOLD_GB}GB)"
                if should_dump:
                    print(f"\n[Memory] SURVIVOR DUMP by {trigger_reason}")
                    print(f"[Stats] RSS: {rss_gb:.1f}GB | Sys: {sys_mem.percent:.0f}% | Swap: {swap_used_gb:.1f}GB")
                    
                    # 1. Calculate survivor whitelist (active symbols)
                    active_symbols = set(self.current_universe) | set(self.portfolio.positions.keys())
                    print(f"[Memory] Preserving {len(active_symbols)} active symbols...")
                    
                    # 2. Clean Engine layer (only remove inactive)
                    engine_cached = list(self.contract_arrays.keys())
                    engine_del = 0
                    for symbol in engine_cached:
                        if symbol not in active_symbols:
                            if symbol in self.contract_data_cache: del self.contract_data_cache[symbol]
                            if symbol in self.contract_timestamps: del self.contract_timestamps[symbol]
                            if symbol in self.contract_arrays: del self.contract_arrays[symbol]
                            engine_del += 1
                    print(f"[Engine] Dropped {engine_del} inactive arrays.")
                    
                    # 3. Clean DataLoader layer (selective)
                    self.data_handler.keep_only(active_symbols)
                    
                    # 4. Force GC
                    gc.collect()
                    print("[Memory] Survivor cleanup done. Hot cache preserved.")
            
            current_time_ns = timeline_ns[i]  # Already pre-computed
            current_time_ms = current_time_ns // 10**6
            
            # 4a. Update universe hourly
            if self._should_update_universe(current_time, last_universe_update):
                self._update_universe(current_time, current_time_ms)
                last_universe_update = current_time
            
            # 4b. Get BTC 1h change for circuit breaker (FAST: numpy lookup)
            # CRITICAL: Use PREVIOUS bar's data to avoid look-ahead bias
            one_min_ns = 60 * 10**9  # 1 minute in nanoseconds
            prev_time_ns = current_time_ns - one_min_ns
            btc_1h_change = self._get_btc_1h_change_fast(prev_time_ns)
            
            # 4b2. Get BTC regime filter (BTC > 24h EMA) (FAST: numpy lookup)
            btc_above_ema = self._check_btc_regime_fast(prev_time_ns)
            
            # 4c. Check circuit breaker
            if not self.strategy.check_circuit_breaker(btc_1h_change):
                # Update balance history and skip
                self._update_balance_history(current_time)
                continue
            
            symbols_to_process = set(self.current_universe) | set(self.portfolio.positions.keys())
            for symbol in symbols_to_process:
                self._process_symbol(symbol, current_time, current_time_ns, btc_1h_change, btc_above_ema)
            
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
        
        # FAST PATH: Use precomputed universe (O(1) lookup, no IO)
        if self.use_precomputed:
            # Floor to hour boundary (precomputation is hourly)
            current_hour = current_time.floor('h')
            # Use lagged hour to avoid look-ahead bias
            lagged_hour = current_hour - pd.Timedelta(hours=1)
            ts_key = str(int(lagged_hour.value // 10**6))
            
            if ts_key in self.precomputed_universe:
                self.current_universe = self.precomputed_universe[ts_key]
            else:
                self.current_universe = []
            # [Stop-the-World GC] No per-hour cleanup - memory dump happens in main loop
            return
        
        # SLOW PATH: Real-time selection (fallback if no precomputed data)
        # Get available contracts
        available = self.universe_manager.get_available_contracts(current_time_ms)
        
        if not available:
            self.current_universe = []
            return
        
        # Select top gainers
        # CRITICAL: Use lagged time to avoid look-ahead bias
        lagged_time = current_time - pd.Timedelta(minutes=1)
        self.current_universe = self.gainer_selector.select_top_gainers(
            available, lagged_time, self.start_ts, self.end_ts
        )
        # [Stop-the-World GC] No per-hour cleanup - memory dump happens in main loop
    
    def _trigger_memory_dump(self):
        """
        [Stop-the-World GC] Nuclear option - clear ALL caches when memory critical.
        Data will be lazy-loaded as needed after dump.
        """
        # 1. Clear Engine layer caches
        self.contract_data_cache.clear()
        self.contract_timestamps.clear()
        self.contract_arrays.clear()
        
        # 2. Clear DataLoader layer cache
        self.data_handler.clear_all_cache()
        
        # 3. Force garbage collection
        gc.collect()
    
    def _process_symbol(
        self, 
        symbol: str, 
        current_time: pd.Timestamp,
        current_time_ns: int,
        btc_1h_change: float,
        btc_above_ema: bool = True
    ):
        """
        Process entry/exit logic for a single symbol.
        OPTIMIZED: Uses numpy arrays directly, no pandas iloc overhead.
        Supports dimension reduction: checks entries only at candle boundaries.
        """
        # Ensure data is loaded (triggers _get_contract_data which populates caches)
        current_time_ms = current_time_ns // 10**6
        if self._get_contract_data(symbol, current_time_ms) is None:
            return
        
        # Get numpy caches
        timestamps = self.contract_timestamps.get(symbol)
        arrays = self.contract_arrays.get(symbol)
        if timestamps is None or arrays is None:
            return
        
        # Fast index lookup
        idx = np.searchsorted(timestamps, current_time_ns, side='right') - 1
        
        # Need at least 3 bars
        if idx < 2:
            return
        
        # Check if we're at a strategy timeframe boundary (for entries only)
        # For 15m strategy: only check entries at 10:00, 10:15, 10:30, 10:45, etc.
        tf_mins = self.config.get('strategy_timeframe_minutes', 1)
        is_candle_close = (current_time.minute % tf_mins == 0)
        
        # ============================================================
        # FAST PATH: Extract scalar values directly from numpy arrays
        # This is 20-50x faster than df.iloc[idx] which creates Series
        # ============================================================
        
        # Current bar (idx) - for exit checks (always 1m precision)
        curr_high = arrays['high'][idx]
        curr_low = arrays['low'][idx]
        curr_atr = arrays['atr'][idx]
        
        # Check if we have a position in this symbol
        position = self.portfolio.get_position(symbol)
        
        # Get trade direction from config
        trade_direction = self.config.get('trade_direction', 'LONG')
        
        # [Day-1] Get listing time for this symbol (for Day-1 strategy mode)
        listing_time_ms = self.universe_manager.get_listing_time(symbol) or 0
        current_time_ms = current_time_ns // 1_000_000  # Convert ns to ms
        
        if position is not None:
            # --- FAST EXIT CHECK (1m precision maintained) ---
            # Exit checks run every minute for tight risk control
            entry_time_ns = position.entry_time.value  # Timestamp to nanoseconds
            
            # Use 1m data for exit precision
            prev_close = arrays['close'][idx - 1]
            
            should_exit, exit_reason, new_highest, new_lowest = self.strategy.check_exit_signal_fast(
                curr_high, curr_low, prev_close,
                position.entry_price, position.highest_price,
                entry_time_ns, current_time_ns,
                curr_atr if not np.isnan(curr_atr) else 0.0,
                position.lowest_price,
                position.side,
                listing_time_ms,
                current_time_ms
            )
            
            # Update position's price extremes
            position.highest_price = new_highest
            position.lowest_price = new_lowest
            
            if should_exit:
                # Calculate exit price with slippage
                slippage = self.config['slippage_rate']
                if position.side == 'LONG':
                    # LONG exit: selling, price slips down
                    if exit_reason == 'DisasterStop':
                        exit_price = curr_low * (1 - slippage)
                    else:
                        exit_price = arrays['close'][idx] * (1 - slippage)
                else:
                    # SHORT exit: buying back, price slips up
                    if exit_reason == 'DisasterStop':
                        exit_price = curr_high * (1 + slippage)
                    else:
                        exit_price = arrays['close'][idx] * (1 + slippage)
                
                self.portfolio.close_position(symbol, exit_price, current_time, exit_reason)
                
                # [Cooldown] Record exit time to prevent re-entry churn
                self.cooldown_tracker[symbol] = current_time_ms
        
        else:
            # --- ENTRY CHECK (filtered by strategy timeframe) ---
            # Only check entries at candle boundaries (e.g., every 15m)
            if not is_candle_close:
                return  # Not at strategy timeframe boundary, skip entry check
            
            if not self.portfolio.can_open_position():
                return
            
            # --- COOLDOWN CHECK (prevent churn) ---
            cooldown_mins = self.config.get('cooldown_minutes', 0)
            if cooldown_mins > 0:
                last_exit_ms = self.cooldown_tracker.get(symbol, 0)
                cooldown_ms = cooldown_mins * 60 * 1000
                if (current_time_ms - last_exit_ms) < cooldown_ms:
                    return  # Still in cooldown period
            
            # --- DAILY TRADE LIMIT CHECK ---
            date_str = current_time.strftime('%Y-%m-%d')
            if symbol not in self.daily_trades:
                self.daily_trades[symbol] = []
            
            if self.daily_trades[symbol].count(date_str) >= self.max_daily_trades:
                return  # Already hit daily limit for this symbol
            
            # Use strategy timeframe data (strat_* columns)
            # At 10:15, we read idx (current moment) which contains the just-completed 10:00-10:15 candle
            # This is safe because resample uses label='right': 10:15 timestamp = 10:00-10:15 data
            prev_close_strat = arrays['strat_close'][idx]
            prev_high_strat = arrays['strat_high'][idx]
            prev_volume_strat = arrays['strat_volume'][idx]
            prev_vol_ma_strat = arrays['strat_volume_ma'][idx]
            prev_bb_upper_strat = arrays['strat_bb_upper'][idx]
            prev_adx_strat = arrays['strat_adx'][idx]
            prev_ema_60_strat = arrays['strat_ema_60'][idx]
            coin_1h_change_strat = arrays['strat_roc_1h'][idx]
            
            if np.isnan(coin_1h_change_strat):
                coin_1h_change_strat = 0.0
            
            # BBP High (bar before previous) - previous period's high
            # For 15m strategy: go back 15 minutes to get previous candle
            prev_period_idx = max(0, idx - tf_mins)
            bbp_high_strat = arrays['strat_high'][prev_period_idx]
            
            # Get strat_open for SHORT logic (red candle detection)
            prev_open_strat = arrays['strat_open'][idx] if 'strat_open' in arrays else 0.0
            
            # [SHORT Strategy] Get VWAP, EMA 20, RSI for Post-Hype Butcher
            prev_ema_20 = arrays['ema_20'][idx] if 'ema_20' in arrays else np.nan
            prev_vwap = arrays['vwap'][idx] if 'vwap' in arrays else np.nan
            prev_rsi = arrays['rsi'][idx] if 'rsi' in arrays else np.nan
            
            # [Day-1] Calculate ORB (Opening Range Breakout) high price
            # listing_high_15m = max(high) of first 15 candles after listing
            listing_high_15m = 0.0
            if listing_time_ms > 0:
                wait_mins = self.config.get('day1_wait_minutes', 15)
                time_since_listing_ms = current_time_ms - listing_time_ms
                
                # Only calculate after wait period has passed
                if time_since_listing_ms >= wait_mins * 60 * 1000:
                    # Find the index of listing time in arrays
                    listing_ts_ns = listing_time_ms * 1_000_000
                    start_idx = np.searchsorted(timestamps, listing_ts_ns, side='left')
                    
                    if start_idx < len(timestamps):
                        # Get first 15 candles (assuming 1m data)
                        end_idx = min(start_idx + wait_mins, len(timestamps))
                        if end_idx > start_idx:
                            listing_high_15m = float(np.max(arrays['high'][start_idx:end_idx]))
            
            # Fast entry signal check using strategy timeframe data
            if self.strategy.check_entry_signal_fast(
                prev_close_strat, 
                prev_open_strat,  # Pass open for red candle check
                prev_high_strat,
                prev_volume_strat, 
                prev_vol_ma_strat, 
                prev_bb_upper_strat, 
                prev_adx_strat,
                bbp_high_strat, 
                coin_1h_change_strat, 
                btc_1h_change, 
                btc_above_ema,
                prev_ema_60_strat,
                trade_direction,
                listing_time_ms,
                current_time_ms,
                listing_high_15m,
                prev_ema_20,
                prev_vwap,
                prev_rsi
            ):
                # Calculate entry price with slippage (use 1m close for execution)
                slippage = self.config['slippage_rate']
                if trade_direction == 'LONG':
                    # LONG: buying, price slips up
                    entry_price = arrays['close'][idx] * (1 + slippage)
                else:
                    # SHORT: selling, price slips down
                    entry_price = arrays['close'][idx] * (1 - slippage)
                
                self.portfolio.open_position(symbol, entry_price, current_time, side=trade_direction)
                
                # Record this trade for daily limit tracking
                self.daily_trades[symbol].append(date_str)
    
    def _prepare_btc_numpy_arrays(self):
        """
        PERFORMANCE: Extract BTC data to numpy arrays for O(1) access.
        This avoids pandas overhead in the hot loop.
        """
        if self.btc_spot_data is None or self.btc_spot_data.empty:
            return
        
        # Extract timestamps as int64 nanoseconds (matches timeline_ns)
        self.btc_timestamps = self.btc_spot_data.index.values.astype('datetime64[ns]').astype(np.int64)
        self.btc_close = self.btc_spot_data['close'].values.astype(np.float64)
        
        if 'ema_24h' in self.btc_spot_data.columns:
            self.btc_ema_24h = self.btc_spot_data['ema_24h'].values.astype(np.float64)
        
        if 'roc_1h' in self.btc_spot_data.columns:
            self.btc_roc_1h = self.btc_spot_data['roc_1h'].values.astype(np.float64)
        
        print(f"[Engine] BTC numpy arrays prepared: {len(self.btc_timestamps):,} bars")
    
    def _get_btc_1h_change_fast(self, current_time_ns: int) -> float:
        """
        PERFORMANCE: Get BTC 1h change using numpy arrays.
        ~10x faster than pandas-based calculation.
        """
        if self.btc_timestamps is None or self.btc_roc_1h is None:
            return 0.0
        
        idx = np.searchsorted(self.btc_timestamps, current_time_ns, side='right') - 1
        if idx < 0 or idx >= len(self.btc_roc_1h):
            return 0.0
        
        val = self.btc_roc_1h[idx]
        return 0.0 if np.isnan(val) else float(val)
    
    def _check_btc_regime_fast(self, current_time_ns: int) -> bool:
        """
        PERFORMANCE: Check BTC regime using numpy arrays.
        ~10x faster than pandas-based calculation.
        """
        if self.btc_timestamps is None or self.btc_close is None or self.btc_ema_24h is None:
            return True  # Default to allowing trades
        
        idx = np.searchsorted(self.btc_timestamps, current_time_ns, side='right') - 1
        if idx < 0 or idx >= len(self.btc_close):
            return True
        
        close = self.btc_close[idx]
        ema = self.btc_ema_24h[idx]
        
        if np.isnan(ema):
            return True
        
        return close > ema
    
    def _get_contract_data(self, symbol: str, current_time_ms: int) -> Optional[pd.DataFrame]:
        """
        Get contract data, managing a rolling window to save memory.
        Auto-reloads if current_time exceeds the loaded future buffer.
        
        Instead of loading full history (2+ years), only loads:
        - 3 days of history (for indicator calculation)
        - 7 days of future data (buffer to reduce IO frequency)
        """
        # 1. Check if we have valid data in cache
        has_cache = symbol in self.contract_data_cache
        
        needs_reload = False
        if has_cache:
            # Check if we are approaching the end of loaded data
            _, loaded_end = self.contract_loaded_ranges.get(symbol, (0, 0))
            
            # If we are within 1 hour of running out of data, reload
            # (1 hour buffer ensures we don't crash mid-calculation)
            ms_until_end = loaded_end - current_time_ms
            if ms_until_end < 3600 * 1000:  # < 1 hour left
                needs_reload = True
        else:
            needs_reload = True
            
        if not needs_reload:
            return self.contract_data_cache[symbol]
            
        # 2. Calculate new window
        # Start: Current time - History Buffer
        load_start = current_time_ms - (self.history_buffer_days * 24 * 3600 * 1000)
        # End: Current time + Future Buffer
        load_end = current_time_ms + (self.future_buffer_days * 24 * 3600 * 1000)
        
        # Clamp to global backtest limits
        global_start = self.start_ts
        global_end = self.end_ts
        
        load_start = max(load_start, global_start)
        load_end = min(load_end, global_end)
        
        # Optimization: Don't reload if we hit the global end and already have data
        if has_cache:
            _, loaded_end = self.contract_loaded_ranges.get(symbol, (0, 0))
            if loaded_end >= global_end:
                return self.contract_data_cache[symbol]

        # 3. Load the specific chunk
        df = self.data_handler.load_contract_data(
            symbol, load_start, load_end, '1m'
        )
        
        if df is not None and not df.empty:
            # Add indicators (Calculated only on this chunk + history buffer)
            df = self.data_handler.prepare_indicators(df)
            
            # Update caches
            self.contract_data_cache[symbol] = df
            self.contract_loaded_ranges[symbol] = (load_start, load_end)
            
            # PERFORMANCE: Cache numpy timestamps for fast searchsorted
            self.contract_timestamps[symbol] = df.index.values.astype('datetime64[ns]').astype(np.int64)
            
            # PERFORMANCE: Extract all columns as numpy arrays for hot loop
            # This eliminates pandas iloc overhead (20-50x speedup)
            self.contract_arrays[symbol] = {
                'open': df['open'].values.astype(np.float64),
                'high': df['high'].values.astype(np.float64),
                'low': df['low'].values.astype(np.float64),
                'close': df['close'].values.astype(np.float64),
                'volume': df['volume'].values.astype(np.float64),
                'volume_ma': df['volume_ma'].values.astype(np.float64) if 'volume_ma' in df.columns else np.full(len(df), np.nan),
                'bb_upper': df['bb_upper'].values.astype(np.float64) if 'bb_upper' in df.columns else np.full(len(df), np.nan),
                'adx': df['adx'].values.astype(np.float64) if 'adx' in df.columns else np.full(len(df), np.nan),
                'atr': df['atr'].values.astype(np.float64) if 'atr' in df.columns else np.full(len(df), np.nan),
                'roc_1h': df['roc_1h'].values.astype(np.float64) if 'roc_1h' in df.columns else np.full(len(df), np.nan),
                'ema_60': df['ema_60'].values.astype(np.float64) if 'ema_60' in df.columns else np.full(len(df), np.nan),
                # Strategy timeframe columns (for dimension reduction)
                'strat_bb_upper': df['strat_bb_upper'].values.astype(np.float64) if 'strat_bb_upper' in df.columns else np.full(len(df), np.nan),
                'strat_volume': df['strat_volume'].values.astype(np.float64) if 'strat_volume' in df.columns else np.full(len(df), np.nan),
                'strat_volume_ma': df['strat_volume_ma'].values.astype(np.float64) if 'strat_volume_ma' in df.columns else np.full(len(df), np.nan),
                'strat_adx': df['strat_adx'].values.astype(np.float64) if 'strat_adx' in df.columns else np.full(len(df), np.nan),
                'strat_ema_60': df['strat_ema_60'].values.astype(np.float64) if 'strat_ema_60' in df.columns else np.full(len(df), np.nan),
                'strat_roc_1h': df['strat_roc_1h'].values.astype(np.float64) if 'strat_roc_1h' in df.columns else np.full(len(df), np.nan),
                'strat_close': df['strat_close'].values.astype(np.float64) if 'strat_close' in df.columns else np.full(len(df), np.nan),
                'strat_high': df['strat_high'].values.astype(np.float64) if 'strat_high' in df.columns else np.full(len(df), np.nan),
                'strat_open': df['strat_open'].values.astype(np.float64) if 'strat_open' in df.columns else np.full(len(df), np.nan),
            }
        
        return df
    
    def _update_balance_history(self, current_time: pd.Timestamp):
        """Update portfolio balance history."""
        current_prices = {}
        current_time_ns = current_time.value  # Already in nanoseconds
        
        for symbol in self.portfolio.positions:
            timestamps = self.contract_timestamps.get(symbol)
            df = self.contract_data_cache.get(symbol)
            
            if timestamps is not None and df is not None and len(df) > 0:
                # PERFORMANCE: Use numpy searchsorted
                idx = np.searchsorted(timestamps, current_time_ns, side='right') - 1
                if idx >= 0:
                    current_prices[symbol] = df['close'].iloc[idx]
        
        self.portfolio.update_balance_history(current_time, current_prices)
    
    def _close_all_positions(self, end_time: pd.Timestamp):
        """Force close all remaining positions at end of backtest."""
        symbols_to_close = list(self.portfolio.positions.keys())
        end_time_ns = end_time.value  # Already in nanoseconds
        
        for symbol in symbols_to_close:
            timestamps = self.contract_timestamps.get(symbol)
            df = self.contract_data_cache.get(symbol)
            position = self.portfolio.get_position(symbol)
            
            if timestamps is not None and df is not None and len(df) > 0 and position is not None:
                # PERFORMANCE: Use numpy searchsorted
                idx = np.searchsorted(timestamps, end_time_ns, side='right') - 1
                if idx >= 0:
                    exit_price = df['close'].iloc[idx]
                    # Apply slippage based on position direction
                    slippage = self.config['slippage_rate']
                    if position.side == 'LONG':
                        exit_price = exit_price * (1 - slippage)  # LONG exit: sell, price slips down
                    else:
                        exit_price = exit_price * (1 + slippage)  # SHORT exit: buy back, price slips up
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


# Alias for backward compatibility
MemeBacktestEngine = BacktestEngine
