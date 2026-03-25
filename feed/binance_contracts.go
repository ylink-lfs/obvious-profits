package feed

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"obvious-profits/utils"

	"github.com/bytedance/sonic"
	"github.com/govalues/decimal"
	"golang.org/x/sync/errgroup"
)

// ---------------------------------------------------------------------------
// JSON response structs (private, match Binance REST API shape)
// ---------------------------------------------------------------------------

type binanceExchangeInfoResp struct {
	Symbols []binanceSymbolInfo `json:"symbols"`
}

type binanceSymbolInfo struct {
	Symbol       string              `json:"symbol"`       // "BLZUSDT"
	Status       string              `json:"status"`       // "TRADING", "SETTLING", etc.
	BaseAsset    string              `json:"baseAsset"`    // For "BLZUSDT", "BLZ"
	QuoteAsset   string              `json:"quoteAsset"`   // For "BLZUSDT", "USDT"
	ContractType string              `json:"contractType"` // "PERPETUAL", "CURRENT_QUARTER", etc.
	Filters      []binanceFilterInfo `json:"filters"`      // "PRICE_FILTER", "LOT_SIZE", etc.
}

type binanceFilterInfo struct {
	FilterType string `json:"filterType"`
	TickSize   string `json:"tickSize,omitempty"`
	StepSize   string `json:"stepSize,omitempty"`
	MinQty     string `json:"minQty,omitempty"`
	MaxQty     string `json:"maxQty,omitempty"`
}

type binanceTicker24hrResp struct {
	Symbol      string `json:"symbol"`
	Volume      string `json:"volume"`      // base asset volume
	QuoteVolume string `json:"quoteVolume"` // quote asset (USDT) volume
}

type binancePremiumIndexResp struct {
	Symbol          string `json:"symbol"`
	MarkPrice       string `json:"markPrice"`
	IndexPrice      string `json:"indexPrice"`
	LastFundingRate string `json:"lastFundingRate"`
	NextFundingTime int64  `json:"nextFundingTime"`
}

// ---------------------------------------------------------------------------
// Public domain types
// ---------------------------------------------------------------------------

// BinanceSymbolMeta holds parsed contract metadata for a Binance USDT-M perpetual.
type BinanceSymbolMeta struct {
	Symbol       string
	BaseAsset    string
	QuoteAsset   string
	Status       string // "TRADING", etc.
	ContractType string // "PERPETUAL", etc.
	TickSize     decimal.Decimal
	StepSize     decimal.Decimal
	MinQty       decimal.Decimal
	MaxQty       decimal.Decimal
}

// BinanceTicker24h holds 24-hour rolling volume for a Binance futures symbol.
type BinanceTicker24h struct {
	Symbol      string
	Volume      decimal.Decimal // base asset volume
	QuoteVolume decimal.Decimal // USDT volume
}

// BinanceFundingInfo holds the latest premium index / funding snapshot.
type BinanceFundingInfo struct {
	Symbol          string
	MarkPrice       decimal.Decimal
	IndexPrice      decimal.Decimal
	LastFundingRate decimal.Decimal
	NextFundingTime int64
}

// BinanceDataSnapshot is an immutable aggregate of all Binance REST data.
// Maps are keyed by lowercase symbol (e.g. "btcusdt").
type BinanceDataSnapshot struct {
	Symbols   map[string]BinanceSymbolMeta
	Tickers   map[string]BinanceTicker24h
	Funding   map[string]BinanceFundingInfo
	FetchedAt time.Time
}

// ---------------------------------------------------------------------------
// BinanceDataFeed — periodic REST cache
// ---------------------------------------------------------------------------

// BinanceDataFeed periodically fetches Binance Futures public REST endpoints
// and caches the result as an immutable BinanceDataSnapshot.
type BinanceDataFeed struct {
	apiBase         string
	refreshInterval time.Duration

	mu       sync.RWMutex
	snapshot BinanceDataSnapshot
}

func NewBinanceDataFeed(apiBase string, refreshInterval time.Duration) *BinanceDataFeed {
	return &BinanceDataFeed{
		apiBase:         apiBase,
		refreshInterval: refreshInterval,
	}
}

// Snapshot returns a copy of the latest data snapshot. Thread-safe.
func (f *BinanceDataFeed) Snapshot() BinanceDataSnapshot {
	f.mu.RLock()
	snap := f.snapshot
	f.mu.RUnlock()
	return snap
}

// Run fetches data immediately, then refreshes at the configured interval.
func (f *BinanceDataFeed) Run(ctx context.Context) error {
	slog.Info("[BinanceDataFeed] starting", "interval", f.refreshInterval)

	if err := f.refresh(ctx); err != nil {
		slog.Error("[BinanceDataFeed] initial fetch failed", "error", err)
	}

	ticker := time.NewTicker(f.refreshInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			if err := f.refresh(ctx); err != nil {
				slog.Error("[BinanceDataFeed] refresh failed", "error", err)
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Parallel refresh orchestrator
// ---------------------------------------------------------------------------

func (f *BinanceDataFeed) refresh(ctx context.Context) error {
	g, gCtx := errgroup.WithContext(ctx)

	var symbols map[string]BinanceSymbolMeta
	var tickers map[string]BinanceTicker24h
	var funding map[string]BinanceFundingInfo

	g.Go(func() error {
		var err error
		symbols, err = f.fetchExchangeInfo(gCtx)
		return err
	})
	g.Go(func() error {
		var err error
		tickers, err = f.fetchTicker24h(gCtx)
		return err
	})
	g.Go(func() error {
		var err error
		funding, err = f.fetchPremiumIndex(gCtx)
		return err
	})

	if err := g.Wait(); err != nil {
		return fmt.Errorf("refresh: %w", err)
	}

	snap := BinanceDataSnapshot{
		Symbols:   symbols,
		Tickers:   tickers,
		Funding:   funding,
		FetchedAt: time.Now(),
	}

	f.mu.Lock()
	f.snapshot = snap
	f.mu.Unlock()

	slog.Info("[BinanceDataFeed] refreshed",
		"symbols", len(symbols), "tickers", len(tickers), "funding", len(funding))
	return nil
}

// ---------------------------------------------------------------------------
// Individual fetch methods
// ---------------------------------------------------------------------------

func (f *BinanceDataFeed) fetchExchangeInfo(ctx context.Context) (map[string]BinanceSymbolMeta, error) {
	// Request Weight: 1
	url := fmt.Sprintf("%s/fapi/v1/exchangeInfo", f.apiBase)
	body, err := utils.HTTPGetJSON(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("exchangeInfo: %w", err)
	}

	var resp binanceExchangeInfoResp
	if err := sonic.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("unmarshal exchangeInfo: %w", err)
	}

	m := make(map[string]BinanceSymbolMeta, len(resp.Symbols))
	for _, s := range resp.Symbols {
		meta := BinanceSymbolMeta{
			Symbol:       s.Symbol,
			BaseAsset:    s.BaseAsset,
			QuoteAsset:   s.QuoteAsset,
			Status:       s.Status,
			ContractType: s.ContractType,
		}
		for _, ft := range s.Filters {
			switch ft.FilterType {
			case "PRICE_FILTER":
				meta.TickSize = parseDecimalOrZero(ft.TickSize)
			case "LOT_SIZE":
				meta.StepSize = parseDecimalOrZero(ft.StepSize)
				meta.MinQty = parseDecimalOrZero(ft.MinQty)
				meta.MaxQty = parseDecimalOrZero(ft.MaxQty)
			}
		}
		key := strings.ToLower(s.Symbol)
		m[key] = meta
	}
	return m, nil
}

func (f *BinanceDataFeed) fetchTicker24h(ctx context.Context) (map[string]BinanceTicker24h, error) {
	// Request Weight: 40 (the symbol parameter is omitted)
	url := fmt.Sprintf("%s/fapi/v1/ticker/24hr", f.apiBase)
	body, err := utils.HTTPGetJSON(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("ticker24hr: %w", err)
	}

	var raw []binanceTicker24hrResp
	if err := sonic.Unmarshal(body, &raw); err != nil {
		return nil, fmt.Errorf("unmarshal ticker24hr: %w", err)
	}

	m := make(map[string]BinanceTicker24h, len(raw))
	for _, r := range raw {
		key := strings.ToLower(r.Symbol)
		m[key] = BinanceTicker24h{
			Symbol:      r.Symbol,
			Volume:      parseDecimalOrZero(r.Volume),
			QuoteVolume: parseDecimalOrZero(r.QuoteVolume),
		}
	}
	return m, nil
}

func (f *BinanceDataFeed) fetchPremiumIndex(ctx context.Context) (map[string]BinanceFundingInfo, error) {
	// Request Weight: 10 (the symbol parameter is omitted)
	url := fmt.Sprintf("%s/fapi/v1/premiumIndex", f.apiBase)
	body, err := utils.HTTPGetJSON(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("premiumIndex: %w", err)
	}

	var raw []binancePremiumIndexResp
	if err := sonic.Unmarshal(body, &raw); err != nil {
		return nil, fmt.Errorf("unmarshal premiumIndex: %w", err)
	}

	m := make(map[string]BinanceFundingInfo, len(raw))
	for _, r := range raw {
		key := strings.ToLower(r.Symbol)
		m[key] = BinanceFundingInfo{
			Symbol:          r.Symbol,
			MarkPrice:       parseDecimalOrZero(r.MarkPrice),
			IndexPrice:      parseDecimalOrZero(r.IndexPrice),
			LastFundingRate: parseDecimalOrZero(r.LastFundingRate),
			NextFundingTime: r.NextFundingTime,
		}
	}
	return m, nil
}


