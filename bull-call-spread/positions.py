# Position management for Squeeze Entry Options Strategy
from AlgorithmImports import *
from typing import Dict, Optional, List
import config
from models import SqueezePosition


class PositionManager:
    """Manages positions for the Squeeze strategy."""
    
    def __init__(self, algorithm, executor):
        self.algo = algorithm
        self.executor = executor
        self.active_positions: Dict[str, SqueezePosition] = {}  # symbol -> position
    
    def has_position(self, symbol: str) -> bool:
        """Check if there's an active position for the symbol."""
        return symbol in self.active_positions
    
    def get_position(self, symbol: str) -> Optional[SqueezePosition]:
        """Get the active position for a symbol."""
        return self.active_positions.get(symbol)
    
    def enter_squeeze_spread(self, symbol: str, symbol_data, 
                              current_price: float, available_capital: float) -> bool:
        """
        Enter a squeeze spread position.
        
        Structure:
        - Buy 2-3 OTM calls (delta <= 0.25)
        - Sell 1 ITM/ATM call (delta >= 0.60)
        
        Premium constraint:
        - Premium received from short call >= Premium paid for long calls
        - Minimize the difference
        
        Returns True if position was entered successfully.
        """
        if self.has_position(symbol):
            self.algo.log(f"Already have position in {symbol}, skipping entry")
            return False
        
        # Get option chain
        chain = self.algo.option_chain(symbol_data.option_symbol)
        if not chain:
            self.algo.log(f"No option chain available for {symbol}")
            return False
        
        # Find monthly expiration with min DTE
        expiration = self.executor.find_monthly_expiration(chain, config.MIN_DTE)
        if not expiration:
            self.algo.log(f"No valid expiration found for {symbol}")
            return False
        
        dte = (expiration - self.algo.time).days
        self.algo.log(f"Selected expiration for {symbol}: {expiration.date()}, DTE: {dte}")
        
        # Find short call (ITM/ATM, delta >= 0.60)
        short_result = self.executor.find_short_call(
            chain, expiration, current_price, config.SHORT_CALL_MIN_DELTA
        )
        
        if not short_result:
            self.algo.log(f"No suitable short call found for {symbol}")
            return False
        
        short_call_symbol, short_data = short_result
        # Use bid price for short leg (selling)
        short_premium = short_data.get("bid_price", self.executor.get_bid_price(short_data))
        
        if short_premium <= 0:
            self.algo.log(f"Short call premium not available for {symbol}")
            return False
        
        self.algo.log(f"Short call for {symbol}: Strike {short_data['strike']:.2f}, "
                     f"Delta {short_data['delta']:.2f}, Bid Premium {short_premium:.2f}")
        
        # Find long call (OTM, delta <= 0.25, delta >= 0.10)
        long_result = self.executor.find_long_call(
            chain, expiration, current_price,
            config.LONG_CALL_MAX_DELTA, config.LONG_CALL_MIN_DELTA,
            short_premium, config.LONG_CALL_INITIAL_QUANTITY
        )
        
        if not long_result:
            self.algo.log(f"No suitable long call found for {symbol} - skipping entry")
            return False
        
        long_call_symbol, long_data, long_quantity = long_result
        # Use ask price for long leg (buying)
        long_premium = long_data.get("ask_price", self.executor.get_ask_price(long_data))
        
        self.algo.log(f"Long call for {symbol}: Strike {long_data['strike']:.2f}, "
                     f"Delta {long_data['delta']:.2f}, Ask Premium {long_premium:.2f}, Qty: {long_quantity}")
        
        # Calculate total cost and verify capital constraint
        total_long_cost = long_quantity * long_premium * 100
        total_short_premium = short_premium * 100
        net_cost = total_long_cost - total_short_premium
        
        # The spread should be a credit or minimal debit
        if net_cost > available_capital:
            self.algo.log(f"Insufficient capital for {symbol}: Need {net_cost:.2f}, Have {available_capital:.2f}")
            return False
        
        # Add contracts and place orders
        self.executor.add_contract_with_fee(long_call_symbol)
        self.executor.add_contract_with_fee(short_call_symbol)
        
        # Place buy order for long calls (use ask price with buffer)
        long_order_price = round(long_premium * config.LIMIT_ORDER_BUFFER, 2)
        self.executor.place_limit_order_safe(long_call_symbol, long_quantity, long_order_price)
        
        # Place sell order for short call (use bid price with buffer)
        short_order_price = round(short_premium * config.LIMIT_ORDER_SELL_BUFFER, 2)
        self.executor.place_limit_order_safe(short_call_symbol, -config.SHORT_CALL_QUANTITY, short_order_price)
        
        # Create and store position
        position = SqueezePosition(
            symbol=symbol,
            entry_date=self.algo.time,
            entry_price=current_price,
            long_call_symbol=long_call_symbol,
            long_call_strike=long_data['strike'],
            long_call_quantity=long_quantity,
            short_call_symbol=short_call_symbol,
            short_call_strike=short_data['strike'],
            short_call_quantity=config.SHORT_CALL_QUANTITY,
            total_premium_paid=total_long_cost,
            total_premium_received=total_short_premium
        )
        
        self.active_positions[symbol] = position
        
        self.algo.log(f"Entered squeeze spread for {symbol}: "
                     f"Long {long_quantity}x {long_data['strike']:.2f}C @ {long_order_price:.2f}, "
                     f"Short 1x {short_data['strike']:.2f}C @ {short_order_price:.2f}, "
                     f"Net: ${net_cost:.2f}")
        
        return True
    
    def close_position(self, symbol: str, reason: str) -> bool:
        """Close an active position."""
        if not self.has_position(symbol):
            self.algo.log(f"No position to close for {symbol}")
            return False
        
        position = self.active_positions[symbol]
        self.algo.log(f"Closing position for {symbol} - Reason: {reason}")
        
        # Close long calls
        if position.long_call_symbol:
            self.executor.liquidate_if_tradable(position.long_call_symbol)
        
        # Close short call (buy back)
        if position.short_call_symbol:
            self.executor.liquidate_if_tradable(position.short_call_symbol)
        
        del self.active_positions[symbol]
        return True
    
    def close_all_positions(self, reason: str):
        """Close all active positions."""
        symbols = list(self.active_positions.keys())
        for symbol in symbols:
            self.close_position(symbol, reason)
    
    def get_active_symbols(self) -> List[str]:
        """Get list of symbols with active positions."""
        return list(self.active_positions.keys())
    
    def get_position_count(self) -> int:
        """Get number of active positions."""
        return len(self.active_positions)
