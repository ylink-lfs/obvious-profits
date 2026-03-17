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

	remaining := budgetUSD
	totalQty := decimal.Zero
	totalCost := decimal.Zero

	for _, level := range bids {
		levelUSD, _ := level.Price.Mul(level.Qty)
		fill := remaining
		if levelUSD.Cmp(fill) < 0 {
			fill = levelUSD
		}
		qty, _ := fill.Quo(level.Price)
		totalQty, _ = totalQty.Add(qty)
		cost, _ := qty.Mul(level.Price)
		totalCost, _ = totalCost.Add(cost)
		remaining, _ = remaining.Sub(fill)
		if !remaining.IsPos() {
			break
		}
	}

	if remaining.IsPos() {
		return decimal.Zero, fmt.Errorf("insufficient bid depth: $%s unfilled of $%s", remaining, budgetUSD)
	}

	vwap, err := totalCost.Quo(totalQty)
	if err != nil {
		return decimal.Zero, fmt.Errorf("vwap division: %w", err)
	}
	return vwap, nil
}
