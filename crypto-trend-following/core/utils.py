# core/utils.py
# Common utility functions shared between backtest and live

import pandas as pd
from typing import Optional
from datetime import datetime


def ms_to_datetime(timestamp_ms: int) -> datetime:
    """Convert millisecond timestamp to datetime."""
    return datetime.fromtimestamp(timestamp_ms / 1000)


def datetime_to_ms(dt: datetime) -> int:
    """Convert datetime to millisecond timestamp."""
    return int(dt.timestamp() * 1000)


def pd_timestamp_to_ms(ts: pd.Timestamp) -> int:
    """Convert pandas Timestamp to milliseconds."""
    return int(ts.value // 10**6)


def ms_to_pd_timestamp(timestamp_ms: int) -> pd.Timestamp:
    """Convert millisecond timestamp to pandas Timestamp."""
    return pd.to_datetime(timestamp_ms, unit='ms')


def format_pnl(pnl: float) -> str:
    """Format PnL with color indicator."""
    if pnl >= 0:
        return f"+${pnl:.2f}"
    else:
        return f"-${abs(pnl):.2f}"


def format_pct(pct: float) -> str:
    """Format percentage."""
    if pct >= 0:
        return f"+{pct:.2f}%"
    else:
        return f"{pct:.2f}%"


def calculate_position_size(
    balance: float,
    fixed_size: float,
    price: float,
    leverage: int = 1
) -> tuple[float, float]:
    """
    Calculate position size in USD and units.
    
    Args:
        balance: Current account balance
        fixed_size: Fixed position size in USD
        price: Entry price
        leverage: Leverage multiplier (default 1)
    
    Returns:
        Tuple of (size_usd, size_units)
    """
    size_usd = min(fixed_size, balance)
    size_units = (size_usd * leverage) / price
    return size_usd, size_units


def calculate_pnl(
    entry_price: float,
    exit_price: float,
    size_units: float,
    fee_rate: float = 0.0005
) -> tuple[float, float, float]:
    """
    Calculate PnL for a trade.
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        size_units: Position size in units
        fee_rate: Fee rate per trade (default 0.05%)
    
    Returns:
        Tuple of (gross_pnl, fees, net_pnl)
    """
    gross_pnl = (exit_price - entry_price) * size_units
    entry_value = entry_price * size_units
    exit_value = exit_price * size_units
    fees = (entry_value + exit_value) * fee_rate
    net_pnl = gross_pnl - fees
    return gross_pnl, fees, net_pnl
