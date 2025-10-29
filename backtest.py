import ccxt
import pandas as pd
import pandas_ta as ta # 引入 pandas-ta 库
import os
import numpy as np

from dotenv import load_dotenv


def fetch_historical_data(symbol, timeframe, limit):
    """
    从币安拉取历史K线数据并转换为Pandas DataFrame
    """
    
    # --- 1. 初始化 CCXT 交易所 ---
    # 我们甚至不需要API Key来拉取公共的K线数据
    # 但为了后续交易，我们保持标准写法
    
    load_dotenv() # 如果只是拉取公开数据，可以暂时不加载key
    apiKey = os.environ.get('BINANCE_API_KEY')
    secret = os.environ.get('BINANCE_SECRET_KEY')
    
    exchange = ccxt.binance({
        'enableRateLimit': True, # 自动处理速率限制
        'apiKey': apiKey,
        'secret': secret
    })
    
    # (可选) 如果您在测试网操作，需要设置
    exchange.set_sandbox_mode(True) 
    
    print(f"正在拉取 {symbol} 的 {timeframe} 数据，最近 {limit} 根K线...")

    try:
        # --- 2. 拉取数据 ---
        # ccxt 返回的是一个列表的列表 [timestamp, open, high, low, close, volume]
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcv:
            print("没有拉取到数据。")
            return None

        # --- 3. 转换为 Pandas DataFrame ---
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 将 timestamp 转换为易读的 datetime 格式
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # 将 timestamp 设置为索引 (这对于时间序列分析是标准做法)
        df.set_index('timestamp', inplace=True)
        
        # 转换数据类型为 float，因为TA计算需要
        df = df.astype(float)
        
        print(f"成功拉取 {len(df)} 根K线数据。")
        return df

    except ccxt.NetworkError as e:
        print(f"网络错误: {e}")
    except ccxt.ExchangeError as e:
        print(f"交易所错误: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")
    
    return None

def calculate_indicators(df):
    """
    在DataFrame上计算技术指标 (EMA 10 和 30)
    """
    if df is None:
        return None
        
    print("正在计算技术指标 (EMA 10, EMA 30)...")
    
    # --- 4. 计算指标 ---
    # 使用 pandas-ta，我们直接在df上调用 .ta.ema()
    # `append=True` 会自动将新列 (如 'EMA_10') 添加回原始的df中
    
    # 计算快速EMA
    df.ta.ema(length=10, append=True)
    
    # 计算慢速EMA
    df.ta.ema(length=30, append=True)
    
    # pandas-ta 默认的列名是 'EMA_10' 和 'EMA_30'
    # 我们可以重命名它们以便更清晰 (可选)
    # df.rename(columns={'EMA_10': 'ema_fast', 'EMA_30': 'ema_slow'}, inplace=True)
    
    print("指标计算完成。")
    return df


# --- [新增] 任务 3.3: 开发回测引擎 (向量化) ---
def run_backtest(df):
    """
    执行向量化回测，生成信号和持仓
    """
    if df is None: return None
    print("正在执行向量化回测...")
    
    # --- 步骤 1: 定义信号 (金叉/死叉) ---
    
    # 金叉 (买入信号): 快速线上穿慢速线
    buy_signal = (df['EMA_10'] > df['EMA_30']) & (df['EMA_10'].shift(1) <= df['EMA_30'].shift(1))
    
    # 死叉 (卖出信号): 快速线下穿慢速线
    sell_signal = (df['EMA_10'] < df['EMA_30']) & (df['EMA_10'].shift(1) >= df['EMA_30'].shift(1))
    
    # --- 步骤 2: 模拟持仓 (Position) ---
    
    # *** 错误修正 ***
    # 修正前 (错误): conditions = [(buy_signal, 1), (sell_signal, 0)]
    #                df['position'] = np.select(conditions, [1, 0], default=np.nan)
    
    # 修正后 (正确):
    # condlist 是一个纯粹的条件(bool)列表
    condlist = [buy_signal, sell_signal]
    
    # choicelist 是一个对应的结果值列表
    choicelist = [1, 0]
    
    # np.select 会按顺序检查condlist：
    # 1. 如果 buy_signal 为 True, 赋值为 1
    # 2. 否则, 如果 sell_signal 为 True, 赋值为 0
    # 3. 否则, 赋值为 default (np.nan)
    df['position'] = np.select(condlist, choicelist, default=np.nan)
    
    # 关键一步: 填充信号间的持仓状态
    # .fillna(method='ffill') 会用前一个有效值 (0或1) 填充所有 np.nan
    df['position'].fillna(method='ffill', inplace=True)
    
    # 处理第一行可能仍为 NaN 的情况 (如果一开始没有信号)
    df['position'].fillna(0, inplace=True)
    
    print("回测信号与持仓模拟完成。")
    return df


# --- [新增] 任务 3.4: 评估绩效 (包含手续费) ---
def evaluate_performance(df, transaction_fee_percent=0.001):
    """
    评估策略绩效
    transaction_fee_percent: 币安手续费 (0.1% = 0.001)
    """
    if df is None or 'position' not in df.columns:
        print("DataFrame不完整，无法评估。")
        return

    print("\n--- 策略绩效评估 ---")
    
    # --- 步骤 1: 计算市场本身的回报 (Buy & Hold) ---
    # 我们假设在第一根K线的收盘价买入，持有到最后
    df['market_return_pct'] = df['close'].pct_change()
    df['market_return_cumulative'] = (1 + df['market_return_pct']).cumprod()
    buy_and_hold_return = df['market_return_cumulative'].iloc[-1]
    
    # --- 步骤 2: 计算策略回报 (Strategy Return) ---
    
    # 关键: 我们在信号出现的 *下一根* K线开盘时交易
    # 所以策略的回报 = 市场回报 * *上一根K线*的持仓状态
    df['strategy_return_pct'] = df['market_return_pct'] * df['position'].shift(1)
    
    # --- 步骤 3: 模拟交易手续费 ---
    # 当持仓状态发生变化时 (0 -> 1 或 1 -> 0)，我们就支付一次手续费
    df['trade_executed'] = (df['position'] != df['position'].shift(1))
    
    if df['trade_executed'].any(): # 确保有交易发生
        # 在发生交易的 K 线上, 减去手续费
        df.loc[df['trade_executed'], 'strategy_return_pct'] -= transaction_fee_percent
    
    # --- 步骤 4: 计算最终的累计回报 ---
    df['strategy_return_cumulative'] = (1 + df['strategy_return_pct']).cumprod()
    strategy_total_return = df['strategy_return_cumulative'].iloc[-1]

    # --- 步骤 5: 打印结果 ---
    print(f"数据周期: {df.index[0]}  至  {df.index[-1]}")
    print(f"交易手续费 (单边): {transaction_fee_percent * 100:.2f}%")
    print(f"总交易次数: {df['trade_executed'].sum()}")
    
    # (1 - 1) * 100 = 0%
    print(f"\n策略总回报 (Strategy): {(strategy_total_return - 1) * 100:.2f}%")
    print(f"市场总回报 (Buy & Hold): {(buy_and_hold_return - 1) * 100:.2f}%")
    
    if strategy_total_return > buy_and_hold_return:
        print("\n结论: 策略表现优于市场 (Buy & Hold)。")
    else:
        print("\n结论: 策略表现劣于市场 (Buy & Hold)。")
        
    # (可选) 您可以取消注释下面这行来保存详细的回测结果到CSV
    # df.to_csv("backtest_results.csv")
    # print("详细结果已保存到 backtest_results.csv")



# --- 主程序执行 ---
if __name__ == "__main__":
    
    # --- 阶段三, 任务 2.1: 拉取数据 ---
    # 我们拉取 BTC/USDT, 5分钟线, 最近1000根 (大约3.5天的数据)
    # 在真实回测中，您需要拉取成千上万根K线
    crypto_df = fetch_historical_data(symbol='BTC/USDT', timeframe='5m', limit=1000)

    if crypto_df is not None:
        
        # --- 阶段三, 任务 3.2: 计算指标 ---
        crypto_df_with_indicators = calculate_indicators(crypto_df)
        
        # 显示最后5行数据，检查EMA列是否已成功添加
        print("\n--- 数据预览 (最后5行) ---")
        print(crypto_df_with_indicators.tail())
    
        # 阶段三, 任务 3.3: 执行回测
        backtest_df = run_backtest(crypto_df_with_indicators)
        
        # 阶段三, 任务 3.4 & 4.1: 评估绩效
        evaluate_performance(backtest_df, transaction_fee_percent=0.001)
