package risk

import (
	"fmt"
	"log/slog"

	"github.com/govalues/decimal"

	"obvious-profits/config"
	"obvious-profits/memory"
)

// ImpactCost computes expected slippage for a given order size
// against the local orderbook (Pillar 4: Feasibility).
type ImpactCost struct {
	cfg  config.RiskConfig
	book *memory.L2Book
}

func NewImpactCost(cfg config.RiskConfig, book *memory.L2Book) *ImpactCost {
	return &ImpactCost{cfg: cfg, book: book}
}

type ImpactResult struct {
	Feasible     bool
	AvgFillPrice decimal.Decimal
	ImpactPct    decimal.Decimal
	Reason       string
}

func (ic *ImpactCost) EstimateSell(sizeUSD decimal.Decimal) ImpactResult {
	bids := ic.book.TopBids(20)
	if len(bids) == 0 {
		return ImpactResult{Feasible: false, Reason: "no bid depth"}
	}

	bestBid := bids[0].Price
	remaining := sizeUSD
	totalFilled := decimal.Zero
	totalCost := decimal.Zero

	for _, level := range bids {
		levelUSD, _ := level.Price.Mul(level.Qty)
		fill := remaining
		if levelUSD.Cmp(remaining) < 0 {
			fill = levelUSD
		}
		qty, _ := fill.Quo(level.Price)
		totalFilled, _ = totalFilled.Add(qty)
		cost, _ := qty.Mul(level.Price)
		totalCost, _ = totalCost.Add(cost)
		remaining, _ = remaining.Sub(fill)
		if !remaining.IsPos() {
			break
		}
	}

	if remaining.IsPos() {
		return ImpactResult{
			Feasible: false,
			Reason:   fmt.Sprintf("insufficient depth: $%s unfilled of $%s", remaining, sizeUSD),
		}
	}

	avgPrice, _ := totalCost.Quo(totalFilled)
	diff, _ := bestBid.Sub(avgPrice)
	impactPct, _ := diff.Quo(bestBid)
	impactPct, _ = impactPct.Mul(decimal.Hundred)

	result := ImpactResult{
		Feasible:     impactPct.Cmp(ic.cfg.MaxImpactCostPct) <= 0,
		AvgFillPrice: avgPrice,
		ImpactPct:    impactPct,
	}
	if !result.Feasible {
		result.Reason = fmt.Sprintf("impact %s%% exceeds max %s%%", impactPct, ic.cfg.MaxImpactCostPct)
	}
	slog.Info("[ImpactCost] sell estimate",
		"size_usd", sizeUSD, "avg_price", avgPrice, "impact_pct", impactPct, "feasible", result.Feasible)
	return result
}

func (ic *ImpactCost) EstimateBuy(sizeUSD decimal.Decimal) ImpactResult {
	asks := ic.book.TopAsks(20)
	if len(asks) == 0 {
		return ImpactResult{Feasible: false, Reason: "no ask depth"}
	}

	bestAsk := asks[0].Price
	remaining := sizeUSD
	totalFilled := decimal.Zero
	totalCost := decimal.Zero

	for _, level := range asks {
		levelUSD, _ := level.Price.Mul(level.Qty)
		fill := remaining
		if levelUSD.Cmp(remaining) < 0 {
			fill = levelUSD
		}
		qty, _ := fill.Quo(level.Price)
		totalFilled, _ = totalFilled.Add(qty)
		cost, _ := qty.Mul(level.Price)
		totalCost, _ = totalCost.Add(cost)
		remaining, _ = remaining.Sub(fill)
		if !remaining.IsPos() {
			break
		}
	}

	if remaining.IsPos() {
		return ImpactResult{
			Feasible: false,
			Reason:   fmt.Sprintf("insufficient depth: $%s unfilled of $%s", remaining, sizeUSD),
		}
	}

	avgPrice, _ := totalCost.Quo(totalFilled)
	diff, _ := avgPrice.Sub(bestAsk)
	impactPct, _ := diff.Quo(bestAsk)
	impactPct, _ = impactPct.Mul(decimal.Hundred)

	result := ImpactResult{
		Feasible:     impactPct.Cmp(ic.cfg.MaxImpactCostPct) <= 0,
		AvgFillPrice: avgPrice,
		ImpactPct:    impactPct,
	}
	if !result.Feasible {
		result.Reason = fmt.Sprintf("impact %s%% exceeds max %s%%", impactPct, ic.cfg.MaxImpactCostPct)
	}
	slog.Info("[ImpactCost] buy estimate",
		"size_usd", sizeUSD, "avg_price", avgPrice, "impact_pct", impactPct, "feasible", result.Feasible)
	return result
}
