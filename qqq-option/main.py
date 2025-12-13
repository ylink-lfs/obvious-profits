# QQQ Boost Options Strategy - Main Algorithm
# region imports
from AlgorithmImports import *
from datetime import timedelta
from typing import Dict, List, Optional

import config
from models import CustomOptionFeeModel
from signals import SignalGenerator
from execution import OrderExecutor
from positions import PositionManager
# endregion


class QQQBoostOptionsStrategy(QCAlgorithm):
    def initialize(self):
        # Backtest period
        self.set_start_date(*config.START_DATE)
        self.set_end_date(*config.END_DATE)
        self.set_cash(config.INITIAL_CAPITAL)
        self.initial_capital = config.INITIAL_CAPITAL

        # Add QQQ equity
        self.qqq = self.add_equity("QQQ", Resolution.DAILY)
        self.qqq.set_data_normalization_mode(DataNormalizationMode.RAW)
        self.qqq_symbol = self.qqq.symbol
        
        # Add options with custom fee model
        option = self.add_option("QQQ", Resolution.DAILY)
        option.set_filter(self._option_filter)
        self.option_symbol = option.symbol
        
        # Apply custom fee model
        self.custom_fee_model = CustomOptionFeeModel(
            config.COMMISSION_PER_CONTRACT, 
            config.MINIMUM_COMMISSION, 
            config.PLATFORM_FEE_PER_ORDER
        )
        option.set_fee_model(self.custom_fee_model)
        
        # Indicators
        self._rsi = self.rsi(self.qqq_symbol, config.RSI_PERIOD, MovingAverageType.WILDERS, Resolution.DAILY)
        self._sma20 = self.sma(self.qqq_symbol, 20, Resolution.DAILY)
        self._sma50 = self.sma(self.qqq_symbol, 50, Resolution.DAILY)
        self._sma200 = self.sma(self.qqq_symbol, 200, Resolution.DAILY)
        
        # Core + Satellite state
        self.core_position_initialized = False
        
        # ATH tracking
        self.all_time_high = 0
        self.previous_day_close = 0
        
        # Initialize components
        self.signal_gen = SignalGenerator(self)
        self.executor = OrderExecutor(self, self.custom_fee_model)
        self.position_mgr = PositionManager(self, self.executor)
        
        # Schedule events
        self._schedule_events()
        
        # Warm up period
        self.set_warm_up(config.WARM_UP_PERIOD, Resolution.DAILY)

    def _option_filter(self, universe: OptionFilterUniverse) -> OptionFilterUniverse:
        """Filter options to relevant strikes and expirations."""
        return universe.strikes(*config.STRIKE_RANGE).expiration(*config.EXPIRATION_RANGE)

    def _schedule_events(self):
        """Schedule all daily events."""
        self.schedule.on(
            self.date_rules.every_day("QQQ"),
            self.time_rules.after_market_open("QQQ", 5),
            self._initialize_core_position
        )
        
        self.schedule.on(
            self.date_rules.every_day("QQQ"),
            self.time_rules.after_market_open("QQQ", 30),
            self._daily_strategy_check
        )
        
        self.schedule.on(
            self.date_rules.every_day("QQQ"),
            self.time_rules.after_market_open("QQQ", 60),
            self.executor.process_pending_orders
        )
        
        self.schedule.on(
            self.date_rules.every_day("QQQ"),
            self.time_rules.before_market_close("QQQ", 1),
            self._record_close_price
        )

    def _initialize_core_position(self):
        """Initialize core QQQ position (Improvement A: Core + Satellite)."""
        if self.is_warming_up or self.core_position_initialized:
            return
        
        core_value = self.portfolio.total_portfolio_value * config.CORE_ALLOCATION
        current_price = self.securities[self.qqq_symbol].price
        
        if current_price > 0:
            shares = int(core_value / current_price)
            if shares > 0:
                self.market_order(self.qqq_symbol, shares)
                self.core_position_initialized = True
                self.log(f"Initialized Core Position: {shares} shares of QQQ @ ${current_price:.2f}")

    def _record_close_price(self):
        """Record the close price at end of day."""
        if self.is_warming_up:
            return
        
        close_price = self.securities[self.qqq_symbol].price
        self.previous_day_close = close_price
        
        if close_price > self.all_time_high:
            self.all_time_high = close_price

    def _daily_strategy_check(self):
        """Main daily strategy logic."""
        if self.is_warming_up or not self._rsi.is_ready:
            return
        
        signal_price = self.previous_day_close if self.previous_day_close > 0 else self.securities[self.qqq_symbol].price
        current_price = self.securities[self.qqq_symbol].price
        base_amount = self.portfolio.total_portfolio_value * config.BASE_AMOUNT_PCT
        
        rsi = self._rsi.current.value
        ath_dist = self.signal_gen.calculate_ath_dist(signal_price, self.all_time_high)
        
        self.log(f"Date: {self.time.date()}, Price: {current_price:.2f}, RSI: {rsi:.2f}, ATH_Dist: {ath_dist:.2%}, Layers: {list(self.position_mgr.active_layers.keys())}")
        
        # Check for rapid price move exit
        self.position_mgr.check_rapid_price_move_exit(
            current_price, self._rsi,
            lambda p: self.signal_gen.calculate_ath_dist(p, self.all_time_high)
        )
        
        # Check exit conditions
        if self.signal_gen.check_exit_signal(rsi, ath_dist) and len(self.position_mgr.active_layers) > 0:
            self.position_mgr.close_all_positions(f"Exit Signal - RSI: {rsi:.2f}, ATH_Dist: {ath_dist:.2%}")
            return
        
        # Check hedge signal
        if self.signal_gen.check_hedge_signal(current_price, self._sma20) and len(self.position_mgr.active_layers) > 0:
            put_amount = self.portfolio.total_portfolio_value * config.HEDGE_AMOUNT_PCT
            self.position_mgr.buy_protective_put(put_amount, current_price)
            self.log(f"Hedge Signal: Price {current_price:.2f} below SMA20")
        
        # Check for new entry signals
        triggered_layer = self.signal_gen.get_triggered_layer(
            ath_dist, rsi, current_price,
            self._sma200, self._sma20, self._sma50,
            self.position_mgr.active_layers
        )
        
        if triggered_layer:
            layer_config = config.LAYER_CONFIG[triggered_layer]
            amount = base_amount * layer_config["coefficient"]
            
            # Capital constraints
            satellite_capital = self.portfolio.total_portfolio_value * config.SATELLITE_ALLOCATION
            available_capital = min(self.portfolio.cash, satellite_capital)
            max_position = self.portfolio.total_portfolio_value * config.MAX_POSITION_PCT
            amount = min(amount, max_position, available_capital * 0.5)
            
            if amount > 0:
                self.log(f"Entry Signal L{triggered_layer} - RSI: {rsi:.2f}, ATH_Dist: {ath_dist:.2%}")
                
                if layer_config["position_type"] == "spread":
                    self.position_mgr.enter_deep_itm_call(triggered_layer, amount, current_price)
                else:
                    self.position_mgr.enter_leaps(triggered_layer, amount, current_price)
        
        # Check for roll opportunities
        self.position_mgr.check_roll_positions(current_price)
        
        # Check for deep drawdown
        if self.signal_gen.check_deep_drawdown(ath_dist, self.position_mgr.active_layers):
            self.log(f"Deep Drawdown Signal - ATH_Dist: {ath_dist:.2%}")
            emergency_amount = base_amount * config.LAYER_CONFIG[5]["coefficient"]
            self.position_mgr.enter_leaps(5, emergency_amount, current_price)

    def on_data(self, data: Slice):
        pass

    def on_order_event(self, order_event: OrderEvent):
        if order_event.status == OrderStatus.FILLED:
            self.log(f"Order Filled: {order_event.symbol}, Qty: {order_event.fill_quantity}, Price: {order_event.fill_price}")

    def on_end_of_algorithm(self):
        self.log("=" * 50)
        self.log("STRATEGY BACKTEST COMPLETE")
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Total Return: {(self.portfolio.total_portfolio_value / self.initial_capital - 1) * 100:.2f}%")
        self.log("=" * 50)
