package pricing

import (
	"fmt"

	"github.com/govalues/decimal"

	"obvious-profits/memory"
)

// VWAPCalculator computes volume-weighted average price against a local L2Book.
// Currently uses a fixed budget passed as parameter; a dedicated budget-sizing
// module will replace this in the future.
type VWAPCalculator struct {
	book *memory.L2Book
}

func NewVWAPCalculator(book *memory.L2Book) *VWAPCalculator {
	return &VWAPCalculator{book: book}
}

// CalcBidVWAP walks the bid side of the orderbook, filling up to budgetUSD,
// and returns the volume-weighted average bid price.
//
// This represents the realistic average price you would receive when selling
// (hitting bids) for the given notional amount.
func (v *VWAPCalculator) CalcBidVWAP(budgetUSD decimal.Decimal) (decimal.Decimal, error) {
	bids := v.book.TopBids(50)
	if len(bids) == 0 {
		return decimal.Zero, fmt.Errorf("no bid depth available")
	}
	return calcLevelVWAP(bids, budgetUSD, decimal.One)
}

// CalcAskVWAP walks the ask side of the orderbook, filling up to budgetUSD,
// and returns the volume-weighted average ask price.
//
// This represents the realistic average price you would pay when buying
// (lifting asks) for the given notional amount.
func (v *VWAPCalculator) CalcAskVWAP(budgetUSD decimal.Decimal) (decimal.Decimal, error) {
	asks := v.book.TopAsks(50)
	if len(asks) == 0 {
		return decimal.Zero, fmt.Errorf("no ask depth available")
	}
	return calcLevelVWAP(asks, budgetUSD, decimal.One)
}

// calcLevelVWAP walks sorted orderbook levels, filling up to budgetUSD of notional,
// and returns budgetUSD / totalBaseQty — the volume-weighted average price.
// quantoMultiplier converts level.Qty (contracts) to base currency units;
// pass decimal.One when qty is already in base currency.
func calcLevelVWAP(levels []memory.Level, budgetUSD, quantoMultiplier decimal.Decimal) (decimal.Decimal, error) {
	remaining := budgetUSD
	totalBaseQty := decimal.Zero

	for _, level := range levels {
		baseQty, _ := level.Qty.Mul(quantoMultiplier)
		levelNotional, _ := level.Price.Mul(baseQty)

		if levelNotional.Cmp(remaining) >= 0 {
			partialBase, _ := remaining.Quo(level.Price)
			totalBaseQty, _ = totalBaseQty.Add(partialBase)
			remaining = decimal.Zero
			break
		}

		totalBaseQty, _ = totalBaseQty.Add(baseQty)
		remaining, _ = remaining.Sub(levelNotional)
	}

	if remaining.IsPos() {
		return decimal.Zero, fmt.Errorf("insufficient depth: $%s unfilled of $%s", remaining, budgetUSD)
	}

	vwap, err := budgetUSD.Quo(totalBaseQty)
	if err != nil {
		return decimal.Zero, fmt.Errorf("vwap division: %w", err)
	}
	return vwap, nil
}
