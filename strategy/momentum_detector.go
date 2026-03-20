package strategy

import (
	"time"

	"obvious-profits/core"
	"obvious-profits/utils"
)

// MomentumDetector maintains a sliding window of SpreadSnapshots and
// detects right-side momentum exhaustion patterns (spread converging
// back toward zero, indicating premium collapse).
type MomentumDetector struct {
	buf *utils.BoundedDeque[core.SpreadSnapshot]
}

// NewMomentumDetector creates a detector with the given window size.
func NewMomentumDetector(windowSize int) *MomentumDetector {
	return &MomentumDetector{buf: utils.NewBoundedDeque[core.SpreadSnapshot](windowSize)}
}

// Push records a new spread snapshot into the sliding window.
func (m *MomentumDetector) Push(snap core.SpreadSnapshot) {
	m.buf.Push(snap)
}

// Detect checks whether the spread is converging back toward zero
// (right-side confirmation that the premium is collapsing).
// Current heuristic: monotonic spread contraction over the 3 most recent
// snapshots.
// TODO: Implement proper pattern detection (trend break, volume dry-up, engulfing).
func (m *MomentumDetector) Detect(symbol string) *core.TriggerSignal {
	n := m.buf.Len()
	if n < 3 {
		return nil
	}

	// Check the 3 most recent snapshots for monotonic spread contraction,
	// using At() to avoid heap allocation.
	declining := true
	for i := n - 2; i < n; i++ {
		if m.buf.At(i).SpreadPct.Abs().Cmp(m.buf.At(i-1).SpreadPct.Abs()) >= 0 {
			declining = false
			break
		}
	}
	if !declining {
		return nil
	}

	first := m.buf.At(n - 3)
	direction := core.TriggerShort
	if first.SpreadPct.IsNeg() {
		direction = core.TriggerLong
	}

	return &core.TriggerSignal{
		Symbol:    symbol,
		Direction: direction,
		Snapshot:  first,
		Reason:    "spread monotonic contraction over sliding window",
		Ts:        time.Now(),
	}
}
