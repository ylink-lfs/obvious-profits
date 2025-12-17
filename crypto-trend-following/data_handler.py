# data_handler.py
# Meme Coin Strategy Data Handler
# Handles loading and preparing kline data from zip files for futures and spot markets

import pandas as pd
import pandas_ta  # noqa: F401 - used via df.ta accessor
import os
import zipfile
import glob
from typing import Dict, Optional


class MemeDataHandler:
    """
    Data handler for meme coin momentum strategy.
    Supports loading data from zip files for multiple contracts.
    """
    
    def __init__(self, config):
        print("[DataHandler] Initializing MemeDataHandler...")
        self.config = config
        self.futures_data_path = config['futures_data_path']
        self.spot_data_path = config['spot_data_path']
        
        # Cache for loaded data
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
        cache_key = f"{symbol}_{timeframe}_{start_ts}_{end_ts}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]
        
        # Construct path to contract data
        contract_path = os.path.join(self.futures_data_path, symbol, timeframe)
        
        if not os.path.exists(contract_path):
            return None
        
        df = self._load_zip_data(contract_path, symbol, timeframe, start_ts, end_ts)
        
        if df is not None and not df.empty:
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
            print(f"[DataHandler] WARNING: BTC spot data path not found: {btc_path}")
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
            
            if date_range_folders:
                # Use date range folder
                data_folder = os.path.join(base_path, sorted(date_range_folders)[0])
            else:
                data_folder = base_path
            
            # Find all zip files
            zip_pattern = os.path.join(data_folder, f"{symbol}-{timeframe}-*.zip")
            zip_files = sorted(glob.glob(zip_pattern))
            
            if not zip_files:
                # Try without symbol prefix
                zip_pattern = os.path.join(data_folder, "*.zip")
                zip_files = sorted(glob.glob(zip_pattern))
            
            if not zip_files:
                return None
            
            # Filter zip files by date range
            start_date = pd.to_datetime(start_ts, unit='ms').date()
            end_date = pd.to_datetime(end_ts, unit='ms').date()
            
            dfs = []
            for zip_path in zip_files:
                # Extract date from filename
                filename = os.path.basename(zip_path)
                try:
                    # Parse date from filename like "BTCUSDT-1m-2024-01-01.zip"
                    date_parts = filename.replace('.zip', '').split('-')
                    if len(date_parts) >= 4:
                        file_date = pd.to_datetime('-'.join(date_parts[-3:])).date()
                    else:
                        continue
                    
                    # Skip if outside date range
                    if file_date < start_date or file_date > end_date:
                        continue
                    
                    # Load data from zip
                    df_temp = self._read_zip_file(zip_path)
                    if df_temp is not None:
                        dfs.append(df_temp)
                        
                except Exception as e:
                    continue
            
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
            print(f"[DataHandler] Error loading data for {symbol}: {e}")
            return None
    
    def _read_zip_file(self, zip_path: str) -> Optional[pd.DataFrame]:
        """
        Read CSV data from a zip file.
        Handles both CSV files with and without headers dynamically.
        """
        # Standard column names for Binance kline data
        column_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ]
        
        try:
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
                    
                    return df
                    
        except Exception as e:
            return None
    
    def prepare_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical indicators needed for the meme strategy.
        Also pre-calculates rolling metrics for vectorized performance.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        if df is None or df.empty:
            return df
        
        df = df.copy()
        
        # Bollinger Bands for volatility breakout
        bb_length = self.config['bb_length']
        bb_std = self.config['bb_std']
        
        bbands = df.ta.bbands(
            close=df['close'],
            length=bb_length,
            std=bb_std
        )
        
        if bbands is not None:
            # Find the upper band column
            upper_col = [c for c in bbands.columns if c.startswith('BBU')][0]
            df['bb_upper'] = bbands[upper_col]
        
        # Volume MA for confirmation
        vol_ma_length = self.config['volume_ma_length']
        df['volume_ma'] = df['volume'].rolling(window=vol_ma_length).mean()
        
        # --- Pre-calculated rolling indicators (Vectorization for performance) ---
        # For 1m timeframe: 24h = 1440 bars, 1h = 60 bars
        
        # 1. Pre-calculate 24h price change (ROC)
        # pct_change with periods=1440 gives instant 24h change
        df['roc_24h'] = df['close'].pct_change(periods=1440)
        
        # 2. Pre-calculate 24h quote volume (rolling sum)
        if 'quote_volume' not in df.columns:
            # Estimate quote volume as close * volume
            df['quote_volume'] = df['close'] * df['volume']
        df['roll_qvol_24h'] = df['quote_volume'].rolling(window=1440, min_periods=1).sum()
        
        # 3. Pre-calculate 1h price change (for BTC circuit breaker and RS check)
        df['roc_1h'] = df['close'].pct_change(periods=60)
        
        return df
    
    def calculate_hourly_change(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """
        Calculate the 1-hour price change for a symbol.
        Uses pre-calculated roc_1h column with O(log N) index lookup.
        
        Args:
            df: DataFrame with 1m OHLCV data
            current_time: Current timestamp
            
        Returns:
            1-hour percentage change (e.g., 0.05 for 5%)
        """
        if df is None or df.empty:
            return 0.0
        
        try:
            # Fast path: use pre-calculated roc_1h if available
            if 'roc_1h' in df.columns:
                # O(log N) index lookup using searchsorted
                idx = df.index.searchsorted(current_time, side='right') - 1
                if idx < 0 or idx >= len(df):
                    return 0.0
                val = df['roc_1h'].iloc[idx]
                return float(val) if not pd.isna(val) else 0.0
            
            # Fallback: calculate on-the-fly (slower)
            one_hour_ago = current_time - pd.Timedelta(hours=1)
            
            # Use searchsorted for O(log N) lookup
            idx_1h = df.index.searchsorted(one_hour_ago, side='right') - 1
            idx_now = df.index.searchsorted(current_time, side='right') - 1
            
            if idx_1h < 0 or idx_now < 0:
                return 0.0
            
            price_1h_ago = df['close'].iloc[idx_1h]
            current_price = df['close'].iloc[idx_now]
            
            return (current_price - price_1h_ago) / price_1h_ago
            
        except Exception:
            return 0.0
    
    def calculate_24h_change(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """
        Calculate the 24-hour price change for a symbol.
        Uses pre-calculated roc_24h column with O(log N) index lookup.
        
        Args:
            df: DataFrame with 1m OHLCV data
            current_time: Current timestamp
            
        Returns:
            24-hour percentage change
        """
        if df is None or df.empty:
            return 0.0
        
        try:
            # Fast path: use pre-calculated roc_24h if available
            if 'roc_24h' in df.columns:
                # O(log N) index lookup using searchsorted
                idx = df.index.searchsorted(current_time, side='right') - 1
                if idx < 0 or idx >= len(df):
                    return 0.0
                val = df['roc_24h'].iloc[idx]
                return float(val) if not pd.isna(val) else 0.0
            
            # Fallback: calculate on-the-fly (slower)
            one_day_ago = current_time - pd.Timedelta(hours=24)
            
            # Use searchsorted for O(log N) lookup
            idx_24h = df.index.searchsorted(one_day_ago, side='right') - 1
            idx_now = df.index.searchsorted(current_time, side='right') - 1
            
            if idx_24h < 0 or idx_now < 0:
                return 0.0
            
            price_24h_ago = df['close'].iloc[idx_24h]
            current_price = df['close'].iloc[idx_now]
            
            return (current_price - price_24h_ago) / price_24h_ago
            
        except Exception:
            return 0.0
    
    def calculate_24h_quote_volume(self, df: pd.DataFrame, current_time: pd.Timestamp) -> float:
        """
        Calculate the 24-hour quote volume (turnover in USDT) for a symbol.
        Uses pre-calculated roll_qvol_24h column with O(log N) index lookup.
        
        Args:
            df: DataFrame with 1m OHLCV data (must include quote_volume column)
            current_time: Current timestamp
            
        Returns:
            24-hour quote volume in USDT
        """
        if df is None or df.empty:
            return 0.0
        
        try:
            # Fast path: use pre-calculated roll_qvol_24h if available
            if 'roll_qvol_24h' in df.columns:
                # O(log N) index lookup using searchsorted
                idx = df.index.searchsorted(current_time, side='right') - 1
                if idx < 0 or idx >= len(df):
                    return 0.0
                val = df['roll_qvol_24h'].iloc[idx]
                return float(val) if not pd.isna(val) else 0.0
            
            # Fallback: calculate on-the-fly (slower)
            one_day_ago = current_time - pd.Timedelta(hours=24)
            
            # Use searchsorted for O(log N) range bounds
            idx_start = df.index.searchsorted(one_day_ago, side='right')
            idx_end = df.index.searchsorted(current_time, side='right')
            
            if idx_start >= idx_end:
                return 0.0
            
            if 'quote_volume' in df.columns:
                return float(df['quote_volume'].iloc[idx_start:idx_end].sum())
            else:
                # Estimate quote volume as close * volume
                data_slice = df.iloc[idx_start:idx_end]
                return float((data_slice['close'] * data_slice['volume']).sum())
            
        except Exception:
            return 0.0
    
    def get_lowest_low(self, df: pd.DataFrame, current_time: pd.Timestamp, lookback: int, exclude_last: int = 1) -> float:
        """
        Get the lowest low of the last N candles (excluding the most recent candles).
        
        For structural exit, we compare prev_bar's close against lowest_low of 
        the 20 candles BEFORE prev_bar, so we need to exclude the last candle 
        from the lookback window.
        
        Args:
            df: DataFrame with OHLCV data
            current_time: Current timestamp
            lookback: Number of candles to look back
            exclude_last: Number of most recent candles to exclude (default 1)
            
        Returns:
            Lowest low price
        """
        if df is None or df.empty:
            return 0.0
        
        try:
            # Use searchsorted for O(log N) index lookup
            idx = df.index.searchsorted(current_time, side='left')
            
            # Calculate the range: [idx - exclude_last - lookback, idx - exclude_last)
            end_idx = idx - exclude_last
            start_idx = end_idx - lookback
            
            if end_idx <= 0 or start_idx < 0:
                # Not enough data
                start_idx = max(0, start_idx)
            
            if start_idx >= end_idx:
                return 0.0
            
            # Get the lowest low in the range
            return float(df['low'].iloc[start_idx:end_idx].min())
            
        except Exception:
            return 0.0
    
    def clear_cache(self):
        """Clear all cached data."""
        self._data_cache.clear()
        self._btc_spot_cache = None