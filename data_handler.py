# data_handler.py
# [MODIFIED] Calculates KC Upper & Lower bands, and a Short exit signal.

import pandas as pd
import pandas_ta as ta
import os
import numpy as np
import glob

class DataHandler:
    """
    Handles loading, processing, and merging all MTF data from CSV files.
    """
    def __init__(self, config):
        print("[DataHandler] Initializing...")
        self.config = config
        # [MODIFIED] Use a clearer path definition
        self.base_data_dir = os.path.join(os.path.dirname(__file__), 'data', 'binance_public_kline')

    def _load_csv_data(self, timeframe, from_datetime_str):
        """
        Load kline data from CSV files for the specified timeframe.
        (This function is unchanged from your provided code)
        """
        print(f"[DataHandler] Loading {self.config['symbol']} {timeframe} data from {from_datetime_str}...")
        
        # Convert symbol format: 'BTC/USDT' -> 'BTCUSDT'
        symbol = self.config['symbol'].replace('/', '')
        
        # Build path to CSV files
        csv_dir = os.path.join(self.base_data_dir, symbol, timeframe)
        
        if not os.path.exists(csv_dir):
            raise FileNotFoundError(f"Data directory not found: {csv_dir}")
        
        # Get all CSV files in the directory
        csv_files = sorted(glob.glob(os.path.join(csv_dir, f"{symbol}-{timeframe}-*.csv")))
        
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in: {csv_dir}")
        
        print(f"[DataHandler] Found {len(csv_files)} CSV files")
        
        # Read and concatenate all CSV files
        dfs = []
        for csv_file in csv_files:
            try:
                df_temp = pd.read_csv(csv_file, header=None, names=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                
                # Extract date from filename (format: SYMBOL-TIMEFRAME-YYYY-MM.csv)
                filename = os.path.basename(csv_file)
                parts = filename.split('-')
                if len(parts) >= 4:
                    year = int(parts[2])
                    # The timestamp for SPOT Data from January 1st 2025 onwards will be in microseconds.
                    if year >= 2025:
                        df_temp['open_time'] = df_temp['open_time'] / 1000
                
                dfs.append(df_temp)
            except Exception as e:
                print(f"[DataHandler] Error reading {csv_file}: {e}")
                continue
        
        if not dfs:
            raise ValueError(f"Failed to load any data from {csv_dir}")
        
        # Concatenate all dataframes
        df = pd.concat(dfs, ignore_index=True)

            # Convert open_time from milliseconds to datetime
        df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
        # Select only required columns: timestamp, open, high, low, close, volume
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        # Filter data from start_date onwards
        from_datetime = pd.to_datetime(from_datetime_str)
        df = df[df['timestamp'] >= from_datetime]
        
        # Remove duplicates and sort by timestamp
        df.drop_duplicates(subset='timestamp', inplace=True)
        df.sort_values('timestamp', inplace=True)
        
        # Set timestamp as index
        df.set_index('timestamp', inplace=True)
        
        # Convert to float
        df = df.astype(float)
        
        print(f"[DataHandler] Loaded {len(df)} bars for {timeframe}.")
        return df

    def prepare_master_dataframe(self):
        """
        Prepares the final merged MTF DataFrame for the backtester.
        """
        # 1. Load both timeframes from CSV files
        df_entry = self._load_csv_data(
            self.config['entry_timeframe'], 
            self.config['start_date']
        )
        df_filter = self._load_csv_data(
            self.config['filter_timeframe'], 
            self.config['start_date']
        )
        
        # 2. Calculate Filter (Daily) Indicators
        print("[DataHandler] Calculating Filter (Daily) indicators...")
        
        # Daily MA
        ma_col = f"MA_{self.config['filter_ma_period']}"
        df_filter[ma_col] = df_filter.ta.ema(length=self.config['filter_ma_period'])
        
        # Daily Trend State (Long_Trend / Short_Trend)
        df_filter['MA_TREND_DAILY'] = np.where(
            df_filter['close'] > df_filter[ma_col], 
            'Long', 
            'Short'
        )
        
        # Daily Exit Signal (for LONGS)
        df_filter['DAILY_EXIT_SIGNAL'] = (
            (df_filter['close'].shift(1) < df_filter[ma_col].shift(1)) &
            (df_filter['close'].shift(2) < df_filter[ma_col].shift(2))
        )
        
        # [NEW] Daily Cover Signal (for SHORTS)
        df_filter['DAILY_COVER_SIGNAL'] = (
            (df_filter['close'].shift(1) > df_filter[ma_col].shift(1)) &
            (df_filter['close'].shift(2) > df_filter[ma_col].shift(2))
        )

        # [REMOVED] Daily ADX logic
        
        # 3. Resample Daily data to Entry timeframe
        print(f"[DataHandler] Resampling Daily data to {self.config['entry_timeframe']}...")
        
        # [MODIFIED] Add the new daily_cover_signal to the list
        filter_cols_to_resample = ['MA_TREND_DAILY', 'DAILY_EXIT_SIGNAL', 'DAILY_COVER_SIGNAL']
        
        df_filter_resampled = df_filter[filter_cols_to_resample].resample(self.config['pandas_entry_freq']).ffill()
        
        # 4. Calculate Entry (1H) Indicators
        print(f"[DataHandler] Calculating Entry ({self.config['entry_timeframe']}) indicators...")
        
        # 4a. 1H Average Volume
        vol_avg_col = f"VOL_AVG_{self.config['vol_avg_period']}"
        df_entry[vol_avg_col] = df_entry.ta.ema(length=self.config['vol_avg_period'], source='volume')

        # 4b. Indicator for RSI (harmless to calculate)
        rsi_col_name = self.config['rsi_col_name']
        df_entry[rsi_col_name] = df_entry.ta.rsi(length=self.config['rsi_length'])

        # 4c. Indicator for ATR (harmless to calculate)
        atr_col_name = self.config['atr_col_name']
        df_entry[atr_col_name] = df_entry.ta.atr(
            length=self.config['atr_length'], 
            high=df_entry['high'], 
            low=df_entry['low'], 
            close=df_entry['close']
        )
        
        # 4d. [MODIFIED] Indicator for Keltner Channel Filter
        try:
            print("[DataHandler] Calculating Keltner Channels...")
            kc_df = df_entry.ta.kc(
                length=self.config['kc_length'], 
                scalar=self.config['kc_multiplier'],
                mamode="EMA", 
                append=True
            )
            
            # Find and rename Upper Band
            kc_upper_col_dynamic = next((col for col in kc_df.columns if col.startswith('KCU')), None)
            static_kc_upper = self.config['kc_upper_col_name']
            if kc_upper_col_dynamic:
                print(f"[DataHandler] Detected KC Upper Band: {kc_upper_col_dynamic}. Renaming to: {static_kc_upper}")
                df_entry.rename(columns={kc_upper_col_dynamic: static_kc_upper}, inplace=True)
            else:
                print("[DataHandler] WARNING: Could not find Keltner Channel Upper Band column.")

            # [NEW] Find and rename Lower Band
            kc_lower_col_dynamic = next((col for col in kc_df.columns if col.startswith('KCL')), None)
            static_kc_lower = self.config['kc_lower_col_name']
            if kc_lower_col_dynamic:
                print(f"[DataHandler] Detected KC Lower Band: {kc_lower_col_dynamic}. Renaming to: {static_kc_lower}")
                df_entry.rename(columns={kc_lower_col_dynamic: static_kc_lower}, inplace=True)
            else:
                print("[DataHandler] WARNING: Could not find Keltner Channel Lower Band column.")

        except KeyError as e:
            print(f"[DataHandler] WARNING: Missing Keltner Channel config: {e}. Skipping KC calculation.")
        except Exception as e:
            print(f"[DataHandler] WARNING: Failed to calculate Keltner Channels: {e}")

        # 5. Merge DataFrames
        print("[DataHandler] Merging dataframes...")
        df_master = df_entry.join(df_filter_resampled)
        
        # 6. Clean and finalize
        df_master.dropna(inplace=True)
        
        print(f"[DataHandler] Master DataFrame prepared. Total valid bars: {len(df_master)}")
        return df_master