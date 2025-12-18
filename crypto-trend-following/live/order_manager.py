# live/order_manager.py
# Order Manager - Tracks orders and positions (skeleton)
#
# This will handle:
# - Order state management
# - Position tracking and sync with exchange
# - Fill reconciliation

from typing import Dict, Optional, List
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.types import Order, Position, OrderStatus


class OrderManager:
    """
    Manages orders and positions for live trading.
    Keeps local state in sync with exchange.
    
    SKELETON - To be implemented with actual order tracking.
    """
    
    def __init__(self, config):
        print("[OrderManager] Initializing OrderManager (SKELETON)...")
        self.config = config
        
        # Local state
        self.orders: Dict[str, Order] = {}  # order_id -> Order
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        
        # Fee rate for PnL calculation
        self.fee_rate = config.get('fee_rate', 0.0005)
        
        print("[OrderManager] WARNING: This is a skeleton - not tracking real orders!")
    
    def add_order(self, order: Order):
        """Add new order to tracking."""
        self.orders[order.order_id] = order
    
    def update_order(self, order_id: str, status: OrderStatus, **kwargs):
        """Update order status and fields."""
        if order_id in self.orders:
            self.orders[order_id].status = status
            for key, value in kwargs.items():
                if hasattr(self.orders[order_id], key):
                    setattr(self.orders[order_id], key, value)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self.orders.get(order_id)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol."""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Position]:
        """Get all open positions."""
        return self.positions
    
    async def sync_with_exchange(self, gateway):
        """Sync local state with exchange positions/orders."""
        # TODO: Fetch positions from exchange and reconcile
        raise NotImplementedError("OrderManager.sync_with_exchange not implemented")
    
    def on_fill(self, order: Order, fill_price: float, fill_quantity: float):
        """Handle order fill - update position state."""
        # TODO: Update position based on fill
        pass
