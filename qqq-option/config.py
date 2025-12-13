# Configuration for QQQ Boost Options Strategy

# Backtest period
START_DATE = (2020, 12, 11)
END_DATE = (2025, 12, 1)
INITIAL_CAPITAL = 100000

# Core + Satellite allocation (Improvement A)
CORE_ALLOCATION = 0.60  # 60% in QQQ stock
SATELLITE_ALLOCATION = 0.40  # 40% for Boost strategy

# Capital allocation
MAX_OPTION_ALLOCATION = 0.70  # 70% max in options
CASH_RESERVE_RATIO = 0.30  # 30% cash reserve
MAX_POSITION_PCT = 0.15  # Max 15% per position

# Base investment amount as percentage of portfolio
BASE_AMOUNT_PCT = 0.0125

# Option filter parameters
STRIKE_RANGE = (-20, 20)
EXPIRATION_RANGE = (14, 200)

# Layer configuration
LAYER_CONFIG = {
    1: {"dd_threshold": -0.05, "coefficient": 1.0, "position_type": "spread", "dte_target": 45},
    2: {"dd_threshold": -0.09, "coefficient": 1.5, "position_type": "spread", "dte_target": 45},
    3: {"dd_threshold": -0.14, "coefficient": 2.25, "position_type": "leaps", "dte_target": 180},
    4: {"dd_threshold": -0.16, "coefficient": 3.375, "position_type": "leaps", "dte_target": 180},
    5: {"dd_threshold": -0.20, "coefficient": 5.0625, "position_type": "leaps", "dte_target": 180},
}

# DTE thresholds
SPREAD_DTE_MIN = 30
SPREAD_DTE_MAX = 60
LEAPS_DTE_MIN = 150
LEAPS_DTE_MAX = 400
SPREAD_ROLL_DTE = 14
LEAPS_ROLL_DTE = 90

# Delta targets
DEEP_ITM_CALL_DELTA = 0.75
LEAPS_DELTA = 0.85
LONG_CALL_DELTA = 0.6
SHORT_CALL_DELTA = 0.3
PROTECTIVE_PUT_DELTA = -0.27

# RSI thresholds
RSI_PERIOD = 14
RSI_UPTREND_THRESHOLD = 55
RSI_DOWNTREND_THRESHOLD = 40

# Exit signal thresholds
EXIT_RSI_THRESHOLD = 58
EXIT_ATH_DIST_THRESHOLD = -0.02

# Hedge parameters
HEDGE_SMA_BUFFER = 0.99  # 1% buffer to confirm break
HEDGE_AMOUNT_PCT = 0.05  # 5% of portfolio for protective puts

# Order parameters
LIMIT_ORDER_BUFFER = 1.01  # 1% above mid for buy orders
LIMIT_ORDER_SELL_BUFFER = 0.99  # 1% below mid for sell orders
PENDING_ORDER_EXPIRY_DAYS = 2

# Stop loss threshold
PRICE_DROP_STOP_LOSS = -0.05  # -5% price drop triggers stop loss

# Deep drawdown threshold
DEEP_DRAWDOWN_THRESHOLD = -0.50

# Fee structure
COMMISSION_PER_CONTRACT = 0.45
MINIMUM_COMMISSION = 1.49
PLATFORM_FEE_PER_ORDER = 0.54

# Warm up period (days)
WARM_UP_PERIOD = 210
