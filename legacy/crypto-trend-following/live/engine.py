# live/engine.py
# Live Trading Engine - Real-time execution (skeleton implementation)
# 
# This is a skeleton for future live trading implementation.
# The actual implementation will:
# - Connect to exchange via CCXT or native API
# - Subscribe to websocket for real-time klines
# - Execute orders through REST API
# - Implement the same ITradingContext interface as BacktestEngine

import os
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.interfaces import ITradingContext
from core.types import Order, Position


class LiveEngine(ITradingContext):
    """
    Live trading engine implementing ITradingContext interface.
    
    This is a SKELETON implementation - actual trading logic will be added later.
    The key benefit: strategy code doesn't change between backtest and live.
    
    Key differences from BacktestEngine:
    - Data comes from websocket, not CSV files
    - Orders go to exchange API, not simulated portfolio
    - Time is real system time, not simulated
    - Need to handle network errors, partial fills, etc.
    """
    
    def __init__(self, config):
        print("[LiveEngine] Initializing LiveEngine (SKELETON)...")
        self.config = config
        
        # Gateway for exchange API (to be implemented)
        self.gateway = None  # Will be: Gateway(config)
        
        # Data feed for real-time klines (to be implemented)
        self.data_feed = None  # Will be: DataFeed(config)
        
        # Order manager for tracking orders (to be implemented)
        self.order_manager = None  # Will be: OrderManager(config)
        
        # Current state
        self.is_running = False
        self.current_universe: List[str] = []
        
        print("[LiveEngine] WARNING: This is a skeleton - not ready for live trading!")
    
    # ========================================
    # ITradingContext Interface Implementation
    # ========================================
    
    def get_current_time(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(datetime.now().timestamp() * 1000)
    
    def get_current_price(self, symbol: str) -> float:
        """Get current/latest price for symbol."""
        # TODO: Implement with data_feed.get_latest_price(symbol)
        raise NotImplementedError("LiveEngine.get_current_price not implemented")
    
    def get_btc_regime(self) -> Dict[str, Any]:
        """Get BTC market regime data for circuit breaker."""
        # TODO: Implement with data_feed
        return {
            'roc_1h': 0.0,
            'above_ema': True,
            'price': 0.0
        }
    
    def buy(self, symbol: str, price: float, size_usd: float) -> Optional[Order]:
        """Open long position via exchange API."""
        # TODO: Implement with gateway.create_order()
        raise NotImplementedError("LiveEngine.buy not implemented")
    
    def sell(self, symbol: str, price: float, reason: str = '') -> Optional[Order]:
        """Close position via exchange API."""
        # TODO: Implement with gateway.create_order()
        raise NotImplementedError("LiveEngine.sell not implemented")
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol from exchange."""
        # TODO: Implement with order_manager.get_position()
        return None
    
    def get_universe(self) -> List[str]:
        """Get current tradeable universe."""
        return self.current_universe
    
    def log(self, message: str, level: str = 'INFO') -> None:
        """Log message to console and/or file."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [{level}] {message}")
    
    # ========================================
    # Live Engine Specific Methods
    # ========================================
    
    def start(self):
        """Start the live trading engine."""
        print("[LiveEngine] Starting live engine...")
        self.is_running = True
        # TODO: Implement main event loop
        raise NotImplementedError("LiveEngine.start not implemented")
    
    def stop(self):
        """Stop the live trading engine."""
        print("[LiveEngine] Stopping live engine...")
        self.is_running = False
    
    def on_kline(self, symbol: str, kline_data: Dict):
        """
        Callback for new kline data from websocket.
        This is where strategy logic would be triggered.
        """
        # TODO: Implement strategy signal checking
        pass
    
    def on_order_update(self, order: Order):
        """Callback for order status updates from exchange."""
        # TODO: Implement order tracking
        pass
