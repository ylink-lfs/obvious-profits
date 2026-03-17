package strategy

import (
	"sync"
	"time"

	"obvious-profits/core"
)

// RingBuffer maintains a fixed-size sliding window of SpreadSnapshots
// for detecting right-side momentum exhaustion patterns.
type RingBuffer struct {
	mu   sync.RWMutex
	data []core.SpreadSnapshot
	size int
	head int
	full bool
}

func NewRingBuffer(size int) *RingBuffer {
	return &RingBuffer{data: make([]core.SpreadSnapshot, size), size: size}
}

func (r *RingBuffer) Push(snap core.SpreadSnapshot) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.data[r.head] = snap
	r.head = (r.head + 1) % r.size
	if r.head == 0 {
		r.full = true
	}
}

func (r *RingBuffer) Window() []core.SpreadSnapshot {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if !r.full {
		result := make([]core.SpreadSnapshot, r.head)
		copy(result, r.data[:r.head])
		return result
	}
	result := make([]core.SpreadSnapshot, r.size)
	copy(result, r.data[r.head:])
	copy(result[r.size-r.head:], r.data[:r.head])
	return result
}

// DetectMomentumExhaustion checks whether the spread is converging back
// toward zero (right-side confirmation that the premium is collapsing).
// TODO: Implement proper pattern detection (trend break, volume dry-up, engulfing).
// Current placeholder checks for monotonic spread contraction.
func (r *RingBuffer) DetectMomentumExhaustion(symbol string) *core.TriggerSignal {
	window := r.Window()
	if len(window) < 3 {
		return nil
	}

	n := len(window)
	recent := window[n-3:]

	declining := true
	for i := 1; i < len(recent); i++ {
		if recent[i].SpreadPct.Abs().Cmp(recent[i-1].SpreadPct.Abs()) >= 0 {
			declining = false
			break
		}
	}
	if !declining {
		return nil
	}

	direction := core.TriggerShort
	if recent[0].SpreadPct.IsNeg() {
		direction = core.TriggerLong
	}

	return &core.TriggerSignal{
		Symbol:    symbol,
		Direction: direction,
		Snapshot:  recent[0],
		Reason:    "spread monotonic contraction over sliding window",
		Ts:        time.Now(),
	}
}
