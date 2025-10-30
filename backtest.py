import ccxt
import pandas as pd
import pandas_ta as ta # Import pandas-ta library
import os
import traceback
import numpy as np
import time
import hashlib

from dotenv import load_dotenv


def fetch_historical_data(symbol, timeframe, from_datetime=None, limit=None, use_cache=True):
    """
    Fetch historical K-line data from Binance and convert to Pandas DataFrame
    
    Parameters:
    symbol (str): Trading pair, e.g. 'BTC/USDT'
    timeframe (str): Time frame, e.g. '1m', '1h', '1d'
    from_datetime (str): Start time, format like '2024-01-01 00:00:00', if None then use limit parameter
    limit (int): If from_datetime is None, fetch the latest limit K-lines
    use_cache (bool): Whether to use cache, default True
    """
    
    # --- 0. Cache handling ---
    if use_cache:
        # Create cache directory
        cache_dir = ".cache"
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        
        # Generate cache filename (based on parameter hash)
        cache_params = f"{symbol}_{timeframe}_{from_datetime}_{limit}"
        cache_hash = hashlib.md5(cache_params.encode()).hexdigest()
        cache_file = os.path.join(cache_dir, f"data_{cache_hash}.csv")
        
        # Check if cache file exists
        if os.path.exists(cache_file):
            try:
                print(f"[Cache] Loading data from cache: {cache_file}")
                df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
                print(f"[Cache] Successfully loaded {len(df)} K-line data from cache.")
                print(f"[Cache] Data time range: {df.index[0]} to {df.index[-1]}")
                return df
            except Exception as e:
                print(f"[Cache] Cache file corrupted, will re-download data: {e}")
    
    # --- 1. Initialize CCXT exchange ---
    load_dotenv() # Load .env variables
    apiKey = os.environ.get('BINANCE_API_KEY')
    secret = os.environ.get('BINANCE_SECRET_KEY')
    
    exchange = ccxt.binance({
        'enableRateLimit': True, # Auto handle rate limiting
        'apiKey': apiKey,
        'secret': secret
    })
    
    # (Optional) If operating on testnet, need to set this
    exchange.set_sandbox_mode(True) 
    
    # Time interval constants (milliseconds)
    timeframe_to_ms = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '30m': 30 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000
    }
    
    if from_datetime:
        # Paged fetch mode: from specified time to now
        print(f"[Fetch] Fetching {symbol} {timeframe} data in pages, from {from_datetime} to now...")
        
        from_timestamp = exchange.parse8601(from_datetime)
        now = exchange.milliseconds()
        all_ohlcv = []
        
        while from_timestamp < now:
            print(f'[Fetch] Pulling ohlcv beginning at: {exchange.iso8601(from_timestamp)}')
            
            try:
                ohlcvs = exchange.fetch_ohlcv(symbol, timeframe, from_timestamp)
                
                if not ohlcvs:
                    break
                    
                # Filter out duplicate data (Binance sometimes returns the last bar)
                if all_ohlcv and ohlcvs[0][0] == all_ohlcv[-1][0]:
                    ohlcvs = ohlcvs[1:]
                    
                if not ohlcvs:
                    break

                all_ohlcv.extend(ohlcvs)
                
                # Update next request start time
                from_timestamp = ohlcvs[-1][0] + timeframe_to_ms.get(timeframe, 60 * 1000)
                
                # Avoid triggering rate limits
                if exchange.rateLimit:
                    time.sleep(exchange.rateLimit / 1000)
                    
            except Exception as e:
                print(f"[Fetch] Error occurred while fetching data: {e}")
                break
        
        ohlcv = all_ohlcv
        
    else:
        # Traditional mode: fetch the latest limit K-lines
        if limit is None:
            limit = 1000
        print(f"[Fetch] Fetching {symbol} {timeframe} data, latest {limit} K-lines...")
        
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            print(f"[Fetch] Error occurred while fetching data: {e}")
            return None
    
    if not ohlcv:
        print("[Fetch] No data fetched.")
        return None

    try:
        # --- Convert to Pandas DataFrame ---
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Convert timestamp to readable datetime format
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Remove potential duplicates
        df.drop_duplicates(subset='timestamp', inplace=True)

        # Set timestamp as index (this is standard practice for time series analysis)
        df.set_index('timestamp', inplace=True)
        
        # Convert data types to float, as TA calculations require it
        df = df.astype(float)
        
        print(f"[Fetch] Successfully fetched {len(df)} K-line data.")
        print(f"[Fetch] Data time range: {df.index[0]} to {df.index[-1]}")
        
        # --- Save to cache ---
        if use_cache:
            try:
                df.to_csv(cache_file)
                print(f"[Cache] Data saved to cache: {cache_file}")
            except Exception as e:
                print(f"[Cache] Error occurred while saving cache: {e}")
        
        return df

    except Exception as e:
        print(f"Unknown error occurred: {traceback.format_exc()}")
    
    return None

# --- [Function 2: calculate_signals (Unchanged from previous)] ---
def calculate_signals(df, rsi_length=14, rsi_col_name='RSI_14', ema_short_len=10, ema_long_len=30):
    """
    Calculates indicators for both Long (EMA) and Short (RSI) strategies.
    The trend indicator is assumed to be already present.
    """
    if df is None: return None
    print(f"[Signal] Calculating indicators (RSI {rsi_length}, EMA {ema_short_len}/{ema_long_len})...")
    
    # 1. Calculate RSI indicator (for Short strategy)
    df[rsi_col_name] = df.ta.rsi(length=rsi_length)
    
    # 2. Calculate EMA indicators (for Long strategy)
    ema_short_col = f'EMA_{ema_short_len}'
    ema_long_col = f'EMA_{ema_long_len}'
    df[ema_short_col] = df.ta.ema(length=ema_short_len)
    df[ema_long_col] = df.ta.ema(length=ema_long_len)
    
    # 3. Pre-calculate Long entry signal (Golden Cross)
    df['buy_signal'] = (df[ema_short_col] > df[ema_long_col]) & (df[ema_short_col].shift(1) <= df[ema_long_col].shift(1))
    
    # 4. Drop rows with initial NaN values
    #    (This will drop NaNs from RSI, EMAs, and the merged TREND_EMA)
    df.dropna(inplace=True) 
    
    print(f"[Signal] Signal calculation complete (valid bars: {len(df)}).")
    return df

# --- [MODIFIED] Function 3: run_event_driven_backtest ---
def run_event_driven_backtest(
    df, 
    stop_loss_pct=0.01,
    take_profit_pct=0.02,
    transaction_fee_pct=0.001, 
    trend_column_name='TREND_EMA_1H',
    rsi_column_name='RSI_14',
    rsi_sell_threshold=70
):
    """
    Executes the event-driven backtest
    *** [MODIFIED] SHORT-ONLY STRATEGY TEST ***
    """
    print(f"\n--- [Backtest] Starting Event-Driven Backtest (SL: {stop_loss_pct*100}%, TP: {take_profit_pct*100}%) ---")
    print(f"*** [Backtest] STRATEGY-LONG: DISABLED FOR THIS TEST ***")
    print(f"*** [Backtest] STRATEGY-SHORT: RSI > {rsi_sell_threshold}")
    print(f"*** [Backtest] TREND FILTER: {trend_column_name} Active")
    print(f"*** [Backtest] EXIT LOGIC: SL/TP only. ***")
    
    # --- [CHANGED] Use position_state: 0 = Flat, 1 = Long, -1 = Short
    position_state = 0 
    entry_price = 0
    stop_loss_price = 0
    take_profit_price = 0
    trades_log = []
    balance = 10000
    balance_history = []
    
    # Check if the required columns exist
    # We still check for 'buy_signal' to ensure the data is complete, even if unused
    required_cols = [trend_column_name, rsi_column_name, 'buy_signal']
    if not all(col in df.columns for col in required_cols):
        print(f"[Backtest] ERROR: DataFrame is missing one or more required columns: {required_cols}")
        missing_cols = [col for col in required_cols if col not in df.columns]
        print(f"[Backtest] Missing: {missing_cols}")
        return [], pd.DataFrame()

    for bar in df.itertuples():
        
        # Get the indicator values for this bar
        current_rsi = getattr(bar, rsi_column_name)
        trend_value = getattr(bar, trend_column_name)
        
        # 1. Check exit conditions IF IN A POSITION
        if position_state != 0:
            
            # --- Check LONG position exits (This part will not be triggered) ---
            if position_state == 1:
                # 1a. Check StopLoss (triggered by bar.low)
                if bar.low <= stop_loss_price:
                    exit_price = stop_loss_price
                    profit_pct = (exit_price / entry_price) - 1 - (transaction_fee_pct * 2) 
                    trades_log.append({'entry_price': entry_price, 'exit_price': exit_price, 'profit_pct': profit_pct, 'exit_reason': 'StopLoss', 'type': 'Long'})
                    balance *= (1 + profit_pct)
                    position_state = 0 # Exit position
                # 1b. Check TakeProfit (triggered by bar.high)
                elif bar.high >= take_profit_price:
                    exit_price = take_profit_price
                    profit_pct = (exit_price / entry_price) - 1 - (transaction_fee_pct * 2)
                    trades_log.append({'entry_price': entry_price, 'exit_price': exit_price, 'profit_pct': profit_pct, 'exit_reason': 'TakeProfit', 'type': 'Long'})
                    balance *= (1 + profit_pct)
                    position_state = 0 # Exit position

            # --- Check SHORT position exits (This is our active logic) ---
            elif position_state == -1:
                # 1a. Check StopLoss (triggered by bar.high - price moved AGAINST us)
                if bar.high >= stop_loss_price:
                    exit_price = stop_loss_price
                    profit_pct = (entry_price / exit_price) - 1 - (transaction_fee_pct * 2) # (entry/exit) for short profit
                    trades_log.append({'entry_price': entry_price, 'exit_price': exit_price, 'profit_pct': profit_pct, 'exit_reason': 'StopLoss', 'type': 'Short'})
                    balance *= (1 + profit_pct)
                    position_state = 0 # Exit position
                # 1b. Check TakeProfit (triggered by bar.low - price moved FOR us)
                elif bar.low <= take_profit_price:
                    exit_price = take_profit_price
                    profit_pct = (entry_price / exit_price) - 1 - (transaction_fee_pct * 2)
                    trades_log.append({'entry_price': entry_price, 'exit_price': exit_price, 'profit_pct': profit_pct, 'exit_reason': 'TakeProfit', 'type': 'Short'})
                    balance *= (1 + profit_pct)
                    position_state = 0 # Exit position

        # 2. Check entry conditions IF FLAT (position_state == 0)
        elif position_state == 0:
            
            if (not np.isnan(trend_value)):
                
                is_above_trend = (bar.close > trend_value)
                is_below_trend = (bar.close < trend_value)
                
                # --- [MODIFIED] LONG Entry Logic ---
                # --- DISABLED FOR THIS TEST ---
                is_golden_cross = bar.buy_signal
                if False and is_above_trend and is_golden_cross:
                    # This block is now disabled
                    entry_price = bar.close
                    position_state = 1 # Set to LONG
                    stop_loss_price = entry_price * (1 - stop_loss_pct)
                    take_profit_price = entry_price * (1 + take_profit_pct)

                # --- SHORT Entry Logic (Active) ---
                # Rule: Downtrend AND Overbought
                elif is_below_trend and (not np.isnan(current_rsi)):
                    is_rsi_overbought = (current_rsi > rsi_sell_threshold)
                    if is_rsi_overbought:
                        entry_price = bar.close
                        position_state = -1 # Set to SHORT
                        stop_loss_price = entry_price * (1 + stop_loss_pct)   # SL is ABOVE entry price
                        take_profit_price = entry_price * (1 - take_profit_pct) # TP is BELOW entry price

        # Log balance history for equity curve
        balance_history.append({'timestamp': bar.Index, 'balance': balance})

    print("[Backtest] Event-driven backtest complete.")
    return trades_log, pd.DataFrame(balance_history).set_index('timestamp')


# --- [Function 4: evaluate_event_driven_performance (Unchanged)] ---
def evaluate_event_driven_performance(trades_log, balance_history, df_market):
    """
    Evaluate event-driven backtest results
    """
    if not trades_log:
        print("\n--- [Evaluate] Strategy Performance Evaluation ---")
        print("[Evaluate] No trades generated during backtest period.")
        strategy_total_return = 0.0
        market_return = (df_market['close'].iloc[-1] / df_market['close'].iloc[0]) - 1
        print(f"\n[Evaluate] Strategy total return: {strategy_total_return * 100:.2f}% (No Trades)")
        print(f"[Evaluate] Market total return (Buy & Hold): {market_return * 100:.2f}%")
        print("\n[Evaluate] Conclusion: Strategy successfully filtered all signals in this market.")
        return

    print("\n--- [Evaluate] Strategy Performance Evaluation ---")
    
    total_trades = len(trades_log)
    trades_df = pd.DataFrame(trades_log)
    
    # Win rate
    wins = (trades_df['profit_pct'] > 0).sum()
    win_rate = (wins / total_trades) * 100
    
    # Profit/Loss ratio
    avg_profit = trades_df[trades_df['profit_pct'] > 0]['profit_pct'].mean()
    avg_loss = trades_df[trades_df['profit_pct'] <= 0]['profit_pct'].mean()
    profit_loss_ratio = abs(avg_profit / avg_loss) if (avg_loss != 0 and not np.isnan(avg_loss)) else np.inf
    
    # Strategy total return (based on balance curve)
    strategy_total_return = (balance_history['balance'].iloc[-1] / balance_history['balance'].iloc[0]) - 1
    
    # Market return (Buy & Hold)
    market_return = (df_market['close'].iloc[-1] / df_market['close'].iloc[0]) - 1
    
    print(f"[Evaluate] Total trades: {total_trades}")
    print(f"[Evaluate] Win Rate: {win_rate:.2f}%")
    print(f"[Evaluate] Average profit: {avg_profit*100:.2f}%")
    print(f"[Evaluate] Average loss: {avg_loss*100:.2f}%")
    print(f"[Evaluate] Profit/Loss Ratio: {profit_loss_ratio:.2f}")
    
    # Break down by Long/Short trades
    if 'type' in trades_df.columns:
        print("\n--- Trade Type Breakdown ---")
        long_trades = trades_df[trades_df['type'] == 'Long']
        short_trades = trades_df[trades_df['type'] == 'Short']
        
        print(f"Total Long Trades: {len(long_trades)}")
        if not long_trades.empty:
            print(f"  Long Win Rate: {(long_trades['profit_pct'] > 0).sum() / len(long_trades) * 100:.2f}%")
        
        print(f"Total Short Trades: {len(short_trades)}")
        if not short_trades.empty:
            print(f"  Short Win Rate: {(short_trades['profit_pct'] > 0).sum() / len(short_trades) * 100:.2f}%")

    
    print(f"\n[Evaluate] Strategy total return: {strategy_total_return * 100:.2f}%")
    
    # [FIXED] Corrected variable name from market_total_return to market_return
    print(f"[Evaluate] Market total return (Buy & Hold): {market_return * 100:.2f}%")

    if strategy_total_return > market_return:
        print("\n[Evaluate] Conclusion: Strategy outperforms the market (Buy & Hold).")
    else:
        print("\n[Evaluate] Conclusion: Strategy underperforms the market (Buy & Hold).")


# --- [Main program execution (Unchanged)] ---
if __name__ == "__main__":
    
    # --- 1. Define MTF Parameters ---
    SYMBOL = 'BTC/USDT'
    START_DATE = '2025-09-01 00:00:00' # Start date from your example
    
    # --- Timeframes ---
    CCXT_SIGNAL_TIMEFRAME = '5m'
    PANDAS_SIGNAL_FREQ = '5T'
    CCXT_TREND_TIMEFRAME = '1h'
    
    # Trend Filter Parameters
    TREND_INDICATOR_NAME = 'TREND_EMA_1H'
    TREND_EMA_LENGTH = 50
    
    # --- Signal Parameters ---
    # Short Strategy
    RSI_LENGTH = 14
    RSI_COLUMN_NAME = f'RSI_{RSI_LENGTH}'
    RSI_SELL_THRESHOLD = 70
    
    # Long Strategy (indicators still need to be calculated)
    EMA_SHORT_LEN = 10
    EMA_LONG_LEN = 30
    
    # --- 2. Fetch Data for Both Timeframes ---
    
    # Fetch signal data (5m)
    df_signal = fetch_historical_data(
        symbol=SYMBOL, 
        timeframe=CCXT_SIGNAL_TIMEFRAME, 
        from_datetime=START_DATE
    )
    
    # Fetch trend data (1h)
    df_trend = fetch_historical_data(
        symbol=SYMBOL, 
        timeframe=CCXT_TREND_TIMEFRAME, 
        from_datetime=START_DATE
    )

    if df_signal is not None and df_trend is not None:
        
        # --- 3. Prepare MTF Data ---
        print(f"[Main] Calculating trend indicator ({CCXT_TREND_TIMEFRAME} EMA {TREND_EMA_LENGTH})...")
        
        # Calculate trend EMA on the 1h data
        trend_indicator = df_trend.ta.ema(length=TREND_EMA_LENGTH)
        
        # Rename it to our defined column name
        trend_indicator.name = TREND_INDICATOR_NAME
        
        print(f"[Main] Resampling trend data to {PANDAS_SIGNAL_FREQ} timeframe...")
        
        # Resample the 1h indicator to the 5m timeframe, filling forward
        trend_resampled = trend_indicator.resample(PANDAS_SIGNAL_FREQ).ffill() 
        
        # Join the 5m signal data with the resampled 15m trend data
        df_merged = df_signal.join(trend_resampled)
        
        # --- 4. Calculate Signals ---
        # We still calculate all signals, even if we only use some
        crypto_df_with_signals = calculate_signals(
            df_merged.copy(), 
            rsi_length=RSI_LENGTH,
            rsi_col_name=RSI_COLUMN_NAME,
            ema_short_len=EMA_SHORT_LEN,
            ema_long_len=EMA_LONG_LEN
        )
        
        if crypto_df_with_signals is None or crypto_df_with_signals.empty:
            print("[Main] No valid data after signal calculation. Exiting.")
        else:
            # --- 5. Execute Event-Driven Backtest ---
            trades_log, balance_history = run_event_driven_backtest(
                crypto_df_with_signals,
                stop_loss_pct=0.01,    # 1% stop loss
                take_profit_pct=0.02,  # 2% take profit
                transaction_fee_pct=0.001, # 0.1% transaction fee
                trend_column_name=TREND_INDICATOR_NAME,
                rsi_column_name=RSI_COLUMN_NAME,
                rsi_sell_threshold=RSI_SELL_THRESHOLD
            )
            
            # --- 6. Evaluate Performance ---
            evaluate_event_driven_performance(trades_log, balance_history, crypto_df_with_signals)
    
    else:
        print("[Main] Failed to fetch data for one or both timeframes. Exiting.")