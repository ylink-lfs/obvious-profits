# Models for QQQ Boost Options Strategy
from AlgorithmImports import *


class CustomOptionFeeModel(FeeModel):
    """Custom fee model for options trading."""
    
    def __init__(self, commission_per_contract: float = 0.45, 
                 minimum_commission: float = 1.49,
                 platform_fee_per_order: float = 0.54):
        self.commission_per_contract = commission_per_contract
        self.minimum_commission = minimum_commission
        self.platform_fee_per_order = platform_fee_per_order
    
    def get_order_fee(self, parameters: OrderFeeParameters) -> OrderFee:
        """Calculate the fee for an option order."""
        order = parameters.order
        
        # Get the number of contracts (absolute value)
        quantity = abs(order.quantity)
        
        # Calculate commission: $0.45 per contract, minimum $1.49
        commission = max(self.minimum_commission, quantity * self.commission_per_contract)
        
        # Add platform fee: $0.54 per order
        total_fee = commission + self.platform_fee_per_order
        
        return OrderFee(CashAmount(total_fee, "USD"))


class LayerPosition:
    """Represents a position in a specific layer."""
    
    def __init__(self, layer: int, entry_date, entry_price: float,
                 position_type: str, long_call, short_call=None,
                 contracts: int = 0, amount: float = 0):
        self.layer = layer
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.position_type = position_type  # "spread", "deep_itm_call", "leaps"
        self.long_call = long_call
        self.short_call = short_call
        self.contracts = contracts
        self.amount = amount
    
    def to_dict(self) -> dict:
        return {
            "entry_date": self.entry_date,
            "entry_price": self.entry_price,
            "position_type": self.position_type,
            "long_call": self.long_call,
            "short_call": self.short_call,
            "contracts": self.contracts,
            "amount": self.amount,
        }
    
    @classmethod
    def from_dict(cls, layer: int, data: dict):
        return cls(
            layer=layer,
            entry_date=data.get("entry_date"),
            entry_price=data.get("entry_price", 0),
            position_type=data.get("position_type", ""),
            long_call=data.get("long_call"),
            short_call=data.get("short_call"),
            contracts=data.get("contracts", 0),
            amount=data.get("amount", 0),
        )


class PendingOrder:
    """Represents a pending order waiting for data."""
    
    def __init__(self, symbol, quantity: int, limit_price: float, created_date):
        self.symbol = symbol
        self.quantity = quantity
        self.limit_price = limit_price
        self.created_date = created_date
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "created_date": self.created_date,
        }


class HedgePut:
    """Represents a protective put position."""
    
    def __init__(self, entry_date, contract, contracts: int):
        self.entry_date = entry_date
        self.contract = contract
        self.contracts = contracts
    
    def to_dict(self) -> dict:
        return {
            "entry_date": self.entry_date,
            "contract": self.contract,
            "contracts": self.contracts,
        }
