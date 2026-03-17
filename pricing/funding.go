package pricing

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"github.com/govalues/decimal"

	"obvious-profits/core"
	"obvious-profits/feed"
	"obvious-profits/memory"
)

// TheoreticalFundingCalculator computes real-time theoretical funding rate
// from local orderbook depth-weighted prices and websocket-streamed index price.
//
// The result is intentionally unclipped (no fmax/fmin clamping) — it reflects
// the true market-implied directional pressure, not the exchange's capped rate.
type TheoreticalFundingCalculator struct {
	symbol     string
	book       *memory.L2Book
	indexPrice *core.AtomicPrice
	contracts  *feed.ContractCache
	out        chan<- core.TheoreticalFundingRate

	mu   sync.Mutex
	ring *premiumRing
}

func NewTheoreticalFundingCalculator(
	symbol string,
	book *memory.L2Book,
	indexPrice *core.AtomicPrice,
	contracts *feed.ContractCache,
	out chan<- core.TheoreticalFundingRate,
) *TheoreticalFundingCalculator {
	return &TheoreticalFundingCalculator{
		symbol:     symbol,
		book:       book,
		indexPrice: indexPrice,
		contracts:  contracts,
		out:        out,
	}
}

// CalcDepthWeightedBuyPrice walks ask levels from lowest to highest,
// accumulating notional until funding_impact_value (USDT) is reached.
// Returns impact_value / total_base_qty — the depth-weighted average buy price.
func (c *TheoreticalFundingCalculator) CalcDepthWeightedBuyPrice() (decimal.Decimal, error) {
	info, ok := c.contracts.Get(c.symbol)
	if !ok {
		return decimal.Zero, fmt.Errorf("contract %s not found in cache", c.symbol)
	}

	asks := c.book.TopAsks(50)
	if len(asks) == 0 {
		return decimal.Zero, fmt.Errorf("no ask depth available")
	}

	return calcDepthWeightedPrice(asks, info.FundingImpactValue, info.QuantoMultiplier)
}

// CalcDepthWeightedSellPrice walks bid levels from highest to lowest,
// accumulating notional until funding_impact_value (USDT) is reached.
// Returns impact_value / total_base_qty — the depth-weighted average sell price.
func (c *TheoreticalFundingCalculator) CalcDepthWeightedSellPrice() (decimal.Decimal, error) {
	info, ok := c.contracts.Get(c.symbol)
	if !ok {
		return decimal.Zero, fmt.Errorf("contract %s not found in cache", c.symbol)
	}

	bids := c.book.TopBids(50)
	if len(bids) == 0 {
		return decimal.Zero, fmt.Errorf("no bid depth available")
	}

	return calcDepthWeightedPrice(bids, info.FundingImpactValue, info.QuantoMultiplier)
}

// calcDepthWeightedPrice walks sorted levels (asks ascending or bids descending),
// accumulating notional (price * qty * quantoMultiplier) until impactValue USDT is filled.
// Returns impactValue / totalBaseQty.
func calcDepthWeightedPrice(levels []memory.Level, impactValue, quantoMultiplier decimal.Decimal) (decimal.Decimal, error) {
	remaining := impactValue
	totalBaseQty := decimal.Zero

	for _, level := range levels {
		// Each level.Qty is in contracts; convert to base currency
		baseQty, _ := level.Qty.Mul(quantoMultiplier)
		levelNotional, _ := level.Price.Mul(baseQty)

		if levelNotional.Cmp(remaining) >= 0 {
			// Partially fill this level
			partialBase, _ := remaining.Quo(level.Price)
			totalBaseQty, _ = totalBaseQty.Add(partialBase)
			remaining = decimal.Zero
			break
		}

		totalBaseQty, _ = totalBaseQty.Add(baseQty)
		remaining, _ = remaining.Sub(levelNotional)
	}

	if remaining.IsPos() {
		return decimal.Zero, fmt.Errorf("insufficient depth: $%s unfilled of $%s impact value", remaining, impactValue)
	}

	price, err := impactValue.Quo(totalBaseQty)
	if err != nil {
		return decimal.Zero, fmt.Errorf("depth-weighted price division: %w", err)
	}
	return price, nil
}

// CalcPremiumIndex computes the premium index from depth-weighted prices and index price.
// Formula: [Max(0, buyPrice - indexPrice) - Max(0, indexPrice - sellPrice)] / indexPrice
func (c *TheoreticalFundingCalculator) CalcPremiumIndex() (decimal.Decimal, error) {
	idx := c.indexPrice.Load()
	if !idx.IsPos() {
		return decimal.Zero, fmt.Errorf("index price not available")
	}

	buyPrice, err := c.CalcDepthWeightedBuyPrice()
	if err != nil {
		return decimal.Zero, fmt.Errorf("buy price: %w", err)
	}

	sellPrice, err := c.CalcDepthWeightedSellPrice()
	if err != nil {
		return decimal.Zero, fmt.Errorf("sell price: %w", err)
	}

	// Max(0, buyPrice - indexPrice)
	buyDiff, _ := buyPrice.Sub(idx)
	if buyDiff.IsNeg() {
		buyDiff = decimal.Zero
	}

	// Max(0, indexPrice - sellPrice)
	sellDiff, _ := idx.Sub(sellPrice)
	if sellDiff.IsNeg() {
		sellDiff = decimal.Zero
	}

	numerator, _ := buyDiff.Sub(sellDiff)
	premium, err := numerator.Quo(idx)
	if err != nil {
		return decimal.Zero, fmt.Errorf("premium index division: %w", err)
	}
	return premium, nil
}

var (
	clampHigh = decimal.MustParse("0.0005")
	clampLow  = decimal.MustParse("-0.0005")
)

// CalcTheoreticalFundingRate computes the theoretical (unclipped) funding rate.
// Formula: avg(premium_indices) + clamp(interest_rate - avg_premium, -0.0005, 0.0005)
// No fmax/fmin clamping is applied.
func (c *TheoreticalFundingCalculator) CalcTheoreticalFundingRate() (decimal.Decimal, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.ring == nil || c.ring.count == 0 {
		return decimal.Zero, fmt.Errorf("no premium index samples collected yet")
	}

	avgPremium := c.ring.Average()

	info, ok := c.contracts.Get(c.symbol)
	if !ok {
		return decimal.Zero, fmt.Errorf("contract %s not found in cache", c.symbol)
	}

	// clamp(interest_rate - avg_premium, -0.0005, 0.0005)
	diff, _ := info.InterestRate.Sub(avgPremium)
	clamped := clamp(diff, clampLow, clampHigh)

	rate, _ := avgPremium.Add(clamped)
	return rate, nil
}

func clamp(v, lo, hi decimal.Decimal) decimal.Decimal {
	if v.Cmp(lo) < 0 {
		return lo
	}
	if v.Cmp(hi) > 0 {
		return hi
	}
	return v
}

// Run samples premium index every 60 seconds and emits TheoreticalFundingRate events.
func (c *TheoreticalFundingCalculator) Run(ctx context.Context) error {
	slog.Info("[TheoFunding] starting", "symbol", c.symbol)

	// Initialize ring buffer based on funding interval
	info, ok := c.contracts.Get(c.symbol)
	ringSize := 480 // default: 8h / 60s
	if ok && info.FundingInterval > 0 {
		ringSize = info.FundingInterval / 60
	}
	c.mu.Lock()
	c.ring = newPremiumRing(ringSize)
	c.mu.Unlock()

	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			c.sampleAndEmit(ctx)
		}
	}
}

func (c *TheoreticalFundingCalculator) sampleAndEmit(ctx context.Context) {
	premium, err := c.CalcPremiumIndex()
	if err != nil {
		slog.Debug("[TheoFunding] premium index unavailable", "error", err)
		return
	}

	c.mu.Lock()
	c.ring.Push(premium)
	c.mu.Unlock()

	rate, err := c.CalcTheoreticalFundingRate()
	if err != nil {
		slog.Debug("[TheoFunding] funding rate unavailable", "error", err)
		return
	}

	// Annualize: rate * (8760 / intervalHours) * 100
	info, ok := c.contracts.Get(c.symbol)
	intervalHours := 8
	if ok && info.FundingInterval > 0 {
		intervalHours = info.FundingInterval / 3600
	}
	intervalsPerYear, _ := decimal.MustParse("8760").Quo(decimal.MustParse(strconv.Itoa(intervalHours)))
	apr, _ := rate.Mul(intervalsPerYear)
	apr, _ = apr.Mul(decimal.Hundred)

	now := time.Now()
	event := core.TheoreticalFundingRate{
		Symbol:          c.symbol,
		TheoreticalRate: rate,
		PremiumIndex:    premium,
		AnnualizedAPR:   apr,
		ExchangeTs:      now,
		LocalTs:         now,
	}

	slog.Info("[TheoFunding] sample",
		"symbol", c.symbol,
		"premium_index", premium,
		"theo_rate", rate,
		"apr", apr)

	select {
	case c.out <- event:
	case <-ctx.Done():
	}
}

// premiumRing is a fixed-size circular buffer of premium index samples.
type premiumRing struct {
	buf   []decimal.Decimal
	size  int
	pos   int
	count int
}

func newPremiumRing(size int) *premiumRing {
	if size <= 0 {
		size = 480
	}
	return &premiumRing{
		buf:  make([]decimal.Decimal, size),
		size: size,
	}
}

func (r *premiumRing) Push(v decimal.Decimal) {
	r.buf[r.pos] = v
	r.pos = (r.pos + 1) % r.size
	if r.count < r.size {
		r.count++
	}
}

func (r *premiumRing) Average() decimal.Decimal {
	if r.count == 0 {
		return decimal.Zero
	}
	sum := decimal.Zero
	for i := 0; i < r.count; i++ {
		sum, _ = sum.Add(r.buf[i])
	}
	avg, _ := sum.Quo(decimal.MustParse(strconv.Itoa(r.count)))
	return avg
}
