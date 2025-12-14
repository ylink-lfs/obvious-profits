# Configuration for Squeeze Entry Options Strategy

# Backtest period
START_DATE = (2023, 1, 1)
END_DATE = (2024, 3, 31)
INITIAL_CAPITAL = 15000

# Symbol pool
SYMBOL_POOL = ["TQQQ", "SOXL", "NVDA", "TSLA", "MSTR", "COIN"]

# Capital allocation
MAX_POSITION_PCT = 0.15  # Max 15% of total capital per entry

# ==================== Entry Signals ====================

# Bollinger Band Squeeze parameters
BB_PERIOD = 20
BB_STD = 2
BB_WIDTH_PERCENTILE_LOOKBACK = 90  # Look back 90 days for percentile
BB_WIDTH_PERCENTILE_THRESHOLD = 20  # 20th percentile threshold

# Close to MA20 threshold
CLOSE_TO_MA20_THRESHOLD = 0.02  # Close within 2% of MA20

# ATR parameters
ATR_SHORT_PERIOD = 5   # Recent 5-day volatility
ATR_LONG_PERIOD = 20   # Past 20-day volatility

# IV Percentile parameters
IV_PERCENTILE_THRESHOLD = 0.30  # IV Percentile < 30%
IV_PERCENTILE_LOOKBACK = 252    # 252 trading days (~52 weeks/1 year) for IV Percentile calculation
IV_ATM_DTE_MIN = 30       # Min DTE for ATM options used in IV calculation
IV_ATM_DTE_MAX = 60       # Max DTE for ATM options used in IV calculation
IV_ATM_STRIKE_RANGE = 0.05  # Consider options within 5% of current price as ATM

# Trend background
MA200_PERIOD = 200
RSI_PERIOD = 14
RSI_MIN = 40  # 40 <= RSI(14) <= 55
RSI_MAX = 55

# ==================== Entry Execution ====================

# Option expiration selection
MIN_DTE = 40  # Minimum 40 days to expiration
MONTHLY_OPTIONS_ONLY = True  # Use nearest monthly options

# Long Call parameters (OTM)
LONG_CALL_INITIAL_QUANTITY = 2  # Start with 2 OTM calls
LONG_CALL_MAX_QUANTITY = 3  # Can increase to 3 if needed
LONG_CALL_MAX_DELTA = 0.25  # Delta <= 0.25
LONG_CALL_MIN_DELTA = 0.10  # Skip entry if delta drops below 0.10

# Short Call parameters (ITM/ATM)
SHORT_CALL_QUANTITY = 1  # 1 ITM or ATM call
SHORT_CALL_MIN_DELTA = 0.60  # Delta >= 0.60

# ==================== Exit Signals ====================

# Price rally exit (OR conditions after precondition met)
# Precondition: Open price > Long strike + (Long strike - Short strike)
# Condition 1: Current RSI(14) < Previous day RSI
# Condition 2: Previous day high > Bollinger Upper Band(20, 2)

# Price drop exit
PRICE_DROP_MULTIPLIER = 0.95  # Exit if price < 0.95 * short strike

# DTE exit
DTE_EXIT_THRESHOLD = 20  # Exit when DTE <= 20

# ==================== Order Parameters ====================

LIMIT_ORDER_BUFFER = 1.01  # 1% above mid for buy orders
LIMIT_ORDER_SELL_BUFFER = 0.99  # 1% below mid for sell orders
PENDING_ORDER_EXPIRY_DAYS = 2

# ==================== Fee Structure ====================

COMMISSION_PER_CONTRACT = 0.45
MINIMUM_COMMISSION = 1.49
PLATFORM_FEE_PER_ORDER = 0.54

# ==================== Warm Up Period ====================

WARM_UP_PERIOD = 210  # days

# ==================== Option Filter ====================

STRIKE_RANGE = (-30, 30)
EXPIRATION_RANGE = (30, 120)
