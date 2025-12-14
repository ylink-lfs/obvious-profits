# Squeeze Entry Options Strategy - Main Algorithm
# region imports
from AlgorithmImports import *
from datetime import timedelta
from typing import Dict, List, Optional

import config
from models import CustomOptionFeeModel, SymbolData, EntryCandidate
from signals import SignalGenerator
from execution import OrderExecutor
from positions import PositionManager
# endregion


class SqueezeEntryOptionsStrategy(QCAlgorithm):
    """
    Squeeze Entry Options Strategy
    
    Entry Signals:
    1. Squeeze Signal (OR):
       - BB width < 20th percentile of 90-day BB width
       - Close within 2% of MA20 AND 5-day ATR < 20-day ATR
    2. IV Percentile < 30%
    3. Trend Background (AND):
       - Close > MA200
       - 40 <= RSI(14) <= 55
    
    Entry Structure:
    - Buy 2-3 OTM calls (delta <= 0.25)
    - Sell 1 ITM/ATM call (delta >= 0.60)
    - Premium received >= Premium paid
    
    Exit Signals:
    1. Price Rally: Open > max profit price AND (RSI declining OR high > upper BB)
    2. Price Drop: Price < 0.95 * short strike
    3. DTE <= 20
    
    Symbol Selection:
    - If multiple symbols trigger, select one with lowest (IV Percentile * BB Width)
    """
    
    def initialize(self):
        # Backtest period
        self.set_start_date(*config.START_DATE)
        self.set_end_date(*config.END_DATE)
        self.set_cash(config.INITIAL_CAPITAL)
        self.initial_capital = config.INITIAL_CAPITAL
        
        # Symbol data storage
        self.symbol_data: Dict[str, SymbolData] = {}
        
        # Custom fee model (must be created before _initialize_symbols)
        self.custom_fee_model = CustomOptionFeeModel(
            config.COMMISSION_PER_CONTRACT,
            config.MINIMUM_COMMISSION,
            config.PLATFORM_FEE_PER_ORDER
        )
        
        # Add equities and options for each symbol in the pool
        self._initialize_symbols()
        
        # Initialize components
        self.signal_gen = SignalGenerator(self)
        self.executor = OrderExecutor(self, self.custom_fee_model)
        self.position_mgr = PositionManager(self, self.executor)
        
        # Schedule events
        self._schedule_events()
        
        # Warm up period
        self.set_warm_up(config.WARM_UP_PERIOD, Resolution.DAILY)
    
    def _initialize_symbols(self):
        """Initialize all symbols in the pool with indicators."""
        for symbol_str in config.SYMBOL_POOL:
            # Add equity
            equity = self.add_equity(symbol_str, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.RAW)
            
            # Add options
            option = self.add_option(symbol_str, Resolution.DAILY)
            option.set_filter(self._option_filter)
            
            # Create symbol data object
            data = SymbolData(symbol=symbol_str)
            data.equity_symbol = equity.symbol
            data.option_symbol = option.symbol
            
            # Initialize indicators
            data.rsi = self.rsi(equity.symbol, config.RSI_PERIOD, 
                               MovingAverageType.WILDERS, Resolution.DAILY)
            data.sma20 = self.sma(equity.symbol, config.BB_PERIOD, Resolution.DAILY)
            data.sma200 = self.sma(equity.symbol, config.MA200_PERIOD, Resolution.DAILY)
            data.bb = self.bb(equity.symbol, config.BB_PERIOD, config.BB_STD, 
                             MovingAverageType.SIMPLE, Resolution.DAILY)
            data.atr_short = self.atr(equity.symbol, config.ATR_SHORT_PERIOD, 
                                      MovingAverageType.SIMPLE, Resolution.DAILY)
            data.atr_long = self.atr(equity.symbol, config.ATR_LONG_PERIOD,
                                     MovingAverageType.SIMPLE, Resolution.DAILY)
            
            # Apply custom fee model to options
            option.set_fee_model(self.custom_fee_model)
            
            self.symbol_data[symbol_str] = data
            self.log(f"Initialized {symbol_str} with indicators")
    
    def _option_filter(self, universe: OptionFilterUniverse) -> OptionFilterUniverse:
        """Filter options to relevant strikes and expirations."""
        return universe.strikes(*config.STRIKE_RANGE).expiration(*config.EXPIRATION_RANGE)
    
    def _schedule_events(self):
        """Schedule all daily events."""
        # Record previous day data before market open
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.at(9, 25),
            self._record_previous_day_data
        )
        
        # Main strategy check after market open
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(config.SYMBOL_POOL[0], 30),
            self._daily_strategy_check
        )
        
        # Process pending orders
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(config.SYMBOL_POOL[0], 60),
            self.executor.process_pending_orders
        )
        
        # Update BB width and IV history at end of day
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(config.SYMBOL_POOL[0], 5),
            self._update_daily_history
        )
    
    def _record_previous_day_data(self):
        """Record previous day's close, high, and RSI for all symbols."""
        if self.is_warming_up:
            return
        
        for symbol_str, data in self.symbol_data.items():
            if not self.securities.contains_key(data.equity_symbol):
                continue
            
            security = self.securities[data.equity_symbol]
            data.prev_close = security.close
            data.prev_high = security.high
            
            if data.rsi is not None and data.rsi.is_ready:
                data.prev_rsi = data.rsi.current.value
    
    def _update_daily_history(self):
        """Update BB width and IV history for all symbols at end of day."""
        if self.is_warming_up:
            return
        
        for symbol_str, data in self.symbol_data.items():
            # Update BB width history
            bb_width = data.get_bb_width()
            if bb_width > 0:
                data.bb_width_history.append(bb_width)
                # Keep only last 100 days to save memory
                if len(data.bb_width_history) > 100:
                    data.bb_width_history = data.bb_width_history[-100:]
            
            # Update IV history (IV is already updated during strategy check)
            # This ensures IV history is captured even on days without signals
    
    def _update_iv_from_chain(self, symbol_str: str, data: SymbolData):
        """
        Update IV from option chain and calculate IV Percentile.
        
        IV Percentile = Percentage of days in past 52 weeks where IV was lower than current IV
        
        Uses ATM option IV as a proxy for overall IV.
        """
        if not self.securities.contains_key(data.equity_symbol):
            return
        
        current_price = self.securities[data.equity_symbol].price
        if current_price <= 0:
            return
        
        # Get option chain
        chain = self.option_chain(data.option_symbol)
        if not chain:
            return
        
        # Find ATM options to get representative IV
        # Look for calls with strike closest to current price
        atm_iv = self._get_atm_iv_from_chain(chain, current_price)
        
        if atm_iv is not None and atm_iv > 0:
            # Update IV history and recalculate IV Percentile
            data.update_iv(atm_iv)
            self.log(f"{symbol_str} IV: {atm_iv:.4f}, IV Percentile: {data.iv_percentile:.2%}, "
                    f"History: {len(data.iv_history)} days")
    
    def _get_atm_iv_from_chain(self, chain, current_price: float) -> Optional[float]:
        """
        Get ATM implied volatility from option chain.
        
        Uses the average IV of ATM call and put options.
        """
        if not chain:
            return None
        
        # Filter for options with reasonable DTE
        min_dte = config.IV_ATM_DTE_MIN
        max_dte = config.IV_ATM_DTE_MAX
        
        calls = []
        puts = []
        
        for contract in chain:
            dte = (contract.expiry - self.time).days
            if not (min_dte <= dte <= max_dte):
                continue
            
            # Get IV directly from contract (QuantConnect stores IV on the contract itself)
            iv = None
            if hasattr(contract, 'implied_volatility'):
                iv = contract.implied_volatility
            
            if iv is None or iv <= 0:
                continue
            
            strike_distance = abs(contract.strike - current_price) / current_price
            
            # Only consider near-ATM options (within configured range of current price)
            if strike_distance > config.IV_ATM_STRIKE_RANGE:
                continue
            
            if contract.right == OptionRight.CALL:
                calls.append((contract, iv, strike_distance))
            else:
                puts.append((contract, iv, strike_distance))
        
        # Get IV from closest ATM options
        iv_values = []
        
        if calls:
            # Sort by strike distance, get closest
            calls.sort(key=lambda x: x[2])
            iv_values.append(calls[0][1])
        
        if puts:
            # Sort by strike distance, get closest
            puts.sort(key=lambda x: x[2])
            iv_values.append(puts[0][1])
        
        if iv_values:
            return sum(iv_values) / len(iv_values)
        
        return None
    
    def _daily_strategy_check(self):
        """Main daily strategy logic."""
        if self.is_warming_up:
            return
        
        # Update IV and IV Percentile for all symbols
        for symbol_str, data in self.symbol_data.items():
            self._update_iv_from_chain(symbol_str, data)
        
        # Check exit signals for existing positions
        self._check_exit_signals()
        
        # Check entry signals if we have capacity
        self._check_entry_signals()
    
    def _check_exit_signals(self):
        """Check exit signals for all active positions."""
        for symbol_str in self.position_mgr.get_active_symbols():
            if symbol_str not in self.symbol_data:
                continue
            
            data = self.symbol_data[symbol_str]
            position = self.position_mgr.get_position(symbol_str)
            
            if position is None:
                continue
            
            # Get current prices
            if not self.securities.contains_key(data.equity_symbol):
                continue
            
            security = self.securities[data.equity_symbol]
            current_price = security.price
            current_open = security.open
            current_high = security.high
            
            # Check all exit signals
            should_exit, reason = self.signal_gen.check_exit_signals(
                position, data, current_price, current_open, current_high, self.time
            )
            
            if should_exit:
                self.position_mgr.close_position(symbol_str, reason)
    
    def _check_entry_signals(self):
        """Check entry signals and enter positions if conditions are met."""
        # Skip if we already have a position (one position at a time)
        if self.position_mgr.get_position_count() > 0:
            return
        
        # Get entry candidates
        candidates = self.signal_gen.get_entry_candidates(self.symbol_data)
        
        if not candidates:
            return
        
        # Calculate available capital
        max_position_value = self.portfolio.total_portfolio_value * config.MAX_POSITION_PCT
        available_capital = min(self.portfolio.cash, max_position_value)
        
        # Try to enter position with the best candidate
        for candidate in candidates:
            symbol_str = candidate.symbol
            data = candidate.symbol_data
            
            if not self.securities.contains_key(data.equity_symbol):
                continue
            
            current_price = self.securities[data.equity_symbol].price
            
            self.log(f"Attempting entry for {symbol_str}: "
                    f"Price={current_price:.2f}, RSI={data.rsi.current.value:.2f}, "
                    f"IV Percentile={data.iv_percentile:.2%}, BB Width Percentile={data.get_bb_width_percentile():.1f}%")
            
            success = self.position_mgr.enter_squeeze_spread(
                symbol_str, data, current_price, available_capital
            )
            
            if success:
                # Only enter one position at a time
                break
    
    def on_data(self, data: Slice):
        """Handle incoming data."""
        pass
    
    def on_order_event(self, order_event: OrderEvent):
        """Handle order events."""
        if order_event.status == OrderStatus.FILLED:
            self.log(f"Order Filled: {order_event.symbol}, "
                    f"Qty: {order_event.fill_quantity}, "
                    f"Price: {order_event.fill_price:.2f}")
    
    def on_end_of_algorithm(self):
        """Called at the end of the backtest."""
        self.log("=" * 50)
        self.log("SQUEEZE ENTRY STRATEGY BACKTEST COMPLETE")
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Total Return: {(self.portfolio.total_portfolio_value / self.initial_capital - 1) * 100:.2f}%")
        self.log(f"Active Positions: {self.position_mgr.get_position_count()}")
        self.log("=" * 50)
