# Order execution for QQQ Boost Options Strategy
from AlgorithmImports import *
from typing import Optional, List
import config


class OrderExecutor:
    """Handles order execution for the strategy."""
    
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
    
    def find_option_contract(self, target_delta: float, is_call: bool, 
                             min_dte: int, max_dte: int, 
                             current_price: float,
                             prefer_jan_june: bool = False) -> Optional[tuple]:
        """Find an option contract matching the criteria."""
        chain = self.algo.option_chain(self.algo.qqq_symbol)
        if not chain:
            self.algo.log("No option chain available")
            return None
        
        # Step 1: Filter by option type (call/put)
        option_type = OptionRight.CALL if is_call else OptionRight.PUT
        type_filtered = [c for c in chain if c.right == option_type]
        
        if not type_filtered:
            self.algo.log(f"No {'call' if is_call else 'put'} options available")
            return None
        
        # Step 2: Filter by DTE range
        dte_filtered = []
        for c in type_filtered:
            dte = (c.expiry - self.algo.time).days
            if min_dte <= dte <= max_dte:
                dte_filtered.append((c, dte))
        
        if not dte_filtered:
            self.algo.log(f"No contracts in DTE range [{min_dte}, {max_dte}]")
            return None
        
        # Step 3: For LEAPS, prefer January or June expirations
        if prefer_jan_june:
            jan_june_contracts = [(c, dte) for c, dte in dte_filtered 
                                  if c.expiry.month in [1, 6]]
            if jan_june_contracts:
                dte_filtered = jan_june_contracts
                self.algo.log(f"Found {len(jan_june_contracts)} Jan/June LEAPS contracts")
        
        # Step 4: Select by delta
        contract = self._select_by_delta(dte_filtered, target_delta, is_call, 
                                         current_price, min_dte, max_dte)
        return contract
    
    def _select_by_delta(self, dte_filtered: list, target_delta: float, 
                         is_call: bool, current_price: float,
                         min_dte: int, max_dte: int) -> Optional[tuple]:
        """Select contract by delta or estimated delta."""
        # Try to use actual Greeks first
        contracts_with_delta = []
        for c, dte in dte_filtered:
            if hasattr(c, 'greeks') and c.greeks is not None:
                delta = c.greeks.delta
                if delta is not None and delta != 0:
                    contracts_with_delta.append((c, dte, delta))
        
        target_dte = (min_dte + max_dte) / 2
        
        if contracts_with_delta:
            best = min(contracts_with_delta,
                      key=lambda x: (abs(x[2] - target_delta), abs(x[1] - target_dte)))
            
            contract = best[0]
            self.algo.log(f"Selected by delta: {contract.symbol}, Delta={best[2]:.3f}, DTE={best[1]}")
            return (contract.symbol, {
                "bid": contract.bid_price,
                "ask": contract.ask_price,
                "last": contract.last_price,
                "strike": contract.strike
            })
        
        # Fallback: Estimate delta based on strike price
        target_strike = self._estimate_strike_from_delta(target_delta, is_call, current_price)
        
        best = min(dte_filtered,
                  key=lambda x: (abs(x[0].strike - target_strike), abs(x[1] - target_dte)))
        
        contract = best[0]
        self.algo.log(f"Selected by strike: {contract.symbol}, Strike={contract.strike:.2f}, DTE={best[1]}")
        return (contract.symbol, {
            "bid": contract.bid_price,
            "ask": contract.ask_price,
            "last": contract.last_price,
            "strike": contract.strike
        })
    
    def _estimate_strike_from_delta(self, target_delta: float, is_call: bool, 
                                    current_price: float) -> float:
        """Estimate target strike based on target delta."""
        if is_call:
            if target_delta >= 0.8:
                return current_price * 0.91
            elif target_delta >= 0.6:
                return current_price * 0.9875
            elif target_delta >= 0.5:
                return current_price
            else:
                return current_price * 1.025
        else:
            abs_delta = abs(target_delta)
            if abs_delta >= 0.5:
                return current_price * (1 + (abs_delta - 0.5) * 0.15)
            else:
                return current_price * (1 - abs_delta * 0.2)
    
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
