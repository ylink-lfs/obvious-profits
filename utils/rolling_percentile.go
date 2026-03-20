package utils

import (
	"sync"

	"github.com/govalues/decimal"
)

// Funding rate discrete domain: precision 0.0001% (= 0.000001), hard cap ±5%.
// Signed rates map to bucket indices [0, 100000]: index = rate/0.000001 + 50000.
// This preserves long/short directionality: bucket 0 = -0.050000, 50000 = 0, 100000 = +0.050000.
const (
	bitSize    = 100001      // number of discrete signed rate buckets: -0.050000 .. +0.050000
	rateScale  = 6           // decimal places (0.000001 = 1e-6)
	bucketZero = 50000       // bucket index corresponding to rate = 0
	minBucket  = 0           // index 0 = rate -0.050000
	maxBucket  = bitSize - 1 // index 100000 = rate +0.050000
)

// rateToBucket converts a signed funding rate to a Fenwick tree bucket index.
// Mapping: rate / 0.000001 + 50000, clamped to [0, 100000].
// Examples: -0.050000 → 0, 0 → 50000, +0.050000 → 100000.
func rateToBucket(rate decimal.Decimal) int {
	scaled := rate.Rescale(rateScale)
	// Coef() returns uint64 (magnitude); IsNeg() provides the sign.
	coef := int(scaled.Coef())
	if rate.IsNeg() {
		coef = -coef
	}
	idx := coef + bucketZero
	if idx < minBucket {
		idx = minBucket
	}
	if idx > maxBucket {
		idx = maxBucket
	}
	return idx
}

// RollingPercentile is a compound data structure for computing the
// Rolling Percentile Rank (RPR) of funding rate samples in O(log M) time,
// where M = 100001 is the number of discrete signed funding rate buckets.
//
// It combines two internal structures:
//   - Time-based Eviction Queue: a fixed-size circular buffer ([]int)
//     storing bucket indices in insertion order for FIFO eviction.
//   - Fenwick Tree (Binary Indexed Tree): maintains prefix-sum counts
//     over 100001 discrete signed rate buckets for O(log M) rank queries.
//
// Signed bucketing preserves long/short directionality: a high RPR
// indicates the current rate is higher than most historical samples
// (long crowding); a low RPR indicates short crowding.
//
// Typical capacity: 14 days × 24h × 60min = 20160 slots at 1-minute sampling.
type RollingPercentile struct {
	mu    sync.RWMutex
	queue []int            // eviction queue: bucket index per sample (circular buffer)
	bit   [bitSize + 1]int // Fenwick tree, 1-indexed (bit[0] unused)
	size  int              // capacity
	head  int              // next write position in queue
	n     int              // actual stored count, capped at size
}

func NewRollingPercentile(size int) *RollingPercentile {
	return &RollingPercentile{
		queue: make([]int, size),
		size:  size,
	}
}

// fenwickUpdate adds delta to bucket idx (0-indexed).
func (b *RollingPercentile) fenwickUpdate(idx, delta int) {
	for i := idx + 1; i <= bitSize; i += i & (-i) {
		b.bit[i] += delta
	}
}

// fenwickQuery returns the prefix sum for buckets [0, idx] (0-indexed).
// Returns 0 if idx < 0.
func (b *RollingPercentile) fenwickQuery(idx int) int {
	if idx < 0 {
		return 0
	}
	sum := 0
	for i := idx + 1; i > 0; i -= i & (-i) {
		sum += b.bit[i]
	}
	return sum
}

// Push appends a funding rate sample. If the buffer is full, the oldest
// sample is evicted from both the queue and the Fenwick tree before insertion.
func (b *RollingPercentile) Push(rate decimal.Decimal) {
	bucket := rateToBucket(rate)
	b.mu.Lock()
	if b.n == b.size {
		evicted := b.queue[b.head]
		b.fenwickUpdate(evicted, -1)
	}
	b.queue[b.head] = bucket
	b.head = (b.head + 1) % b.size
	b.fenwickUpdate(bucket, 1)
	if b.n < b.size {
		b.n++
	}
	b.mu.Unlock()
}

// Count returns the number of samples currently stored.
func (b *RollingPercentile) Count() int {
	b.mu.RLock()
	n := b.n
	b.mu.RUnlock()
	return n
}

// PercentileRank returns the fraction of stored samples that are strictly
// less than value (signed comparison), as a decimal in [0, 1].
// High RPR (→1) = current rate exceeds most historical samples (long crowding).
// Low RPR (→0) = current rate is below most historical samples (short crowding).
// Uses the Fenwick tree for O(log M) prefix-sum query (M = 100001 buckets).
func (b *RollingPercentile) PercentileRank(value decimal.Decimal) decimal.Decimal {
	b.mu.RLock()
	n := b.n
	if n == 0 {
		b.mu.RUnlock()
		return decimal.Zero
	}

	queryBucket := rateToBucket(value)
	// Count samples in buckets [0, queryBucket-1] (strictly less than value).
	below := b.fenwickQuery(queryBucket - 1)
	b.mu.RUnlock()

	valBelow, _ := decimal.New(int64(below), 0)
	valN, _ := decimal.New(int64(n), 0)
	rank, _ := valBelow.Quo(valN)
	return rank
}
