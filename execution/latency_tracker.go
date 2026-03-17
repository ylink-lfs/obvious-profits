package execution

import (
	"fmt"
	"strings"
	"sync"
	"time"
)

// LatencyTracker records microsecond-precision timestamps at each pipeline stage.
type LatencyTracker struct {
	mu     sync.Mutex
	marks  []mark
	symbol string
}

type mark struct {
	label string
	ts    time.Time
}

func NewLatencyTracker(symbol string) *LatencyTracker {
	return &LatencyTracker{symbol: symbol}
}

func (lt *LatencyTracker) Reset() {
	lt.mu.Lock()
	defer lt.mu.Unlock()
	lt.marks = lt.marks[:0]
}

func (lt *LatencyTracker) Mark(label string) {
	lt.mu.Lock()
	defer lt.mu.Unlock()
	lt.marks = append(lt.marks, mark{label: label, ts: time.Now()})
}

func (lt *LatencyTracker) Summary() string {
	lt.mu.Lock()
	defer lt.mu.Unlock()
	if len(lt.marks) < 2 {
		return fmt.Sprintf("[Latency:%s] insufficient marks", lt.symbol)
	}
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("[Latency:%s] ", lt.symbol))
	for i := 1; i < len(lt.marks); i++ {
		delta := lt.marks[i].ts.Sub(lt.marks[i-1].ts)
		sb.WriteString(fmt.Sprintf("%s->%s: %v  ", lt.marks[i-1].label, lt.marks[i].label, delta))
	}
	total := lt.marks[len(lt.marks)-1].ts.Sub(lt.marks[0].ts)
	sb.WriteString(fmt.Sprintf("TOTAL: %v", total))
	return sb.String()
}
