package feed

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"obvious-profits/utils"

	"github.com/bytedance/sonic"
	"github.com/govalues/decimal"
)

// ContractInfo holds the full metadata for a single Gate.io USDT-settled futures contract.
type ContractInfo struct {
	// Identity
	Name   string
	Type   string // "direct", "quanto", etc.
	Status string // "trading", etc.

	// Funding
	FundingRate           decimal.Decimal
	FundingRateIndicative decimal.Decimal
	FundingInterval       int   // seconds (e.g. 28800 = 8h)
	FundingNextApply      int64 // unix timestamp
	FundingImpactValue    decimal.Decimal
	FundingCapRatio       decimal.Decimal
	FundingRateLimit      decimal.Decimal
	FundingOffset         int
	InterestRate          decimal.Decimal

	// Pricing
	MarkPrice      decimal.Decimal
	MarkType       string
	MarkPriceRound decimal.Decimal
	IndexPrice     decimal.Decimal
	LastPrice      decimal.Decimal

	// Order constraints
	OrderSizeMin      int64
	OrderSizeMax      int64
	OrderPriceRound   decimal.Decimal
	OrderPriceDeviate decimal.Decimal
	OrdersLimit       int

	// Leverage & risk
	LeverageMin          decimal.Decimal
	LeverageMax          decimal.Decimal
	CrossLeverageDefault decimal.Decimal
	MaintenanceRate      decimal.Decimal
	RiskLimitBase        decimal.Decimal
	RiskLimitMax         decimal.Decimal
	RiskLimitStep        decimal.Decimal

	// Fees
	MakerFeeRate    decimal.Decimal
	TakerFeeRate    decimal.Decimal
	RefRebateRate   decimal.Decimal
	RefDiscountRate decimal.Decimal

	// Contract details
	QuantoMultiplier     decimal.Decimal
	EnableDecimal        bool
	EnableBonus          bool
	EnableCredit         bool
	InDelisting          bool
	IsPreMarket          bool
	EnableCircuitBreaker bool

	// Market data snapshot
	TradeSize    int64
	PositionSize int64
	LongUsers    int
	ShortUsers   int
	TradeID      int64
	OrderbookID  int64

	// Timestamps
	CreateTime       int64
	LaunchTime       int64
	ConfigChangeTime int64

	// Market order
	VoucherLeverage      decimal.Decimal
	MarketOrderSlipRatio decimal.Decimal
	MarketOrderSizeMax   decimal.Decimal
}

type gateContractResponse struct {
	Name                  string `json:"name"`
	Type                  string `json:"type"`
	Status                string `json:"status"`
	FundingRate           string `json:"funding_rate"`
	FundingRateIndicative string `json:"funding_rate_indicative"`
	FundingInterval       int    `json:"funding_interval"`
	FundingNextApply      int64  `json:"funding_next_apply"`
	FundingImpactValue    string `json:"funding_impact_value"`
	FundingCapRatio       string `json:"funding_cap_ratio"`
	FundingRateLimit      string `json:"funding_rate_limit"`
	FundingOffset         int    `json:"funding_offset"`
	InterestRate          string `json:"interest_rate"`
	MarkPrice             string `json:"mark_price"`
	MarkType              string `json:"mark_type"`
	MarkPriceRound        string `json:"mark_price_round"`
	IndexPrice            string `json:"index_price"`
	LastPrice             string `json:"last_price"`
	OrderSizeMin          int64  `json:"order_size_min"`
	OrderSizeMax          int64  `json:"order_size_max"`
	OrderPriceRound       string `json:"order_price_round"`
	OrderPriceDeviate     string `json:"order_price_deviate"`
	OrdersLimit           int    `json:"orders_limit"`
	LeverageMin           string `json:"leverage_min"`
	LeverageMax           string `json:"leverage_max"`
	CrossLeverageDefault  string `json:"cross_leverage_default"`
	MaintenanceRate       string `json:"maintenance_rate"`
	RiskLimitBase         string `json:"risk_limit_base"`
	RiskLimitMax          string `json:"risk_limit_max"`
	RiskLimitStep         string `json:"risk_limit_step"`
	MakerFeeRate          string `json:"maker_fee_rate"`
	TakerFeeRate          string `json:"taker_fee_rate"`
	RefRebateRate         string `json:"ref_rebate_rate"`
	RefDiscountRate       string `json:"ref_discount_rate"`
	QuantoMultiplier      string `json:"quanto_multiplier"`
	EnableDecimal         bool   `json:"enable_decimal"`
	EnableBonus           bool   `json:"enable_bonus"`
	EnableCredit          bool   `json:"enable_credit"`
	InDelisting           bool   `json:"in_delisting"`
	IsPreMarket           bool   `json:"is_pre_market"`
	EnableCircuitBreaker  bool   `json:"enable_circuit_breaker"`
	TradeSize             int64  `json:"trade_size"`
	PositionSize          int64  `json:"position_size"`
	LongUsers             int    `json:"long_users"`
	ShortUsers            int    `json:"short_users"`
	TradeID               int64  `json:"trade_id"`
	OrderbookID           int64  `json:"orderbook_id"`
	CreateTime            int64  `json:"create_time"`
	LaunchTime            int64  `json:"launch_time"`
	ConfigChangeTime      int64  `json:"config_change_time"`
	VoucherLeverage       string `json:"voucher_leverage"`
	MarketOrderSlipRatio  string `json:"market_order_slip_ratio"`
	MarketOrderSizeMax    string `json:"market_order_size_max"`
}

// ContractCache periodically fetches all Gate.io USDT-settled futures contracts
// and caches them locally for lock-free lookups.
type ContractCache struct {
	apiBase         string
	refreshInterval time.Duration

	mu        sync.RWMutex
	contracts map[string]ContractInfo
}

func NewContractCache(apiBase string, refreshInterval time.Duration) *ContractCache {
	return &ContractCache{
		apiBase:         apiBase,
		refreshInterval: refreshInterval,
		contracts:       make(map[string]ContractInfo),
	}
}

// Get returns contract info for the given symbol. Thread-safe.
func (c *ContractCache) Get(symbol string) (ContractInfo, bool) {
	c.mu.RLock()
	info, ok := c.contracts[symbol]
	c.mu.RUnlock()
	return info, ok
}

// Run fetches contracts immediately, then refreshes at the configured interval.
func (c *ContractCache) Run(ctx context.Context) error {
	slog.Info("[ContractCache] starting", "interval", c.refreshInterval)

	if err := c.fetchAndParse(ctx); err != nil {
		slog.Error("[ContractCache] initial fetch failed", "error", err)
	}

	ticker := time.NewTicker(c.refreshInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			if err := c.fetchAndParse(ctx); err != nil {
				slog.Error("[ContractCache] refresh failed", "error", err)
			}
		}
	}
}

func (c *ContractCache) fetchAndParse(ctx context.Context) error {
	url := fmt.Sprintf("%s/futures/usdt/contracts", c.apiBase)
	body, err := utils.HTTPGetJSON(ctx, url)
	if err != nil {
		return fmt.Errorf("fetch contracts: %w", err)
	}

	var raw []gateContractResponse
	if err := sonic.Unmarshal(body, &raw); err != nil {
		return fmt.Errorf("unmarshal contracts: %w", err)
	}

	m := make(map[string]ContractInfo, len(raw))
	for _, r := range raw {
		impactVal, err := decimal.Parse(r.FundingImpactValue)
		if err != nil {
			slog.Warn("[ContractCache] skip contract: bad funding_impact_value", "name", r.Name, "error", err)
			continue
		}
		quantoMul, err := decimal.Parse(r.QuantoMultiplier)
		if err != nil {
			slog.Warn("[ContractCache] skip contract: bad quanto_multiplier", "name", r.Name, "error", err)
			continue
		}

		m[r.Name] = ContractInfo{
			Name:                  r.Name,
			Type:                  r.Type,
			Status:                r.Status,
			FundingRate:           parseDecimalOrZero(r.FundingRate),
			FundingRateIndicative: parseDecimalOrZero(r.FundingRateIndicative),
			FundingInterval:       r.FundingInterval,
			FundingNextApply:      r.FundingNextApply,
			FundingImpactValue:    impactVal,
			FundingCapRatio:       parseDecimalOrZero(r.FundingCapRatio),
			FundingRateLimit:      parseDecimalOrZero(r.FundingRateLimit),
			FundingOffset:         r.FundingOffset,
			InterestRate:          parseDecimalOrZero(r.InterestRate),
			MarkPrice:             parseDecimalOrZero(r.MarkPrice),
			MarkType:              r.MarkType,
			MarkPriceRound:        parseDecimalOrZero(r.MarkPriceRound),
			IndexPrice:            parseDecimalOrZero(r.IndexPrice),
			LastPrice:             parseDecimalOrZero(r.LastPrice),
			OrderSizeMin:          r.OrderSizeMin,
			OrderSizeMax:          r.OrderSizeMax,
			OrderPriceRound:       parseDecimalOrZero(r.OrderPriceRound),
			OrderPriceDeviate:     parseDecimalOrZero(r.OrderPriceDeviate),
			OrdersLimit:           r.OrdersLimit,
			LeverageMin:           parseDecimalOrZero(r.LeverageMin),
			LeverageMax:           parseDecimalOrZero(r.LeverageMax),
			CrossLeverageDefault:  parseDecimalOrZero(r.CrossLeverageDefault),
			MaintenanceRate:       parseDecimalOrZero(r.MaintenanceRate),
			RiskLimitBase:         parseDecimalOrZero(r.RiskLimitBase),
			RiskLimitMax:          parseDecimalOrZero(r.RiskLimitMax),
			RiskLimitStep:         parseDecimalOrZero(r.RiskLimitStep),
			MakerFeeRate:          parseDecimalOrZero(r.MakerFeeRate),
			TakerFeeRate:          parseDecimalOrZero(r.TakerFeeRate),
			RefRebateRate:         parseDecimalOrZero(r.RefRebateRate),
			RefDiscountRate:       parseDecimalOrZero(r.RefDiscountRate),
			QuantoMultiplier:      quantoMul,
			EnableDecimal:         r.EnableDecimal,
			EnableBonus:           r.EnableBonus,
			EnableCredit:          r.EnableCredit,
			InDelisting:           r.InDelisting,
			IsPreMarket:           r.IsPreMarket,
			EnableCircuitBreaker:  r.EnableCircuitBreaker,
			TradeSize:             r.TradeSize,
			PositionSize:          r.PositionSize,
			LongUsers:             r.LongUsers,
			ShortUsers:            r.ShortUsers,
			TradeID:               r.TradeID,
			OrderbookID:           r.OrderbookID,
			CreateTime:            r.CreateTime,
			LaunchTime:            r.LaunchTime,
			ConfigChangeTime:      r.ConfigChangeTime,
			VoucherLeverage:       parseDecimalOrZero(r.VoucherLeverage),
			MarketOrderSlipRatio:  parseDecimalOrZero(r.MarketOrderSlipRatio),
			MarketOrderSizeMax:    parseDecimalOrZero(r.MarketOrderSizeMax),
		}
	}

	c.mu.Lock()
	c.contracts = m
	c.mu.Unlock()

	slog.Info("[ContractCache] refreshed", "count", len(m))
	return nil
}

func parseDecimalOrZero(s string) decimal.Decimal {
	if s == "" {
		return decimal.Zero
	}
	d, err := decimal.Parse(s)
	if err != nil {
		return decimal.Zero
	}
	return d
}
