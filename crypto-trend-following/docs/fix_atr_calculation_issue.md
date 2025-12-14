# ATR 計算失效問題修復報告

**日期**: 2025-12-05  
**狀態**: ✅ 已修復

---

## 問題描述

回測運行時出現大量警告：
```
[Portfolio] WARNING: Invalid risk (SL check failed) at 2020-01-04 04:00:00. Skipping.
```

導致幾乎所有交易信號被跳過，回測無法正常執行。

---

## 根本原因分析

### 初步假設（文檔中記錄）
`pandas-ta` 庫的 ATR 計算使用了隱式列名推斷，導致計算結果為 `NaN` 或 `0`。

### 實際根因
經過調試發現，**ATR 計算本身是正確的**（數據中無 NaN 或零值）。

真正的問題在於 `engine.py` 中的 **信號處理邏輯錯誤**：

1. `BollingerMeanReversion` 策略在價格觸及布林帶中軌時返回止盈信號：
   ```python
   ('SELL', middle_band, 0.0, 'BB_MEAN_REVERT')  # sl_price = 0.0
   ```

2. 當 `portfolio.state == 0`（空倉）時，`engine.py` 錯誤地將此 `SELL` 信號當作 **做空開倉信號** 處理

3. 由於 `sl_price = 0.0`，風險計算變為：
   ```python
   risk_per_unit = stop_loss_price - entry_price = 0.0 - middle_band < 0
   ```

4. 負風險觸發 "Invalid risk" 警告，交易被跳過

---

## 修復方案

**修改文件**: `engine.py`

**修改內容**: 在處理 `SELL` 信號時，增加 `sl_price > 0` 的檢查條件

### 修改前
```python
elif signal[0] == 'SELL':
    entry_price, sl_price, trade_type = signal[1], signal[2], signal[3]
    self.portfolio.handle_entry_signal(bar, 'SELL', entry_price, sl_price, trade_type)
```

### 修改後
```python
# [FIX] Only handle SELL as short-entry if sl_price > 0
# This prevents treating Take-Profit SELL signals (sl=0) as short entries
elif signal[0] == 'SELL' and signal[2] > 0:
    entry_price, sl_price, trade_type = signal[1], signal[2], signal[3]
    self.portfolio.handle_entry_signal(bar, 'SELL', entry_price, sl_price, trade_type)
```

---

## 修復驗證

修復後回測正常運行，無 "Invalid risk" 警告：

```
--- [Evaluate] Strategy Performance Evaluation ---
[Evaluate] Total trades: 122
[Evaluate] Win Rate: 41.80%
[Evaluate] Average profit: 1.36%
[Evaluate] Average loss: -1.48%
[Evaluate] Profit/Loss Ratio: 0.92
```

---

## 補充說明

### 關於 `data_handler.py` 中的 ATR 計算

當前代碼已經正確使用顯式參數傳遞：
```python
df[self.config['atr_col_name']] = df.ta.atr(
    high=df['high'], 
    low=df['low'], 
    close=df['close'],
    length=self.config['atr_length']
)
```

這是正確的做法，應保持不變。

### 信號設計建議

為避免類似問題，建議在策略設計時明確區分：
- **開倉信號**: `('BUY'/'SELL', entry_price, stop_loss_price, trade_type)` - `sl_price > 0`
- **平倉信號**: 可考慮使用獨立的信號類型如 `('CLOSE_LONG', exit_price, reason)`

---

## 相關文件

- `engine.py` - 主要修改文件
- `strategy/mean_revision.py` - 策略文件（無需修改）
- `portfolio.py` - 風險管理文件（無需修改）
- `data_handler.py` - 數據處理文件（無需修改）
