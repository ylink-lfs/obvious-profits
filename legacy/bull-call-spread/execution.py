# Order execution for Squeeze Entry Options Strategy
from AlgorithmImports import *
from typing import Optional, List, Tuple
import config


class OrderExecutor:
    """Handles order execution for the Squeeze strategy."""
    
    def __init__(self, algorithm, custom_fee_model):
        self.algo = algorithm
        self.custom_fee_model = custom_fee_model
        self.pending_orders: List[dict] = []
    
    def security_has_data(self, symbol) -> bool:
        """Check if a security has received data and is ready for trading."""
        if not self.algo.securities.contains_key(symbol):
            return False
        security = self.algo.securities[symbol]
        return security.has_data and security.price > 0
    
    def place_limit_order_safe(self, symbol, quantity: int, limit_price: float):
        """Place a limit order, queuing it if data is not yet available."""
        if self.security_has_data(symbol):
            self.algo.limit_order(symbol, quantity, limit_price)
        else:
            self.pending_orders.append({
                "symbol": symbol,
                "quantity": quantity,
                "limit_price": limit_price,
                "created_date": self.algo.time
            })
            self.algo.log(f"Queued pending order: {symbol}, Qty: {quantity}, Price: {limit_price}")
    
    def process_pending_orders(self):
        """Process any pending orders that were waiting for data."""
        if not self.pending_orders:
            return
        
        still_pending = []
        for order_info in self.pending_orders:
            symbol = order_info["symbol"]
            quantity = order_info["quantity"]
            limit_price = order_info["limit_price"]
            created_date = order_info["created_date"]
            
            # Cancel if order is more than N days old
            if (self.algo.time - created_date).days > config.PENDING_ORDER_EXPIRY_DAYS:
                self.algo.log(f"Pending order expired: {symbol}")
                continue
            
            if self.security_has_data(symbol):
                self.algo.limit_order(symbol, quantity, limit_price)
                self.algo.log(f"Executed pending order: {symbol}, Qty: {quantity}, Price: {limit_price}")
            else:
                still_pending.append(order_info)
        
        self.pending_orders = still_pending
    
    def add_contract_with_fee(self, symbol):
        """Add option contract and apply custom fee model."""
        if not self.algo.securities.contains_key(symbol):
            option_contract = self.algo.add_option_contract(symbol)
            option_contract.set_fee_model(self.custom_fee_model)
    
    def liquidate_if_tradable(self, symbol) -> bool:
        """Liquidate a position if it's tradable."""
        if self.algo.securities.contains_key(symbol) and self.algo.securities[symbol].is_tradable:
            self.algo.liquidate(symbol)
            return True
        else:
            self.algo.log(f"Warning: Cannot liquidate {symbol} - not tradable")
            return False
    
    def find_monthly_expiration(self, chain, min_dte: int) -> Optional[datetime]:
        """
        Find the nearest monthly option expiration with at least min_dte days.
        
        Monthly options typically expire on the 3rd Friday of the month.
        """
        if not chain:
            return None
        
        # Get all unique expiration dates
        expirations = sorted(set(c.expiry for c in chain))
        
        for exp in expirations:
            dte = (exp - self.algo.time).days
            if dte < min_dte:
                continue
            
            # Check if it's a monthly expiration (3rd Friday)
            # Monthly options expire on Friday, and it's the 3rd one (day 15-21)
            if exp.weekday() == 4 and 15 <= exp.day <= 21:
                return exp
        
        # If no monthly found, return nearest valid expiration
        for exp in expirations:
            dte = (exp - self.algo.time).days
            if dte >= min_dte:
                return exp
        
        return None
    
    def find_short_call(self, chain, expiration, current_price: float,
                        min_delta: float) -> Optional[Tuple]:
        """
        Find a short call (ITM/ATM) with delta >= min_delta.
        
        Uses bid price for short leg (selling) to be conservative.
        
        Returns (contract_symbol, contract_data) or None
        """
        if not chain:
            return None
        
        # Filter calls with matching expiration
        calls = [c for c in chain 
                 if c.right == OptionRight.CALL and c.expiry == expiration]
        
        if not calls:
            return None
        
        # Find contract with delta >= min_delta (ITM/ATM)
        # Sort by delta descending, pick the one closest to min_delta from above
        candidates = []
        for c in calls:
            delta = self._get_delta(c)
            if delta is not None and delta >= min_delta:
                candidates.append((c, delta))
        
        if not candidates:
            # Fallback: estimate by strike (ITM means strike < current price for calls)
            for c in calls:
                if c.strike <= current_price:  # ITM or ATM
                    estimated_delta = self._estimate_call_delta(c.strike, current_price)
                    if estimated_delta >= min_delta:
                        candidates.append((c, estimated_delta))
        
        if not candidates:
            return None
        
        # Pick the one closest to min_delta (from above)
        candidates.sort(key=lambda x: x[1])
        best = candidates[0]
        
        # Get bid price for short leg (selling)
        bid_price = self._get_bid_price_from_contract(best[0])
        
        return (best[0].symbol, {
            "bid": best[0].bid_price,
            "ask": best[0].ask_price,
            "last": best[0].last_price,
            "strike": best[0].strike,
            "delta": best[1],
            "bid_price": bid_price  # Use bid price for order
        })
    
    def find_long_call(self, chain, expiration, current_price: float,
                       max_delta: float, min_delta: float,
                       short_premium: float, quantity: int,
                       max_debit: float = 0.0) -> Optional[Tuple]:
        """
        Find a long call (OTM) with delta <= max_delta and delta >= min_delta.
        
        The selected call should satisfy:
        - Net credit >= -max_debit (i.e., short_bid - quantity * long_ask >= -max_debit)
        
        If max_debit is 0, requires a net credit (short premium covers long cost).
        If max_debit > 0, allows a small net debit up to that amount.
        
        Uses ask price for long leg (buying) to be conservative.
        
        If not found, move strike up until condition is met or delta < min_delta.
        
        Returns (contract_symbol, contract_data, final_quantity, net_credit) or None
        """
        if not chain:
            return None
        
        # Filter calls with matching expiration
        calls = [c for c in chain 
                 if c.right == OptionRight.CALL and c.expiry == expiration]
        
        if not calls:
            return None
        
        # Get OTM calls (strike > current price) with delta <= max_delta
        candidates = []
        for c in calls:
            if c.strike <= current_price:  # Skip ITM/ATM
                continue
            
            delta = self._get_delta(c)
            if delta is None:
                delta = self._estimate_call_delta(c.strike, current_price)
            
            if min_delta <= delta <= max_delta:
                candidates.append((c, delta))
        
        if not candidates:
            return None
        
        # Sort by strike ascending (lower strike = higher delta, more expensive)
        candidates.sort(key=lambda x: x[0].strike)
        
        # Try to find a contract where premium condition is met
        # Use ask price for long leg (buying) - more conservative
        for c, delta in candidates:
            ask_price = self._get_ask_price_from_contract(c)
            if ask_price <= 0:
                continue
            
            # Calculate net credit: short premium - long cost
            # Positive = credit spread, Negative = debit spread
            total_long_cost = quantity * ask_price * 100
            net_credit = short_premium * 100 - total_long_cost
            
            # Allow if net credit >= -max_debit (accept small debits up to threshold)
            if net_credit >= -max_debit:
                return (c.symbol, {
                    "bid": c.bid_price,
                    "ask": c.ask_price,
                    "last": c.last_price,
                    "strike": c.strike,
                    "delta": delta,
                    "ask_price": ask_price  # Use ask price for order
                }, quantity, net_credit)
        
        # If 2 contracts don't work, try with 3 contracts at higher strikes
        if quantity == 2:
            for c, delta in candidates:
                if delta < min_delta:
                    break
                    
                ask_price = self._get_ask_price_from_contract(c)
                if ask_price <= 0:
                    continue
                
                # Try with 3 contracts
                total_long_cost = 3 * ask_price * 100
                net_credit = short_premium * 100 - total_long_cost
                
                if net_credit >= -max_debit:
                    return (c.symbol, {
                        "bid": c.bid_price,
                        "ask": c.ask_price,
                        "last": c.last_price,
                        "strike": c.strike,
                        "delta": delta,
                        "ask_price": ask_price  # Use ask price for order
                    }, 3, net_credit)
        
        return None
    
    def _get_delta(self, contract) -> Optional[float]:
        """Get delta from contract Greeks if available."""
        if hasattr(contract, 'greeks') and contract.greeks is not None:
            delta = contract.greeks.delta
            if delta is not None and delta != 0:
                return delta
        return None
    
    def _estimate_call_delta(self, strike: float, current_price: float) -> float:
        """Estimate call delta based on moneyness."""
        moneyness = current_price / strike
        
        if moneyness >= 1.10:  # Deep ITM
            return 0.90
        elif moneyness >= 1.05:  # ITM
            return 0.75
        elif moneyness >= 1.00:  # ATM
            return 0.55
        elif moneyness >= 0.97:  # Slightly OTM
            return 0.40
        elif moneyness >= 0.94:  # OTM
            return 0.25
        elif moneyness >= 0.90:  # More OTM
            return 0.15
        else:  # Deep OTM
            return 0.08
    
    def _get_mid_price_from_contract(self, contract) -> float:
        """Calculate mid price from contract bid/ask."""
        bid = contract.bid_price
        ask = contract.ask_price
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return contract.last_price if contract.last_price > 0 else 0
    
    def _get_ask_price_from_contract(self, contract) -> float:
        """Get ask price for buying (long leg). Falls back to mid price if unavailable."""
        ask = contract.ask_price
        if ask > 0:
            return ask
        # Fallback to mid price
        return self._get_mid_price_from_contract(contract)
    
    def _get_bid_price_from_contract(self, contract) -> float:
        """Get bid price for selling (short leg). Falls back to mid price if unavailable."""
        bid = contract.bid_price
        if bid > 0:
            return bid
        # Fallback to mid price
        return self._get_mid_price_from_contract(contract)
    
    def get_mid_price(self, data: dict) -> float:
        """Calculate mid price from bid/ask dictionary."""
        bid = data.get("bid", 0)
        ask = data.get("ask", 0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return data.get("last", 0)
    
    def get_ask_price(self, data: dict) -> float:
        """Get ask price for buying (long leg). Falls back to mid price if unavailable."""
        ask = data.get("ask", 0)
        if ask > 0:
            return ask
        # Fallback to mid price
        return self.get_mid_price(data)
    
    def get_bid_price(self, data: dict) -> float:
        """Get bid price for selling (short leg). Falls back to mid price if unavailable."""
        bid = data.get("bid", 0)
        if bid > 0:
            return bid
        # Fallback to mid price
        return self.get_mid_price(data)
