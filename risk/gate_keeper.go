package risk

import (
	"log/slog"

	"github.com/govalues/decimal"

	"obvious-profits/config"
	"obvious-profits/core"
)

var (
	minSpreadPct    = decimal.MustParse("0.1")
	fundingExtreme  = decimal.MustParse("0.001")
	negFundingLimit = decimal.MustParse("-0.001")
)

// GateKeeper implements Pillar 2 (Red Line / Risk Control).
type GateKeeper struct {
	cfg config.RiskConfig
}

func NewGateKeeper(cfg config.RiskConfig) *GateKeeper {
	return &GateKeeper{cfg: cfg}
}

// Check evaluates a SpreadSnapshot against Red Line rules.
func (g *GateKeeper) Check(snap core.SpreadSnapshot) bool {
	if snap.SpreadPct.Abs().Cmp(minSpreadPct) < 0 {
		slog.Warn("[GateKeeper] REJECT: spread too small", "spread_pct", snap.SpreadPct)
		return false
	}

	// Left-side burial guard: positive premium + positive funding = euphoric momentum
	if snap.SpreadPct.IsPos() && snap.FundingRate.Cmp(fundingExtreme) > 0 {
		weight, _ := g.cfg.LeftSideBurialWeight.Mul(decimal.Hundred)
		slog.Warn("[GateKeeper] REJECT: left-side burial risk",
			"spread_pct", snap.SpreadPct, "funding", snap.FundingRate, "weight_pct", weight)
		return false
	}

	// Negative premium + deeply negative funding = squeezed longs
	if snap.SpreadPct.IsNeg() && snap.FundingRate.Cmp(negFundingLimit) < 0 {
		slog.Warn("[GateKeeper] REJECT: left-side burial risk on long side",
			"spread_pct", snap.SpreadPct, "funding", snap.FundingRate)
		return false
	}

	// TODO: Add more sophisticated left-side detection using price velocity,
	// recent trade direction, and order flow imbalance.

	slog.Info("[GateKeeper] PASS", "spread_pct", snap.SpreadPct, "funding", snap.FundingRate)
	return true
}
