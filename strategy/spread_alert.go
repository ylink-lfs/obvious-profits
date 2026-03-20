package strategy

import (
	"context"
	"log/slog"
	"time"

	"github.com/govalues/decimal"

	"obvious-profits/config"
	"obvious-profits/core"
)

// SpreadAlert monitors Binance and Gate ticker streams, computes
// clock-aligned spread, checks funding ESI extremes, and emits
// SpreadSnapshot alerts when thresholds are breached.
type SpreadAlert struct {
	cfg        config.AlertConfig
	binanceCh  <-chan core.Ticker
	gateCh     <-chan core.Ticker
	fundingCh  <-chan core.FundingSignal
	alertCh    chan<- core.SpreadSnapshot
	priceState *core.PriceState
	fundState  *core.FundingSignalState
}

func NewSpreadAlert(
	cfg config.AlertConfig,
	binanceCh <-chan core.Ticker,
	gateCh <-chan core.Ticker,
	fundingCh <-chan core.FundingSignal,
	alertCh chan<- core.SpreadSnapshot,
	priceState *core.PriceState,
	fundState *core.FundingSignalState,
) *SpreadAlert {
	return &SpreadAlert{
		cfg:        cfg,
		binanceCh:  binanceCh,
		gateCh:     gateCh,
		fundingCh:  fundingCh,
		alertCh:    alertCh,
		priceState: priceState,
		fundState:  fundState,
	}
}

func (s *SpreadAlert) Run(ctx context.Context) error {
	slog.Info("[SpreadAlert] started")
	for {
		select {
		case <-ctx.Done():
			return nil
		case t := <-s.binanceCh:
			s.priceState.BinanceAsk.Store(t.Ask)
			s.priceState.BinanceBid.Store(t.Bid)
			s.checkAndEmit(ctx, t.Symbol)
		case t := <-s.gateCh:
			s.priceState.GateAsk.Store(t.Ask)
			s.priceState.GateBid.Store(t.Bid)
			s.checkAndEmit(ctx, t.Symbol)
		case sig := <-s.fundingCh:
			s.fundState.Store(sig)
			if sig.ESI.Cmp(s.cfg.ESIThreshold) >= 0 {
				slog.Warn("[SpreadAlert] extreme funding ESI",
					"esi", sig.ESI, "rpr", sig.RPR, "sr", sig.SR,
					"funding_rate", sig.FundingRate, "kappa", sig.Kappa)
			}
		}
	}
}

func (s *SpreadAlert) checkAndEmit(ctx context.Context, symbol string) {
	binanceAsk := s.priceState.BinanceAsk.Load()
	gateBid := s.priceState.GateBid.Load()
	if !binanceAsk.IsPos() || !gateBid.IsPos() {
		return
	}

	diff, _ := gateBid.Sub(binanceAsk)
	spreadPct, _ := diff.Quo(binanceAsk)
	spreadPct, _ = spreadPct.Mul(decimal.Hundred)
	fundSig := s.fundState.Load()

	if spreadPct.Abs().Cmp(s.cfg.SpreadPctThreshold) < 0 && fundSig.ESI.Cmp(s.cfg.ESIThreshold) < 0 {
		return
	}

	snap := core.SpreadSnapshot{
		Symbol:      symbol,
		BinanceAsk:  binanceAsk,
		GateBid:     gateBid,
		SpreadPct:   spreadPct,
		FundingRate: fundSig.FundingRate,
		Ts:          time.Now(),
	}
	slog.Warn("[SpreadAlert] ALERT", "spread_pct", spreadPct, "funding_rate", fundSig.FundingRate, "esi", fundSig.ESI)

	select {
	case s.alertCh <- snap:
	case <-ctx.Done():
	}
}
