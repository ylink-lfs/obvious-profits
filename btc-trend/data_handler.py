# data_handler.py
# [MODIFIED] Explicitly passes columns to ATR/ADX/BBands to fix calculation errors.

import pandas as pd
import pandas_ta as ta
import os
import numpy as np
import glob

class DataHandler:
    def __init__(self, config):
        print("[DataHandler] Initializing...")
        self.config = config
        self.base_data_dir = os.path.join(os.path.dirname(__file__), 'data', 'binance_public_kline')

    def _load_csv_data(self, timeframe, start_ts, end_ts=None):
        """
        Load kline data from CSV files.
        """
        start_date_str = pd.to_datetime(start_ts, unit='ms')
        end_date_str = pd.to_datetime(end_ts, unit='ms') if end_ts else "Now"
        print(f"[DataHandler] Loading {self.config['symbol']} {timeframe} data ({start_date_str} to {end_date_str})...")
        
        symbol = self.config['symbol'].replace('/', '')
        csv_dir = os.path.join(self.base_data_dir, symbol, timeframe)
        
        if not os.path.exists(csv_dir):
            raise FileNotFoundError(f"Data directory not found: {csv_dir}")
        
        csv_files = sorted(glob.glob(os.path.join(csv_dir, f"{symbol}-{timeframe}-*.csv")))
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in: {csv_dir}")
        
        dfs = []
        for csv_file in csv_files:
            try:
                df_temp = pd.read_csv(csv_file, header=None, names=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                filename = os.path.basename(csv_file)
                parts = filename.split('-')
                # Handle 2025+ timestamps (us to ms)
                if len(parts) >= 4 and int(parts[2]) >= 2025:
                    df_temp['open_time'] = df_temp['open_time'] / 1000
                dfs.append(df_temp)
            except Exception:
                continue
        
        df = pd.concat(dfs, ignore_index=True)
        df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
        
        # Ensure columns are strictly lowercase and float
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        target_start_dt = pd.to_datetime(start_ts, unit='ms')
        mask = (df['timestamp'] >= target_start_dt)
        if end_ts:
            mask = mask & (df['timestamp'] <= pd.to_datetime(end_ts, unit='ms'))
        df = df.loc[mask]
        
        df.drop_duplicates(subset='timestamp', inplace=True)
        df.sort_values('timestamp', inplace=True)
        df.set_index('timestamp', inplace=True)
        df = df.astype(float)
        
        if df.empty: raise ValueError("No data found")
        print(f"[DataHandler] Loaded {len(df)} bars.")
        return df

    def _robust_rename(self, df, dynamic_prefix, static_name):
        """ Helper to find and rename columns like BBL_20_2.0 -> BB_LOWER_STATIC """
        dynamic_col = next((col for col in df.columns if col.startswith(dynamic_prefix)), None)
        if dynamic_col:
            print(f"[DataHandler] Renaming {dynamic_col} -> {static_name}")
            df.rename(columns={dynamic_col: static_name}, inplace=True)
        else:
            print(f"[DataHandler] WARNING: Could not find column starting with '{dynamic_prefix}'")

    def prepare_data(self, start_ts, end_ts=None):
        timeframe = self.config['timeframe']
        df = self._load_csv_data(timeframe, start_ts, end_ts)
        
        print("[DataHandler] Calculating Indicators...")
        
        # 1. ADX (For Filter)
        # [FIX] Explicitly pass High, Low, Close
        df.ta.adx(
            high=df['high'], 
            low=df['low'], 
            close=df['close'], 
            length=self.config['adx_length'], 
            append=True
        )
        
        # 2. Bollinger Bands (For Strategy)
        # [FIX] Explicitly pass Close
        df.ta.bbands(
            close=df['close'],
            length=self.config['bb_length'], 
            std=self.config['bb_std'], 
            append=True
        )
        self._robust_rename(df, 'BBL', self.config['bb_lower_col'])
        self._robust_rename(df, 'BBM', self.config['bb_middle_col'])
        
        # 3. ATR (For Stop Loss) - [CRITICAL FIX]
        # [FIX] Explicitly pass High, Low, Close. This fixes the "Invalid risk" error.
        df[self.config['atr_col_name']] = df.ta.atr(
            high=df['high'], 
            low=df['low'], 
            close=df['close'],
            length=self.config['atr_length']
        )
        
        # Debug: Check if ATR is 0 or NaN
        if (df[self.config['atr_col_name']] <= 0).any():
            print("[DataHandler] WARNING: Found 0 or negative ATR values! Check data quality.")

        df.dropna(inplace=True)
        return df