# live/gateway.py
# Exchange Gateway - API wrapper for order execution (skeleton)
#
# This will wrap CCXT or native Binance API for:
# - Creating/canceling orders
# - Fetching account balance
# - Managing positions

from typing import Optional, Dict, Any
from datetime import datetime


class Gateway:
    """
    Exchange gateway for order execution.
    Wraps CCXT or native exchange API.
    
    SKELETON - To be implemented with actual API calls.
    """
    
    def __init__(self, config):
        print("[Gateway] Initializing Gateway (SKELETON)...")
        self.config = config
        self.exchange = None  # Will be: ccxt.binanceusdm({...})
        
        # API credentials from config or .env
        self.api_key = config.get('api_key', '')
        self.api_secret = config.get('api_secret', '')
        
        print("[Gateway] WARNING: This is a skeleton - not connected to exchange!")
    
    async def connect(self):
        """Connect to exchange API."""
        # TODO: Initialize CCXT exchange
        raise NotImplementedError("Gateway.connect not implemented")
    
    async def create_order(
        self,
        symbol: str,
        side: str,  # 'BUY' or 'SELL'
        order_type: str,  # 'MARKET' or 'LIMIT'
        quantity: float,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create an order on the exchange."""
        # TODO: Implement with exchange.create_order()
        raise NotImplementedError("Gateway.create_order not implemented")
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an open order."""
        # TODO: Implement with exchange.cancel_order()
        raise NotImplementedError("Gateway.cancel_order not implemented")
    
    async def get_balance(self) -> Dict[str, float]:
        """Get account balances."""
        # TODO: Implement with exchange.fetch_balance()
        raise NotImplementedError("Gateway.get_balance not implemented")
    
    async def get_positions(self) -> Dict[str, Dict]:
        """Get all open positions."""
        # TODO: Implement with exchange.fetch_positions()
        raise NotImplementedError("Gateway.get_positions not implemented")
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get open orders."""
        # TODO: Implement with exchange.fetch_open_orders()
        raise NotImplementedError("Gateway.get_open_orders not implemented")
