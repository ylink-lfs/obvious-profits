package core

import (
	"sync"
	"sync/atomic"
	"time"

	"github.com/govalues/decimal"
)

// AtomicPrice stores a decimal.Decimal price with a RWMutex for safe concurrent access.
type AtomicPrice struct {
	mu    sync.RWMutex
	price decimal.Decimal
	ts    atomic.Int64
}

func (a *AtomicPrice) Store(price decimal.Decimal) {
	a.mu.Lock()
	a.price = price
	a.mu.Unlock()
	a.ts.Store(time.Now().UnixNano())
}

func (a *AtomicPrice) Load() decimal.Decimal {
	a.mu.RLock()
	p := a.price
	a.mu.RUnlock()
	return p
}

func (a *AtomicPrice) LastUpdate() time.Time {
	return time.Unix(0, a.ts.Load())
}

// PriceState holds the latest price snapshots for a single symbol pair.
type PriceState struct {
	BinanceAsk              AtomicPrice
	BinanceBid              AtomicPrice
	GateAsk                 AtomicPrice
	GateBid                 AtomicPrice
	GateIndexPrice          AtomicPrice // real-time index price from futures.tickers WS
	WsIndicativeFundingRate AtomicPrice // exchange-reported indicative funding rate from futures.tickers WS
}

// TheoreticalFundingState holds the latest theoretical funding rate for Gate.
type TheoreticalFundingState struct {
	mu   sync.RWMutex
	rate decimal.Decimal
	ts   atomic.Int64
}

func (f *TheoreticalFundingState) Store(rate decimal.Decimal) {
	f.mu.Lock()
	f.rate = rate
	f.mu.Unlock()
	f.ts.Store(time.Now().UnixNano())
}

func (f *TheoreticalFundingState) Load() decimal.Decimal {
	f.mu.RLock()
	r := f.rate
	f.mu.RUnlock()
	return r
}

func (f *TheoreticalFundingState) LastUpdate() time.Time {
	return time.Unix(0, f.ts.Load())
}
