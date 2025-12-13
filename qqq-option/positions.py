# Position management for QQQ Boost Options Strategy
from AlgorithmImports import *
from typing import Dict, Optional
import config


class PositionManager:
    """Manages positions for the strategy."""
    
    def __init__(self, algorithm, executor):
        self.algo = algorithm
        self.executor = executor
        self.active_layers: Dict[int, dict] = {}
        self.hedge_puts: list = []
    
    def enter_deep_itm_call(self, layer: int, amount: float, current_price: float):
        """
        Enter Deep ITM Call position (Improvement D).
        Delta 0.7-0.8 provides stock-like exposure with unlimited upside.
        """
        call_result = self.executor.find_option_contract(
            target_delta=config.DEEP_ITM_CALL_DELTA, is_call=True,
            min_dte=config.SPREAD_DTE_MIN, max_dte=config.SPREAD_DTE_MAX,
            current_price=current_price
        )
        
        if not call_result:
            return
        
        call_contract, call_data = call_result
        mid_price = self._get_mid_price(call_data)
        
        if mid_price <= 0:
            self.algo.log(f"Warning: Deep ITM Call price not available for {call_contract}")
            return
        
        contract_cost = mid_price * 100
        num_contracts = max(1, int(amount / contract_cost))
        
        self.executor.add_contract_with_fee(call_contract)
        
        limit_price = round(mid_price * config.LIMIT_ORDER_BUFFER, 2)
        self.executor.place_limit_order_safe(call_contract, num_contracts, limit_price)
        
        self.active_layers[layer] = {
            "entry_date": self.algo.time,
            "entry_price": current_price,
            "position_type": "deep_itm_call",
            "long_call": call_contract,
            "short_call": None,
            "contracts": num_contracts,
            "amount": amount,
        }
        
        self.algo.log(f"Entered Deep ITM Call L{layer}: Buy {call_contract} @{limit_price:.2f}, Contracts: {num_contracts}")
    
    def enter_bull_call_spread(self, layer: int, amount: float, current_price: float):
        """Enter Bull Call Spread position."""
        long_result = self.executor.find_option_contract(
            target_delta=config.LONG_CALL_DELTA, is_call=True,
            min_dte=config.SPREAD_DTE_MIN, max_dte=config.SPREAD_DTE_MAX,
            current_price=current_price
        )
        
        short_result = self.executor.find_option_contract(
            target_delta=config.SHORT_CALL_DELTA, is_call=True,
            min_dte=config.SPREAD_DTE_MIN, max_dte=config.SPREAD_DTE_MAX,
            current_price=current_price
        )
        
        if not long_result or not short_result:
            return
        
        long_call, long_data = long_result
        short_call, short_data = short_result
        
        long_mid = self._get_mid_price(long_data)
        short_mid = self._get_mid_price(short_data)
        
        if long_mid <= 0:
            self.algo.log(f"Warning: Long call price not available for {long_call}")
            return
        
        spread_cost = (long_mid - short_mid) * 100
        if spread_cost <= 0:
            return
        
        num_contracts = max(1, int(amount / spread_cost))
        
        self.executor.add_contract_with_fee(long_call)
        self.executor.add_contract_with_fee(short_call)
        
        long_order_price = round(long_mid * config.LIMIT_ORDER_BUFFER, 2)
        short_order_price = round(short_mid * config.LIMIT_ORDER_SELL_BUFFER, 2)
        
        self.executor.place_limit_order_safe(long_call, num_contracts, long_order_price)
        self.executor.place_limit_order_safe(short_call, -num_contracts, short_order_price)
        
        self.active_layers[layer] = {
            "entry_date": self.algo.time,
            "entry_price": current_price,
            "position_type": "spread",
            "long_call": long_call,
            "short_call": short_call,
            "contracts": num_contracts,
            "amount": amount,
        }
        
        self.algo.log(f"Entered Bull Call Spread L{layer}: Buy {long_call} @{long_order_price:.2f}, Sell {short_call} @{short_order_price:.2f}")
    
    def enter_leaps(self, layer: int, amount: float, current_price: float):
        """Enter LEAPS position."""
        leaps_result = self.executor.find_option_contract(
            target_delta=config.LEAPS_DELTA, is_call=True,
            min_dte=config.LEAPS_DTE_MIN, max_dte=config.LEAPS_DTE_MAX,
            current_price=current_price,
            prefer_jan_june=True
        )
        
        if not leaps_result:
            return
        
        leaps_call, leaps_data = leaps_result
        mid_price = self._get_mid_price(leaps_data)
        
        if mid_price <= 0:
            self.algo.log(f"Warning: LEAPS price not available for {leaps_call}")
            return
        
        contract_cost = mid_price * 100
        num_contracts = max(1, int(amount / contract_cost))
        
        self.executor.add_contract_with_fee(leaps_call)
        
        limit_price = round(mid_price * config.LIMIT_ORDER_BUFFER, 2)
        self.executor.place_limit_order_safe(leaps_call, num_contracts, limit_price)
        
        self.active_layers[layer] = {
            "entry_date": self.algo.time,
            "entry_price": current_price,
            "position_type": "leaps",
            "long_call": leaps_call,
            "contracts": num_contracts,
            "amount": amount,
        }
        
        self.algo.log(f"Entered LEAPS L{layer}: Buy {leaps_call} @{limit_price:.2f}, Contracts: {num_contracts}")
    
    def buy_protective_put(self, amount: float, current_price: float):
        """Buy OTM put for hedging."""
        put_result = self.executor.find_option_contract(
            target_delta=config.PROTECTIVE_PUT_DELTA, is_call=False,
            min_dte=config.SPREAD_DTE_MIN, max_dte=config.SPREAD_DTE_MAX,
            current_price=current_price
        )
        
        if not put_result:
            return
        
        put_contract, put_data = put_result
        mid_price = self._get_mid_price(put_data)
        
        if mid_price <= 0:
            self.algo.log(f"Warning: Put price not available for {put_contract}")
            return
        
        num_contracts = max(1, int(amount / (mid_price * 100)))
        
        self.executor.add_contract_with_fee(put_contract)
        
        limit_price = round(mid_price * config.LIMIT_ORDER_BUFFER, 2)
        self.executor.place_limit_order_safe(put_contract, num_contracts, limit_price)
        
        self.hedge_puts.append({
            "entry_date": self.algo.time,
            "contract": put_contract,
            "contracts": num_contracts,
        })
        
        self.algo.log(f"Bought Protective Put: {put_contract} @{limit_price:.2f}, Contracts: {num_contracts}")
    
    def close_all_positions(self, reason: str):
        """Close all option positions and reset layers."""
        self.algo.log(f"Closing all positions - Reason: {reason}")
        
        for layer, position in list(self.active_layers.items()):
            self._close_position_contracts(position)
        
        self.active_layers.clear()
    
    def close_layer_position(self, layer: int, reason: str):
        """Close a specific layer's position."""
        if layer not in self.active_layers:
            return
        
        position = self.active_layers[layer]
        self.algo.log(f"Closing L{layer} - Reason: {reason}")
        
        self._close_position_contracts(position)
        del self.active_layers[layer]
    
    def _close_position_contracts(self, position: dict):
        """Close contracts in a position."""
        if position.get("long_call"):
            self.executor.liquidate_if_tradable(position["long_call"])
        if position.get("short_call"):
            self.executor.liquidate_if_tradable(position["short_call"])
    
    def check_roll_positions(self, current_price: float):
        """Check if any positions need to be rolled."""
        for layer, position in list(self.active_layers.items()):
            if "long_call" not in position:
                continue
            
            contract = self.algo.securities.get(position["long_call"])
            if not contract:
                continue
            
            dte = (contract.symbol.id.date - self.algo.time).days
            
            if position["position_type"] == "spread" and dte <= config.SPREAD_ROLL_DTE:
                self._roll_spread(layer, position, current_price)
            elif position["position_type"] == "deep_itm_call" and dte <= config.SPREAD_ROLL_DTE:
                self._roll_deep_itm_call(layer, position, current_price)
            elif position["position_type"] == "leaps" and dte <= config.LEAPS_ROLL_DTE:
                self._roll_leaps(layer, position, current_price)
    
    def check_rapid_price_move_exit(self, current_price: float, rsi, ath_dist_func):
        """Check for rapid price moves that require position adjustment."""
        for layer, position in list(self.active_layers.items()):
            if position["position_type"] == "deep_itm_call":
                self._check_deep_itm_price_move(layer, position, current_price, rsi, ath_dist_func)
            elif position["position_type"] == "spread":
                self._check_spread_price_move(layer, position, current_price, rsi, ath_dist_func)
    
    def _check_deep_itm_price_move(self, layer: int, position: dict, current_price: float,
                                   rsi, ath_dist_func):
        """Check Deep ITM Call for rapid price moves."""
        long_call = position.get("long_call")
        if not long_call:
            return
        
        long_strike = long_call.id.strike_price
        contract = self.algo.securities.get(long_call)
        if not contract:
            return
        
        dte = (contract.symbol.id.date - self.algo.time).days
        
        if current_price < long_strike:
            self.algo.log(f"RAPID DROP Deep ITM L{layer}: Price {current_price:.2f} < Strike {long_strike:.2f}")
            
            if dte < 15:
                self.close_layer_position(layer, f"Deep ITM Stop Loss")
            else:
                rsi_val = rsi.current.value
                ath_dist = ath_dist_func(current_price)
                
                for leaps_layer in [3, 4, 5]:
                    if leaps_layer not in self.active_layers:
                        if ath_dist <= config.LAYER_CONFIG[leaps_layer]["dd_threshold"] and rsi_val <= config.RSI_UPTREND_THRESHOLD:
                            self.close_layer_position(layer, "Closing Deep ITM for LEAPS opportunity")
                            break
    
    def _check_spread_price_move(self, layer: int, position: dict, current_price: float,
                                 rsi, ath_dist_func):
        """Check spread for rapid price moves."""
        long_call = position.get("long_call")
        short_call = position.get("short_call")
        
        if not long_call or not short_call:
            return
        
        long_strike = long_call.id.strike_price
        short_strike = short_call.id.strike_price
        
        contract = self.algo.securities.get(long_call)
        if not contract:
            return
        
        dte = (contract.symbol.id.date - self.algo.time).days
        
        if current_price > short_strike:
            self.algo.log(f"RAPID RALLY L{layer}: Price {current_price:.2f} > Short Strike {short_strike:.2f}")
            self.close_layer_position(layer, f"Stock Rally")
            if dte > 14:
                self.enter_bull_call_spread(layer, position["amount"], current_price)
        elif current_price < long_strike:
            self.algo.log(f"RAPID DROP L{layer}: Price {current_price:.2f} < Long Strike {long_strike:.2f}")
            
            if dte < 15:
                self.close_layer_position(layer, f"Stock Drop Stop Loss")
            else:
                rsi_val = rsi.current.value
                ath_dist = ath_dist_func(current_price)
                
                for leaps_layer in [3, 4, 5]:
                    if leaps_layer not in self.active_layers:
                        if ath_dist <= config.LAYER_CONFIG[leaps_layer]["dd_threshold"] and rsi_val <= config.RSI_DOWNTREND_THRESHOLD:
                            self.close_layer_position(layer, "Closing spread for LEAPS opportunity")
                            break
    
    def _roll_spread(self, layer: int, position: dict, current_price: float):
        """Roll a bull call spread to new expiration."""
        self.algo.log(f"Rolling spread for L{layer}")
        self._close_position_contracts(position)
        
        if self._should_roll(position, current_price):
            self.enter_bull_call_spread(layer, position["amount"], current_price)
        else:
            del self.active_layers[layer]
    
    def _roll_deep_itm_call(self, layer: int, position: dict, current_price: float):
        """Roll Deep ITM Call to new expiration."""
        self.algo.log(f"Rolling Deep ITM Call for L{layer}")
        self._close_position_contracts(position)
        
        if self._should_roll(position, current_price):
            self.enter_deep_itm_call(layer, position["amount"], current_price)
        else:
            del self.active_layers[layer]
    
    def _roll_leaps(self, layer: int, position: dict, current_price: float):
        """Roll LEAPS to new expiration."""
        self.algo.log(f"Rolling LEAPS for L{layer}")
        self._close_position_contracts(position)
        self.enter_leaps(layer, position["amount"], current_price)
    
    def _should_roll(self, position: dict, current_price: float) -> bool:
        """Check if position should be rolled or closed."""
        entry_price = position["entry_price"]
        price_change_pct = (current_price - entry_price) / entry_price
        
        if price_change_pct < config.PRICE_DROP_STOP_LOSS:
            self.algo.log(f"Price dropped {price_change_pct:.2%}, not rolling")
            return False
        return True
    
    def _get_mid_price(self, data: dict) -> float:
        """Calculate mid price from bid/ask."""
        bid = data.get("bid", 0)
        ask = data.get("ask", 0)
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return data.get("last", 0)
