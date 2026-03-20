package core

import (
	"time"

	"github.com/govalues/decimal"
)

// Ticker represents a best-bid/ask snapshot from any exchange.
type Ticker struct {
	Symbol     string
	Bid        decimal.Decimal
	BidQty     decimal.Decimal
	Ask        decimal.Decimal
	AskQty     decimal.Decimal
	ExchangeTs time.Time
	LocalTs    time.Time
}

// FundingSignal is emitted every 60s by the FundingMonitor.
// It carries the raw API funding rate, the two orthogonal filter
// dimensions (RPR + SR), and the fused ESI score.
type FundingSignal struct {
	Symbol      string
	FundingRate decimal.Decimal // discrete F_t from API
	RateLimit   decimal.Decimal // C_max from API (funding_rate_limit)
	RPR         decimal.Decimal // rolling percentile rank [0, 1]
	SR          decimal.Decimal // saturation ratio [0, 1]
	ESI         decimal.Decimal // fused extreme sentiment index [0, 1]
	Kappa       decimal.Decimal // data confidence coefficient [0, 1]
	SampleCount int             // current ring buffer fill count
	Ts          time.Time
}

// L2Update represents a single orderbook level change.
type L2Update struct {
	Symbol     string
	Side       Side
	Price      decimal.Decimal
	Qty        decimal.Decimal
	ExchangeTs time.Time
	LocalTs    time.Time
}

type Side int

const (
	SideBid Side = iota
	SideAsk
)

// SpreadSnapshot captures a point-in-time cross-exchange spread measurement.
type SpreadSnapshot struct {
	Symbol      string
	BinanceAsk  decimal.Decimal
	GateBid     decimal.Decimal
	SpreadPct   decimal.Decimal
	FundingRate decimal.Decimal
	Ts          time.Time
}

// TriggerSignal is emitted when right-side confirmation is detected.
type TriggerSignal struct {
	Symbol    string
	Direction TriggerDirection
	Snapshot  SpreadSnapshot
	Reason    string
	Ts        time.Time
}

type TriggerDirection int

const (
	TriggerShort TriggerDirection = iota
	TriggerLong
)

// PipelineState represents the state machine phase.
type PipelineState int

const (
	StateIdle PipelineState = iota
	StateAlert
	StateRiskCheck
	StateArmed
	StateTriggered
	StateCooldown
)

func (s PipelineState) String() string {
	switch s {
	case StateIdle:
		return "IDLE"
	case StateAlert:
		return "ALERT"
	case StateRiskCheck:
		return "RISK_CHECK"
	case StateArmed:
		return "ARMED"
	case StateTriggered:
		return "TRIGGERED"
	case StateCooldown:
		return "COOLDOWN"
	default:
		return "UNKNOWN"
	}
}
