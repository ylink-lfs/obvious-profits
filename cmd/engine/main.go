package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"time"

	"obvious-profits/config"
	"obvious-profits/core"
	"obvious-profits/execution"
	"obvious-profits/feed"
	"obvious-profits/memory"
	"obvious-profits/pricing"
	"obvious-profits/risk"
	"obvious-profits/strategy"
)

func main() {
	cfg, err := config.Load("config.yaml")
	if err != nil {
		slog.Error("load config", "error", err)
		os.Exit(1)
	}

	if len(cfg.Symbols) == 0 {
		slog.Error("no symbols configured")
		os.Exit(1)
	}
	sym := cfg.Symbols[0]

	// Shared state
	priceState := &core.PriceState{}
	theoFundState := &core.TheoreticalFundingState{}
	book := memory.NewL2Book()

	// Channels
	binanceCh := make(chan core.Ticker, 64)
	gateCh := make(chan core.Ticker, 64)
	fundingCh := make(chan core.TheoreticalFundingRate, 16)
	alertCh := make(chan core.SpreadSnapshot, 16)
	triggerCh := make(chan core.TriggerSignal, 4)

	// Modules
	binanceAsk := &core.AtomicPrice{}
	binanceTickerWS := feed.NewBinanceTickerWS(cfg.Binance.FuturesWSBase, sym.BinanceSymbol, binanceCh, binanceAsk)
	gateTickerWS := feed.NewGateTickerWS(cfg.Gate.FuturesWSBase, sym.GateSymbol, gateCh,
		&priceState.GateIndexPrice, &priceState.WsIndicativeFundingRate)

	// Contract cache: fetches all Gate USDT contracts periodically
	refreshMin := cfg.Gate.ContractCacheRefreshMinutes
	if refreshMin <= 0 {
		refreshMin = 1
	}
	contractCache := feed.NewContractCache(cfg.Gate.FuturesAPIBase, time.Duration(refreshMin)*time.Minute)

	// Theoretical funding rate calculator (replaces old REST polling)
	theoFundCalc := pricing.NewTheoreticalFundingCalculator(
		sym.GateSymbol, book, &priceState.GateIndexPrice, contractCache, fundingCh,
	)

	spreadAlert := strategy.NewSpreadAlert(cfg.Alert, binanceCh, gateCh, fundingCh, alertCh, priceState, theoFundState)
	gateKeeper := risk.NewGateKeeper(cfg.Risk)
	impactCost := risk.NewImpactCost(cfg.Risk, book)
	tracker := execution.NewLatencyTracker(sym.GateSymbol)
	gateAPI := execution.NewGateAPI(cfg.Gate, tracker)
	ringBuf := strategy.NewRingBuffer(30)

	// Pricing modules: orderbook sync, VWAP, spread calculator
	gateOB := feed.NewGateOrderbookWS(cfg.Gate.FuturesWSBase, sym.GateSymbol, book)
	vwapCalc := pricing.NewVWAPCalculator(book)
	spreadCalc := pricing.NewSpreadCalculator(cfg.Pricing, binanceAsk, vwapCalc)

	cooldown := time.Duration(cfg.Cooldown) * time.Second
	stateMachine := strategy.NewStateMachine(
		sym.GateSymbol, cooldown, alertCh,
		gateKeeper.Check, ringBuf, triggerCh,
	)

	// Context with graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt)
	go func() {
		<-interrupt
		slog.Info("[Engine] shutting down...")
		cancel()
	}()

	// Launch goroutines
	go func() {
		if err := contractCache.Run(ctx); err != nil {
			slog.Error("[Engine] contract cache error", "error", err)
		}
	}()
	go func() {
		if err := binanceTickerWS.Run(ctx); err != nil {
			slog.Error("[Engine] binance ticker ws error", "error", err)
		}
	}()
	go func() {
		if err := gateTickerWS.Run(ctx); err != nil {
			slog.Error("[Engine] gate ticker ws error", "error", err)
		}
	}()
	go func() {
		if err := gateOB.Run(ctx); err != nil {
			slog.Error("[Engine] gate orderbook ws error", "error", err)
		}
	}()
	go func() {
		if err := theoFundCalc.Run(ctx); err != nil {
			slog.Error("[Engine] theoretical funding calc error", "error", err)
		}
	}()
	go func() {
		if err := spreadAlert.Run(ctx); err != nil {
			slog.Error("[Engine] spread alert error", "error", err)
		}
	}()
	go func() {
		if err := stateMachine.Run(ctx); err != nil {
			slog.Error("[Engine] state machine error", "error", err)
		}
	}()

	// Execution loop
	slog.Info("[Engine] started", "binance", sym.BinanceSymbol, "gate", sym.GateSymbol)
	for {
		select {
		case <-ctx.Done():
			slog.Info("[Engine] stopped")
			return
		case sig := <-triggerCh:
			tracker.Reset()
			tracker.Mark("trigger_received")

			// Compute VWAP-based actionable spread before execution
			if sr, err := spreadCalc.Calculate(); err != nil {
				slog.Error("[Engine] spread calc", "error", err)
			} else {
				slog.Info("[Engine] actionable spread",
					"actionable_pct", sr.ActionableSpreadPct,
					"raw_pct", sr.RawSpreadPct)
			}
			tracker.Mark("spread_calculated")

			var impact risk.ImpactResult
			if sig.Direction == core.TriggerShort {
				impact = impactCost.EstimateSell(cfg.Risk.MaxPositionUSD)
			} else {
				impact = impactCost.EstimateBuy(cfg.Risk.MaxPositionUSD)
			}
			tracker.Mark("impact_checked")

			if !impact.Feasible {
				slog.Warn("[Engine] execution rejected", "reason", impact.Reason)
				continue
			}

			side := execution.OrderSell
			price := impact.AvgFillPrice
			if sig.Direction == core.TriggerLong {
				side = execution.OrderBuy
			}

			req := execution.OrderRequest{
				Symbol:  sig.Symbol,
				Side:    side,
				Type:    execution.OrderFOK,
				Price:   price,
				SizeUSD: cfg.Risk.MaxPositionUSD,
				Signal:  sig,
				Impact:  impact,
			}

			result := gateAPI.PlaceOrder(ctx, req)
			tracker.Mark("order_complete")

			slog.Info("[Engine] order result",
				"success", result.Success, "id", result.OrderID, "error", result.Error)
			slog.Info(tracker.Summary())
		}
	}
}
