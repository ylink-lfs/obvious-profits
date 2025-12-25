# core/__init__.py
# Core module - shared interfaces, types, and utilities for backtest/live

from .interfaces import ITradingContext, IDataFeed, IOrderManager
from .types import Bar, Order, Trade, Position, OrderSide, OrderType, OrderStatus
from .universe import ContractListingScanner, UniverseManager

__all__ = [
    'ITradingContext',
    'IDataFeed', 
    'IOrderManager',
    'Bar',
    'Order',
    'Trade',
    'Position',
    'OrderSide',
    'OrderType',
    'OrderStatus',
    'ContractListingScanner',
    'UniverseManager',
]
