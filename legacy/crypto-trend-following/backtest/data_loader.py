# backtest/data_loader.py\n# Backtest Data Loader - Loads historical data from ZIP files\n# Migrated from data_handler.py with updated imports

import pandas as pd
import pandas_ta  # noqa: F401 - registers df.ta accessor
import os
import zipfile
import glob
from typing import Dict, Optional, List, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing


# Standalone function for parallel execution (must be at module level for pickling)
def _read_zip_file_standalone(zip_path: str) -> Optional[pd.DataFrame]:
    """
    Read CSV data from a zip file (standalone version for multiprocessing).
    First checks if an extracted CSV file exists next to the zip file.
    If CSV exists, loads it directly. Otherwise, extracts from zip and saves CSV.
    """
    column_names = [
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'number_of_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ]
    
    # Check for cached CSV file (same name as zip but with .csv extension)
    csv_cache_path = zip_path.replace('.zip', '.csv')
    
    try:
        # Fast path: load from cached CSV if exists
        if os.path.exists(csv_cache_path):
            df = pd.read_csv(csv_cache_path)
            # Handle microseconds timestamps (2025+ data)
            if df['open_time'].iloc[0] > 1e15:
                df['open_time'] = df['open_time'] // 1000
            return df
        
        # Slow path: extract from zip and cache
        with zipfile.ZipFile(zip_path, 'r') as zf:
            csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
            if not csv_files:
                return None
            
            with zf.open(csv_files[0]) as csv_file:
                df_probe = pd.read_csv(csv_file, nrows=1, header=None)
                if df_probe.empty:
                    return None
                first_value = df_probe.iloc[0, 0]
                has_header = False
                try:
                    int(first_value)
                except (ValueError, TypeError):
                    has_header = True
            
            with zf.open(csv_files[0]) as csv_file:
                if has_header:
                    df = pd.read_csv(csv_file)
                    df.columns = column_names[:len(df.columns)]
                else:
                    df = pd.read_csv(csv_file, header=None, names=column_names)
                
                # Handle microseconds timestamps (2025+ data)
                if df['open_time'].iloc[0] > 1e15:
                    df['open_time'] = df['open_time'] // 1000
                
                # Save to CSV cache for future runs
                try:
                    df.to_csv(csv_cache_path, index=False)
                except Exception:
                    pass  # Ignore write errors (permissions, disk space, etc.)
                
                return df
    except Exception:
        return None


class BacktestDataLoader:
    """
    Data loader for backtest engine.
    Loads historical kline data from Binance ZIP files.
    
    Supports:
    - Multiple date range folders (e.g., 2020-2021 and 2021-2024 split)
    - Dynamic header detection in CSV files
    - Indicator pre-calculation for vectorized performance
    """
    
    def __init__(self, config):
        print("[DataLoader] Initializing Fast Cache Mode (Periodic Dump)...")
        self.config = config
        self.futures_data_path = config['futures_data_path']
        self.spot_data_path = config['spot_data_path']
        
        # Simple cache - just store, Engine will trigger full dump when memory high
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._btc_spot_cache: Optional[pd.DataFrame] = None
    
    def load_contract_data(
        self, 
        symbol: str, 
        start_ts: int, 
        end_ts: int,
        timeframe: str = '1m'
    ) -> Optional[pd.DataFrame]:
        """
        Load kline data for a specific contract.
        
        Args:
            symbol: Contract symbol (e.g., 'BTCUSDT')
            start_ts: Start timestamp in milliseconds
            end_ts: End timestamp in milliseconds
            timeframe: Kline timeframe (default '1m')
            
        Returns:
            DataFrame with OHLCV data indexed by timestamp
        """
        # [Smart Cache] Use symbol as key (start/end are constant during backtest)
        cache_key = symbol
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]
        
        # Construct path to contract data
        contract_path = os.path.join(self.futures_data_path, symbol, timeframe)
        
        if not os.path.exists(contract_path):
            return None
        
        df = self._load_zip_data(contract_path, symbol, timeframe, start_ts, end_ts)
        
        if df is not None and not df.empty:
            # [Memory Optimization] Convert float64 -> float32 (50% memory savings)
            float_cols = df.select_dtypes(include=['float64']).columns
            df[float_cols] = df[float_cols].astype('float32')
            
            # Store in cache
            self._data_cache[cache_key] = df
        
        return df
    
    def load_btc_spot_data(self, start_ts: int, end_ts: int) -> Optional[pd.DataFrame]:
        """
        Load BTC spot data for reference (circuit breaker, relative strength).
        
        Args:
            start_ts: Start timestamp in milliseconds
            end_ts: End timestamp in milliseconds
            
        Returns:
            DataFrame with BTCUSDT spot OHLCV data
        """
        if self._btc_spot_cache is not None:
            # Filter to requested range
            mask = (self._btc_spot_cache.index >= pd.to_datetime(start_ts, unit='ms')) & \
                   (self._btc_spot_cache.index <= pd.to_datetime(end_ts, unit='ms'))
            return self._btc_spot_cache.loc[mask]
        
        btc_path = os.path.join(self.spot_data_path, 'BTCUSDT', '1m')
        
        if not os.path.exists(btc_path):
            print(f"[DataLoader] WARNING: BTC spot data path not found: {btc_path}")
            return None
        
        df = self._load_zip_data(btc_path, 'BTCUSDT', '1m', start_ts, end_ts)
        
        if df is not None:
            self._btc_spot_cache = df
        
        return df
    
    def _load_zip_data(
        self, 
        base_path: str, 
        symbol: str, 
        timeframe: str,
        start_ts: int, 
        end_ts: int
    ) -> Optional[pd.DataFrame]:
        """
        Load kline data from zip files.
        Handles multiple date range folders (e.g., 2020-2021 and 2021-2024 split).
        
        Args:
            base_path: Path to the timeframe directory
            symbol: Contract symbol
            timeframe: Kline timeframe
            start_ts: Start timestamp in ms
            end_ts: End timestamp in ms
            
        Returns:
            Combined DataFrame with OHLCV data
        """
        try:
            # Check for date range folder structure
            items = os.listdir(base_path)
            date_range_folders = [d for d in items if '_' in d and 
                                  os.path.isdir(os.path.join(base_path, d))]
            
            # Collect all data folders to scan (may be multiple date ranges)
            if date_range_folders:
                # Use ALL date range folders, not just the first one
                data_folders = [os.path.join(base_path, f) for f in sorted(date_range_folders)]
            else:
                data_folders = [base_path]
            
            # Find all zip files from ALL folders
            zip_files = []
            for data_folder in data_folders:
                zip_pattern = os.path.join(data_folder, f"{symbol}-{timeframe}-*.zip")
                folder_zips = glob.glob(zip_pattern)
                
                if not folder_zips:
                    # Try without symbol prefix
                    zip_pattern = os.path.join(data_folder, "*.zip")
                    folder_zips = glob.glob(zip_pattern)
                
                zip_files.extend(folder_zips)
            
            zip_files = sorted(zip_files)
            
            if not zip_files:
                return None
            
            # Filter zip files by date range
            start_date = pd.to_datetime(start_ts, unit='ms').date()
            end_date = pd.to_datetime(end_ts, unit='ms').date()
            
            # Build list of valid zip files to process
            valid_zip_files = []
            for zip_path in zip_files:
                filename = os.path.basename(zip_path)
                try:
                    date_parts = filename.replace('.zip', '').split('-')
                    if len(date_parts) >= 4:
                        file_date = pd.to_datetime('-'.join(date_parts[-3:])).date()
                    else:
                        continue
                    if file_date < start_date or file_date > end_date:
                        continue
                    valid_zip_files.append(zip_path)
                except Exception:
                    continue
            
            if not valid_zip_files:
                return None
            
            # Parallel I/O: Read zip files using multiple processes
            # Use min(8, num_files, cpu_count-1) workers to avoid overhead
            n_workers = min(8, len(valid_zip_files), max(1, multiprocessing.cpu_count() - 1))
            
            dfs = []
            if n_workers > 1 and len(valid_zip_files) > 4:
                # Parallel path for many files
                with ProcessPoolExecutor(max_workers=n_workers) as executor:
                    futures = {executor.submit(_read_zip_file_standalone, zp): zp for zp in valid_zip_files}
                    for future in as_completed(futures):
                        try:
                            df_temp = future.result()
                            if df_temp is not None:
                                dfs.append(df_temp)
                        except Exception:
                            pass
            else:
                # Serial path for few files (avoid process spawn overhead)
                for zip_path in valid_zip_files:
                    df_temp = self._read_zip_file(zip_path)
                    if df_temp is not None:
                        dfs.append(df_temp)
            
            if not dfs:
                return None
            
            # Combine all dataframes
            df = pd.concat(dfs, ignore_index=True)
            
            # Process timestamps
            df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
            
            # Select and clean columns (include quote_volume for liquidity filter)
            cols_to_keep = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if 'quote_volume' in df.columns:
                cols_to_keep.append('quote_volume')
            df = df[cols_to_keep]
            
            # Filter to exact time range
            mask = (df['timestamp'] >= pd.to_datetime(start_ts, unit='ms')) & \
                   (df['timestamp'] <= pd.to_datetime(end_ts, unit='ms'))
            df = df.loc[mask]
            
            # Clean up
            df.drop_duplicates(subset='timestamp', inplace=True)
            df.sort_values('timestamp', inplace=True)
            df.set_index('timestamp', inplace=True)
            # Use float32 instead of float64 to save 50% memory
            df = df.astype('float32')
            
            return df
            
        except Exception as e:
            print(f"[DataLoader] Error loading data for {symbol}: {e}")
            return None
    
    def _read_zip_file(self, zip_path: str) -> Optional[pd.DataFrame]:
        """
        Read CSV data from a zip file.
        First checks if an extracted CSV file exists next to the zip file.
        If CSV exists, loads it directly. Otherwise, extracts from zip and saves CSV.
        Handles both CSV files with and without headers dynamically.
        """
        # Standard column names for Binance kline data
        column_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ]
        
        # Check for cached CSV file (same name as zip but with .csv extension)
        csv_cache_path = zip_path.replace('.zip', '.csv')
        
        try:
            # Fast path: load from cached CSV if exists
            if os.path.exists(csv_cache_path):
                df = pd.read_csv(csv_cache_path)
                # Handle microseconds timestamps (2025+ data)
                if df['open_time'].iloc[0] > 1e15:
                    df['open_time'] = df['open_time'] // 1000
                return df
            
            # Slow path: extract from zip and cache
            with zipfile.ZipFile(zip_path, 'r') as zf:
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    return None
                
                with zf.open(csv_files[0]) as csv_file:
                    # Read first row to detect if it's a header
                    df_probe = pd.read_csv(csv_file, nrows=1, header=None)
                    
                    if df_probe.empty:
                        return None
                    
                    # Check if first row is a header (first value is non-numeric)
                    first_value = df_probe.iloc[0, 0]
                    has_header = False
                    try:
                        int(first_value)
                    except (ValueError, TypeError):
                        has_header = True
                
                # Re-read the file with proper handling
                with zf.open(csv_files[0]) as csv_file:
                    if has_header:
                        # File has header - read it and rename columns
                        df = pd.read_csv(csv_file)
                        # Rename columns to standard names
                        df.columns = column_names[:len(df.columns)]
                    else:
                        # File has no header - assign column names
                        df = pd.read_csv(csv_file, header=None, names=column_names)
                    
                    # Handle microseconds timestamps (2025+ data)
                    if df['open_time'].iloc[0] > 1e15:
                        df['open_time'] = df['open_time'] // 1000
                    
                    # Save to CSV cache for future runs
                    try:
                        df.to_csv(csv_cache_path, index=False)
                    except Exception:
                        pass  # Ignore write errors (permissions, disk space, etc.)
                    
                    return df
                    
        except Exception:
            return None
    
    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical indicators needed for the meme strategy.
        Supports dimension reduction: can resample to higher timeframes (15m, 1h)
        while keeping 1m precision for exits.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        if df is None or df.empty:
            return df
        
        df = df.copy()
        
        # 1. Base 1m indicators (for risk control)
        # ----------------------------------------------------
        # ATR always calculated at 1m level to capture instant volatility for stops
        df['atr_1m'] = df.ta.atr(high=df['high'], low=df['low'], close=df['close'], length=14)
        
        # Get strategy timeframe configuration
        tf_mins = self.config.get('strategy_timeframe_minutes', 1)
        
        # ============================================================
        # Dimension Reduction Logic (15m/1h)
        # ============================================================
        if tf_mins > 1:
            # 1. Resample to target timeframe
            # label='left', closed='left': 10:00 timestamp represents data from 10:00-10:14
            # This is the standard pandas resampling mode
            df_res = df.resample(f'{tf_mins}min', label='left', closed='left').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            })
            
            # 2. Calculate indicators on resampled DF
            # BBands
            bbands = df_res.ta.bbands(close=df_res['close'], length=self.config['bb_length'], std=self.config['bb_std'])
            if bbands is not None:
                upper_col = [c for c in bbands.columns if c.startswith('BBU')][0]
                df_res['strat_bb_upper'] = bbands[upper_col]
            
            # Volume MA
            df_res['strat_volume_ma'] = df_res['volume'].rolling(window=self.config['volume_ma_length']).mean()
            
            # ADX
            adx_res = df_res.ta.adx(high=df_res['high'], low=df_res['low'], close=df_res['close'], length=self.config.get('adx_length', 14))
            if adx_res is not None:
                adx_col = [c for c in adx_res.columns if c.startswith('ADX_')][0]
                df_res['strat_adx'] = adx_res[adx_col]

            # ATR (critical: risk management indicator)
            df_res['strat_atr'] = df_res.ta.atr(high=df_res['high'], low=df_res['low'], close=df_res['close'], length=self.config.get('atr_length', 14))
            
            # EMA 60 (trend filter)
            df_res['strat_ema_60'] = df_res['close'].ewm(span=self.config.get('ema_deviation_length', 60), adjust=False).mean()
            
            # ROC 1h (momentum) - adjust period based on timeframe
            # If we want 60 minutes of change: 15m * 4 = 60m
            roc_period = int(60 / tf_mins)
            df_res['strat_roc_1h'] = df_res['close'].pct_change(periods=roc_period)
            
            # Save original OHLCV for strategy logic
            df_res['strat_open'] = df_res['open']
            df_res['strat_high'] = df_res['high']
            df_res['strat_close'] = df_res['close']
            df_res['strat_volume'] = df_res['volume']

            # 3. SAFE MAPPING with shift(1) to prevent look-ahead bias
            # Key fix: Shift the 10:00 calculation result to 10:15 timestamp
            # When Engine runs at 10:15, it reads the "just completed 10:00-10:14 candle" data
            # All strat_ indicators must use shift(1) to avoid peeking at the forming candle
            cols_to_map = ['strat_bb_upper', 'strat_volume_ma', 'strat_adx', 'strat_ema_60', 'strat_roc_1h', 'strat_open', 'strat_high', 'strat_close', 'strat_volume']
            
            # Shift 1 period (15m) and reindex back to 1m timeline (ffill)
            # Every minute from 10:15..10:29 will read 10:00 bin's data (Safe)
            mapped = df_res[cols_to_map].shift(1).reindex(df.index, method='ffill')
            
            for col in cols_to_map:
                df[col] = mapped[col]

            # [B] Safe columns for risk management - 1m ATR for most sensitive stops
            # Use 1m ATR regardless of strategy timeframe for tight risk control
            df['atr'] = df['atr_1m']
            
        else:
            # ============================================================
            # Original 1m logic (for rollback)
            # ============================================================
            bbands = df.ta.bbands(close=df['close'], length=self.config['bb_length'], std=self.config['bb_std'])
            if bbands is not None:
                upper_col = [c for c in bbands.columns if c.startswith('BBU')][0]
                df['strat_bb_upper'] = bbands[upper_col]
            
            df['strat_volume_ma'] = df['volume'].rolling(window=self.config['volume_ma_length']).mean()
            
            adx_res = df.ta.adx(high=df['high'], low=df['low'], close=df['close'], length=self.config.get('adx_length', 14))
            if adx_res is not None:
                adx_col = [c for c in adx_res.columns if c.startswith('ADX_')][0]
                df['strat_adx'] = adx_res[adx_col]
            
            df['strat_ema_60'] = df['close'].ewm(span=self.config.get('ema_deviation_length', 60), adjust=False).mean()
            df['strat_roc_1h'] = df['close'].pct_change(periods=60)
            df['strat_open'] = df['open']
            df['strat_high'] = df['high']
            df['strat_close'] = df['close']
            df['strat_volume'] = df['volume']
            
            # Use 1m ATR for risk control
            df['atr'] = df['atr_1m']

        # Common indicators (1m level, always needed)
        # 24h change (for coin selection)
        df['roc_24h'] = df['close'].pct_change(periods=1440)
        if 'quote_volume' not in df.columns:
            df['quote_volume'] = df['close'] * df['volume']
        df['roll_qvol_24h'] = df['quote_volume'].rolling(window=1440, min_periods=1).sum()
        df['ema_24h'] = df['close'].ewm(span=1440, adjust=False).mean()
        
        # ============================================================
        # [SHORT Strategy Indicators] Post-Hype Butcher
        # ============================================================
        # EMA 20 (short-term support line)
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # VWAP (Volume Weighted Average Price) - institutional cost basis
        # Approximation using cumulative values
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        
        # RSI (for overbought detection)
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        return df
    
    def calculate_hourly_change(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """Calculate the 1-hour price change for a symbol."""
        if df is None or df.empty:
            return 0.0
        
        try:
            if 'roc_1h' in df.columns:
                idx = df.index.searchsorted(current_time, side='right') - 1
                if idx < 0 or idx >= len(df):
                    return 0.0
                val = df['roc_1h'].iloc[idx]
                return float(val) if not pd.isna(val) else 0.0
            return 0.0
        except Exception:
            return 0.0
    
    def calculate_24h_change(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """Calculate the 24-hour price change for a symbol."""
        if df is None or df.empty:
            return 0.0
        
        try:
            if 'roc_24h' in df.columns:
                idx = df.index.searchsorted(current_time, side='right') - 1
                if idx < 0 or idx >= len(df):
                    return 0.0
                val = df['roc_24h'].iloc[idx]
                return float(val) if not pd.isna(val) else 0.0
            return 0.0
        except Exception:
            return 0.0
    
    def calculate_24h_quote_volume(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """Calculate the 24-hour quote volume (turnover in USDT) for a symbol."""
        if df is None or df.empty:
            return 0.0
        
        try:
            if 'roll_qvol_24h' in df.columns:
                idx = df.index.searchsorted(current_time, side='right') - 1
                if idx < 0 or idx >= len(df):
                    return 0.0
                val = df['roll_qvol_24h'].iloc[idx]
                return float(val) if not pd.isna(val) else 0.0
            return 0.0
        except Exception:
            return 0.0
    
    def clear_all_cache(self):
        """
        Nuclear option: Clear ALL cached DataFrames.
        Called by Engine when memory exceeds threshold.
        """
        cache_size = len(self._data_cache)
        self._data_cache.clear()
        self._btc_spot_cache = None
        print(f"[DataLoader] Nuked {cache_size} cached DataFrames.")
    
    def keep_only(self, active_symbols: set):
        """
        [Survivor Strategy] Keep only active symbols, prune the rest.
        Avoids cache stampede by preserving hot data.
        """
        cached_symbols = list(self._data_cache.keys())
        deleted_count = 0
        
        for symbol in cached_symbols:
            if symbol not in active_symbols:
                del self._data_cache[symbol]
                deleted_count += 1
        
        if deleted_count > 0:
            print(f"[DataLoader] Pruned {deleted_count} inactive. Kept {len(self._data_cache)} active.")


# Alias for backward compatibility
MemeDataHandler = BacktestDataLoader
