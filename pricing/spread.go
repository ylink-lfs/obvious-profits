package pricing

import (
	"fmt"
	"log/slog"
	"time"

	"github.com/govalues/decimal"

	"obvious-profits/config"
	"obvious-profits/core"
)

// SpreadResult holds both raw and friction-adjusted spread values.
type SpreadResult struct {
	RawGateVWAP         decimal.Decimal
	AdjustedGateVWAP    decimal.Decimal
	RawBinanceAsk       decimal.Decimal
	AdjustedBinanceAsk  decimal.Decimal
	RawSpreadPct        decimal.Decimal
	ActionableSpreadPct decimal.Decimal
	Ts                  time.Time
}

// SpreadCalculator computes the actionable spread between Gate bid VWAP
// and Binance ask, incorporating slippage penalties and taker fees.
//
// Formula:
//
//	ActionableSpread = (Gate_VWAP_adjusted - Binance_Ask_adjusted) / Binance_Ask_adjusted
//
// Gate side:   VWAP * (1 - S_small) * (1 - gate_taker_fee)
// Binance side (Path A, naked_short):  Ask * (1 - momentum_drift)
// Binance side (Path B, hedged):       Ask * (1 + S_binance) * (1 + binance_taker_fee)
type SpreadCalculator struct {
	cfg        config.PricingConfig
	binanceAsk *core.AtomicPrice
	vwap       *VWAPCalculator
}

func NewSpreadCalculator(
	cfg config.PricingConfig,
	binanceAsk *core.AtomicPrice,
	vwap *VWAPCalculator,
) *SpreadCalculator {
	return &SpreadCalculator{cfg: cfg, binanceAsk: binanceAsk, vwap: vwap}
}

// Calculate computes the actionable spread at the current instant.
func (s *SpreadCalculator) Calculate() (*SpreadResult, error) {
	rawAsk := s.binanceAsk.Load()
	if !rawAsk.IsPos() {
		return nil, fmt.Errorf("binance ask price not available")
	}

	rawVWAP, err := s.vwap.CalcBidVWAP(s.cfg.BudgetUSD)
	if err != nil {
		return nil, fmt.Errorf("gate VWAP: %w", err)
	}

	// Gate side: penalise for liquidity pulling and taker fee
	gateSlipPct, _ := s.cfg.GateSlippagePct.Quo(decimal.Hundred)
	gateSlipFactor, _ := decimal.One.Sub(gateSlipPct)
	gateFeePct, _ := s.cfg.GateTakerFeePct.Quo(decimal.Hundred)
	gateFeeFactor, _ := decimal.One.Sub(gateFeePct)
	adjustedGate, _ := rawVWAP.Mul(gateSlipFactor)
	adjustedGate, _ = adjustedGate.Mul(gateFeeFactor)

	// Binance side: depends on execution path
	var adjustedBinance decimal.Decimal
	switch s.cfg.ExecutionPath {
	case "hedged":
		// Path B: actually buying on Binance, add slippage + taker fee
		bncSlipPct, _ := s.cfg.BinanceSlippagePct.Quo(decimal.Hundred)
		bncSlipFactor, _ := decimal.One.Add(bncSlipPct)
		bncFeePct, _ := s.cfg.BinanceTakerFeePct.Quo(decimal.Hundred)
		bncFeeFactor, _ := decimal.One.Add(bncFeePct)
		adjustedBinance, _ = rawAsk.Mul(bncSlipFactor)
		adjustedBinance, _ = adjustedBinance.Mul(bncFeeFactor)
	default:
		// Path A (naked_short): Binance is price anchor only,
		// shift anchor down by expected momentum drift
		driftPct, _ := s.cfg.BinanceMomentumDriftPct.Quo(decimal.Hundred)
		driftFactor, _ := decimal.One.Sub(driftPct)
		adjustedBinance, _ = rawAsk.Mul(driftFactor)
	}

	rawDiff, _ := rawVWAP.Sub(rawAsk)
	rawSpread, _ := rawDiff.Quo(rawAsk)
	rawSpread, _ = rawSpread.Mul(decimal.Hundred)

	actionDiff, _ := adjustedGate.Sub(adjustedBinance)
	actionableSpread, _ := actionDiff.Quo(adjustedBinance)
	actionableSpread, _ = actionableSpread.Mul(decimal.Hundred)

	result := &SpreadResult{
		RawGateVWAP:         rawVWAP,
		AdjustedGateVWAP:    adjustedGate,
		RawBinanceAsk:       rawAsk,
		AdjustedBinanceAsk:  adjustedBinance,
		RawSpreadPct:        rawSpread,
		ActionableSpreadPct: actionableSpread,
		Ts:                  time.Now(),
	}

	slog.Info("[Spread] calculated",
		"raw_pct", rawSpread, "actionable_pct", actionableSpread,
		"gate_vwap", rawVWAP, "gate_adj", adjustedGate,
		"bnc_ask", rawAsk, "bnc_adj", adjustedBinance,
		"path", s.cfg.ExecutionPath)

	return result, nil
}
