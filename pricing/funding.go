package pricing

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/govalues/decimal"

	"obvious-profits/config"
	"obvious-profits/core"
	"obvious-profits/feed"
	"obvious-profits/utils"
)

var one = decimal.One

// FundingMonitor samples the funding rate every poll interval, preferring the
// real-time WS feed (futures.tickers) and falling back to the REST-cached
// ContractCache when the WS stream is stale (>30 s without a message).
// It computes RPR + SR, fuses them into ESI via cold-start-aware dynamic
// weighting, and emits FundingSignal events.
// ESI: Extreme Sentiment Index, a fused funding extremeness score in [0, 1].
// RPR: Rolling Percentile Rank of the current funding rate within the recent window.
// SR: Saturation Ratio, the absolute funding rate as a fraction of the maximum (C_max).
// κ: Data confidence coefficient, a function of the ring buffer fill level that governs the dynamic weighting between RPR and SR.
type FundingMonitor struct {
	symbol        string
	contracts     *feed.ContractCache
	wsFundingRate *core.AtomicPrice // real-time funding_rate from WS
	buf           *utils.RollingPercentile
	cfg           config.FundingConfig
	nTarget       int // RPRWindowDays * 1440
	out           chan<- core.FundingSignal
}

const wsStalenessThreshold = 30 * time.Second

func NewFundingMonitor(
	symbol string,
	contracts *feed.ContractCache,
	wsFundingRate *core.AtomicPrice,
	cfg config.FundingConfig,
	out chan<- core.FundingSignal,
) *FundingMonitor {
	if cfg.PollIntervalSeconds <= 0 {
		cfg.PollIntervalSeconds = 60
	}
	if cfg.RPRWindowDays <= 0 {
		cfg.RPRWindowDays = 14
	}
	nTarget := cfg.RPRWindowDays * 24 * 60 // 1-minute samples per window
	return &FundingMonitor{
		symbol:        symbol,
		contracts:     contracts,
		wsFundingRate: wsFundingRate,
		buf:           utils.NewRollingPercentile(nTarget),
		cfg:           cfg,
		nTarget:       nTarget,
		out:           out,
	}
}

// Run starts the periodic funding rate sampling loop.
func (m *FundingMonitor) Run(ctx context.Context) error {
	slog.Info("[FundingMonitor] starting", "symbol", m.symbol,
		"poll_interval_s", m.cfg.PollIntervalSeconds,
		"rpr_window_days", m.cfg.RPRWindowDays,
		"n_target", m.nTarget)

	ticker := time.NewTicker(time.Duration(m.cfg.PollIntervalSeconds) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			m.sampleAndEmit(ctx)
		}
	}
}

func (m *FundingMonitor) sampleAndEmit(ctx context.Context) {
	// Always need ContractCache for cMax (funding_rate_limit) — WS doesn't provide it.
	info, ok := m.contracts.Get(m.symbol)
	if !ok {
		slog.Debug("[FundingMonitor] contract not in cache", "symbol", m.symbol)
		return
	}
	cMax := info.FundingRateLimit // funding_rate_limit (C_max)

	// Prefer WS funding_rate; fall back to REST if WS stream is stale.
	var ft decimal.Decimal
	var source string
	if m.wsFundingRate != nil && time.Since(m.wsFundingRate.LastUpdate()) <= wsStalenessThreshold {
		ft = m.wsFundingRate.Load()
		source = "ws"
	} else {
		ft = info.FundingRate
		source = "rest"
	}

	// Push into ring buffer
	m.buf.Push(ft)
	n := m.buf.Count()

	// SR: |F_t / C_max|, clamped to [0, 1]
	sr, err := m.calcSR(ft, cMax)
	if err != nil {
		slog.Debug("[FundingMonitor] SR calc failed", "error", err)
		return
	}

	// RPR: rolling percentile rank [0, 1]
	rpr := m.buf.PercentileRank(ft)

	// κ = min(1, N/N_target)²
	kappa := m.calcKappa(n)

	// ESI = W_RPR * RPR + W_SR * SR
	// W_RPR = 0.5 * κ, W_SR = 1.0 - 0.5 * κ
	esi := m.calcESI(rpr, sr, kappa)

	sig := core.FundingSignal{
		Symbol:      m.symbol,
		FundingRate: ft,
		RateLimit:   cMax,
		RPR:         rpr,
		SR:          sr,
		ESI:         esi,
		Kappa:       kappa,
		SampleCount: n,
		Ts:          time.Now().Truncate(time.Minute),
	}

	slog.Info("[FundingMonitor] sample",
		"symbol", m.symbol,
		"source", source,
		"funding_rate", ft,
		"rate_limit", cMax,
		"sr", sr,
		"rpr", rpr,
		"kappa", kappa,
		"esi", esi,
		"samples", n)

	select {
	case m.out <- sig:
	case <-ctx.Done():
	}
}

// calcSR computes the saturation ratio: |F_t / C_max|, clamped to [0, 1].
func (m *FundingMonitor) calcSR(ft, cMax decimal.Decimal) (decimal.Decimal, error) {
	if cMax.IsZero() {
		return decimal.Zero, fmt.Errorf("funding_rate_limit is zero")
	}
	ratio, err := ft.Quo(cMax)
	if err != nil {
		return decimal.Zero, err
	}
	sr := ratio.Abs()
	if sr.Cmp(one) > 0 {
		sr = one
	}
	return sr, nil
}

// calcKappa computes the data confidence coefficient: min(1, N/N_target)².
func (m *FundingMonitor) calcKappa(n int) decimal.Decimal {
	if m.nTarget <= 0 {
		return one
	}
	dN, _ := decimal.New(int64(n), 0)
	dTarget, _ := decimal.New(int64(m.nTarget), 0)
	ratio, _ := dN.Quo(dTarget)
	if ratio.Cmp(one) > 0 {
		ratio = one
	}
	kappa, _ := ratio.Mul(ratio) // ratio²
	return kappa
}

// calcESI computes the Extreme Sentiment Index:
//
//	W_RPR = 0.5 * κ
//	W_SR  = 1.0 - 0.5 * κ
//	ESI   = W_RPR * RPR + W_SR * SR
func (m *FundingMonitor) calcESI(rpr, sr, kappa decimal.Decimal) decimal.Decimal {
	half := decimal.MustParse("0.5")
	halfKappa, _ := half.Mul(kappa) // 0.5 * κ

	wRPR := halfKappa            // W_RPR
	wSR, _ := one.Sub(halfKappa) // W_SR = 1.0 - 0.5 * κ

	rprTerm, _ := wRPR.Mul(rpr) // W_RPR * RPR
	srTerm, _ := wSR.Mul(sr)    // W_SR  * SR

	esi, _ := rprTerm.Add(srTerm)
	return esi
}
