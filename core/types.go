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

// TheoreticalFundingRate represents a theoretical (unclipped) funding rate
// computed from real-time orderbook depth-weighted prices and index price.
// No fmax/fmin clamping is applied — this reflects true market-implied pressure.
type TheoreticalFundingRate struct {
	Symbol          string
	TheoreticalRate decimal.Decimal // unclipped theoretical funding rate
	PremiumIndex    decimal.Decimal // latest premium index snapshot
	AnnualizedAPR   decimal.Decimal
	ExchangeTs      time.Time
	LocalTs         time.Time
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
