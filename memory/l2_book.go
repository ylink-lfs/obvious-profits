package memory

import (
	"sort"
	"sync"

	"github.com/govalues/decimal"

	"obvious-profits/core"
)

// L2Book maintains a local orderbook depth tree for a single symbol.
type L2Book struct {
	mu   sync.RWMutex
	bids map[string]Level // price string → Level
	asks map[string]Level
}

func NewL2Book() *L2Book {
	return &L2Book{bids: make(map[string]Level), asks: make(map[string]Level)}
}

func (b *L2Book) Apply(u core.L2Update) {
	b.mu.Lock()
	defer b.mu.Unlock()
	book := b.bids
	if u.Side == core.SideAsk {
		book = b.asks
	}
	key := u.Price.String()
	if u.Qty.IsZero() {
		delete(book, key)
	} else {
		book[key] = Level{Price: u.Price, Qty: u.Qty}
	}
}

type Level struct {
	Price decimal.Decimal
	Qty   decimal.Decimal
}

func (b *L2Book) TopBids(n int) []Level {
	b.mu.RLock()
	defer b.mu.RUnlock()
	levels := make([]Level, 0, len(b.bids))
	for _, l := range b.bids {
		levels = append(levels, l)
	}
	sort.Slice(levels, func(i, j int) bool { return levels[i].Price.Cmp(levels[j].Price) > 0 })
	if n > len(levels) {
		n = len(levels)
	}
	return levels[:n]
}

func (b *L2Book) TopAsks(n int) []Level {
	b.mu.RLock()
	defer b.mu.RUnlock()
	levels := make([]Level, 0, len(b.asks))
	for _, l := range b.asks {
		levels = append(levels, l)
	}
	sort.Slice(levels, func(i, j int) bool { return levels[i].Price.Cmp(levels[j].Price) < 0 })
	if n > len(levels) {
		n = len(levels)
	}
	return levels[:n]
}

func (b *L2Book) TotalBidDepth(n int) decimal.Decimal {
	total := decimal.Zero
	for _, l := range b.TopBids(n) {
		notional, _ := l.Price.Mul(l.Qty)
		total, _ = total.Add(notional)
	}
	return total
}

func (b *L2Book) TotalAskDepth(n int) decimal.Decimal {
	total := decimal.Zero
	for _, l := range b.TopAsks(n) {
		notional, _ := l.Price.Mul(l.Qty)
		total, _ = total.Add(notional)
	}
	return total
}

// ReplaceAll atomically clears the entire book and repopulates from snapshot data.
// Used by full-snapshot orderbook feeds.
func (b *L2Book) ReplaceAll(bids, asks []Level) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.bids = make(map[string]Level, len(bids))
	b.asks = make(map[string]Level, len(asks))
	for _, l := range bids {
		b.bids[l.Price.String()] = l
	}
	for _, l := range asks {
		b.asks[l.Price.String()] = l
	}
}
