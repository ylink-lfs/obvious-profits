package utils

import (
	"sync"
	"testing"

	"github.com/govalues/decimal"
)

func mustDecimal(s string) decimal.Decimal {
	d, err := decimal.Parse(s)
	if err != nil {
		panic("bad decimal literal: " + s)
	}
	return d
}

// --- rateToBucket (unexported, same package) ---

func TestRateToBucket_Zero(t *testing.T) {
	if got := rateToBucket(decimal.Zero); got != bucketZero {
		t.Fatalf("rateToBucket(0) = %d, want %d", got, bucketZero)
	}
}

func TestRateToBucket_Symmetry(t *testing.T) {
	pos := mustDecimal("0.001000")
	neg := mustDecimal("-0.001000")
	bp := rateToBucket(pos)
	bn := rateToBucket(neg)
	// Both should be equidistant from center.
	if (bp - bucketZero) != (bucketZero - bn) {
		t.Fatalf("asymmetric: pos bucket %d, neg bucket %d, center %d", bp, bn, bucketZero)
	}
}

func TestRateToBucket_ClampExtreme(t *testing.T) {
	extremePositive := mustDecimal("0.100000") // 10%, well above +5% cap
	if got := rateToBucket(extremePositive); got != maxBucket {
		t.Fatalf("rateToBucket(0.1) = %d, want maxBucket %d", got, maxBucket)
	}
	extremeNegative := mustDecimal("-0.100000")
	if got := rateToBucket(extremeNegative); got != minBucket {
		t.Fatalf("rateToBucket(-0.1) = %d, want minBucket %d", got, minBucket)
	}
}

func TestRateToBucket_ExactBoundaries(t *testing.T) {
	// Exactly at +5% and -5% should hit the boundary buckets, not be clamped.
	pos := mustDecimal("0.050000")
	neg := mustDecimal("-0.050000")
	if got := rateToBucket(pos); got != maxBucket {
		t.Fatalf("rateToBucket(+0.05) = %d, want %d", got, maxBucket)
	}
	if got := rateToBucket(neg); got != minBucket {
		t.Fatalf("rateToBucket(-0.05) = %d, want %d", got, minBucket)
	}
}

// --- RollingPercentile ---

func TestRollingPercentile_EmptyPercentileRank(t *testing.T) {
	rp := NewRollingPercentile(100)
	rank := rp.PercentileRank(mustDecimal("0.0001"))
	if !rank.IsZero() {
		t.Fatalf("expected 0 for empty buffer, got %s", rank)
	}
}

func TestRollingPercentile_SingleSample(t *testing.T) {
	rp := NewRollingPercentile(10)
	rp.Push(mustDecimal("0.0001"))

	// Same value: midrank = (0 + 0.5*1)/1 = 0.5.
	rank := rp.PercentileRank(mustDecimal("0.0001"))
	want := mustDecimal("0.5")
	if rank.Cmp(want) != 0 {
		t.Fatalf("same value rank should be 0.5, got %s", rank)
	}

	// Value above: midrank = (1 + 0)/1 = 1.
	rank = rp.PercentileRank(mustDecimal("0.001"))
	want = mustDecimal("1")
	if rank.Cmp(want) != 0 {
		t.Fatalf("above rank should be 1, got %s", rank)
	}

	// Value below: midrank = (0 + 0)/1 = 0.
	rank = rp.PercentileRank(mustDecimal("-0.001"))
	if !rank.IsZero() {
		t.Fatalf("below rank should be 0, got %s", rank)
	}
}

func TestRollingPercentile_AllIdenticalSamples(t *testing.T) {
	rp := NewRollingPercentile(50)
	rate := mustDecimal("0.0003")
	for range 50 {
		rp.Push(rate)
	}
	// Midrank: (0 + 0.5*50)/50 = 0.5 (neutral, not extreme).
	rank := rp.PercentileRank(rate)
	want := mustDecimal("0.5")
	if rank.Cmp(want) != 0 {
		t.Fatalf("identical samples: rank should be 0.5, got %s", rank)
	}
}

func TestRollingPercentile_EvictionFullReplacement(t *testing.T) {
	const cap = 5
	rp := NewRollingPercentile(cap)

	low := mustDecimal("-0.001")
	high := mustDecimal("0.001")

	// Fill entirely with low rate.
	for i := 0; i < cap; i++ {
		rp.Push(low)
	}

	// Fully replace with high rate.
	for i := 0; i < cap; i++ {
		rp.Push(high)
	}

	// All samples are now high. Midrank = (0 + 0.5*5)/5 = 0.5.
	rank := rp.PercentileRank(high)
	want := mustDecimal("0.5")
	if rank.Cmp(want) != 0 {
		t.Fatalf("after full replacement, rank of high should be 0.5, got %s", rank)
	}

	// Rank of low should also be 0 (low is below all stored high samples).
	rank = rp.PercentileRank(low)
	if !rank.IsZero() {
		t.Fatalf("rank of low should be 0 (below all), got %s", rank)
	}

	// A value above high should have rank 1 (all 5 samples strictly less).
	rank = rp.PercentileRank(mustDecimal("0.01"))
	want = mustDecimal("1")
	if rank.Cmp(want) != 0 {
		t.Fatalf("rank above all should be 1, got %s", rank)
	}
}

func TestRollingPercentile_CountPartialFill(t *testing.T) {
	rp := NewRollingPercentile(100)
	for i := 0; i < 7; i++ {
		rp.Push(mustDecimal("0.0001"))
	}
	if rp.Count() != 7 {
		t.Fatalf("Count() = %d, want 7", rp.Count())
	}
}

func TestRollingPercentile_CountPinnedAtCapacity(t *testing.T) {
	const cap = 10
	rp := NewRollingPercentile(cap)
	for i := 0; i < cap*3; i++ {
		rp.Push(mustDecimal("0.0001"))
	}
	if rp.Count() != cap {
		t.Fatalf("Count() = %d, want %d", rp.Count(), cap)
	}
}

func TestRollingPercentile_CapacityOneWindow(t *testing.T) {
	rp := NewRollingPercentile(1)

	rp.Push(mustDecimal("-0.001"))
	if rp.Count() != 1 {
		t.Fatalf("Count should be 1, got %d", rp.Count())
	}

	// Push a higher rate — evicts the old one.
	rp.Push(mustDecimal("0.001"))
	if rp.Count() != 1 {
		t.Fatalf("Count should still be 1, got %d", rp.Count())
	}

	// Only the new high sample exists; rank of a value above it should be 1.
	rank := rp.PercentileRank(mustDecimal("0.01"))
	want := mustDecimal("1")
	if rank.Cmp(want) != 0 {
		t.Fatalf("rank above sole sample should be 1, got %s", rank)
	}

	// Rank of exact sole sample: midrank = (0 + 0.5*1)/1 = 0.5.
	rank = rp.PercentileRank(mustDecimal("0.001"))
	want = mustDecimal("0.5")
	if rank.Cmp(want) != 0 {
		t.Fatalf("rank of exact sole sample should be 0.5, got %s", rank)
	}
}

func TestRollingPercentile_ExtremeRatesNosPanic(t *testing.T) {
	rp := NewRollingPercentile(5)
	// Push rates far beyond ±5% cap — should be clamped, not panic.
	rp.Push(mustDecimal("0.500000"))
	rp.Push(mustDecimal("-0.500000"))
	if rp.Count() != 2 {
		t.Fatalf("Count should be 2, got %d", rp.Count())
	}
	// The two samples land in min and max buckets.
	// Rank of 0 (midpoint): 1 sample in minBucket is strictly less → rank 0.5.
	rank := rp.PercentileRank(decimal.Zero)
	want := mustDecimal("0.5")
	if rank.Cmp(want) != 0 {
		t.Fatalf("rank of zero between extremes should be 0.5, got %s", rank)
	}
}

// --- Concurrency ---

func TestRollingPercentile_ConcurrentPushAndRank(t *testing.T) {
	const (
		cap     = 100
		writers = 4
		readers = 4
		ops     = 500
	)
	rp := NewRollingPercentile(cap)

	rates := []decimal.Decimal{
		mustDecimal("-0.001000"),
		mustDecimal("0.000000"),
		mustDecimal("0.000100"),
		mustDecimal("0.001000"),
	}

	var wg sync.WaitGroup
	wg.Add(writers + readers)

	// Concurrent writers: push a mix of rates.
	for w := 0; w < writers; w++ {
		w := w
		go func() {
			defer wg.Done()
			for i := 0; i < ops; i++ {
				rp.Push(rates[(w+i)%len(rates)])
			}
		}()
	}

	// Concurrent readers: call PercentileRank + Count while pushes happen.
	for r := 0; r < readers; r++ {
		r := r
		go func() {
			defer wg.Done()
			for i := 0; i < ops; i++ {
				rank := rp.PercentileRank(rates[(r+i)%len(rates)])
				// Rank must always be in [0, 1].
				if rank.Cmp(decimal.Zero) < 0 || rank.Cmp(decimal.One) > 0 {
					t.Errorf("rank out of [0,1]: %s", rank)
					return
				}
				n := rp.Count()
				if n < 0 || n > cap {
					t.Errorf("count out of range: %d", n)
					return
				}
			}
		}()
	}

	wg.Wait()

	// After all writers finish, count must be exactly min(total_pushes, cap).
	totalPushes := writers * ops
	wantCount := totalPushes
	if wantCount > cap {
		wantCount = cap
	}
	if got := rp.Count(); got != wantCount {
		t.Fatalf("final Count = %d, want %d", got, wantCount)
	}
}

func TestRollingPercentile_PartialEviction(t *testing.T) {
	const cap = 5
	rp := NewRollingPercentile(cap)

	// Push 7 distinct ascending rates into a cap-5 buffer.
	// After 7 pushes, only the last 5 remain: {0.000, 0.001, 0.002, 0.003, 0.004}.
	for _, r := range []string{"-0.002000", "-0.001000", "0.000000", "0.001000", "0.002000", "0.003000", "0.004000"} {
		rp.Push(mustDecimal(r))
	}

	if rp.Count() != cap {
		t.Fatalf("Count = %d, want %d", rp.Count(), cap)
	}

	// Evicted value: rank of -0.002 should be 0 (below all remaining samples).
	rank := rp.PercentileRank(mustDecimal("-0.002000"))
	if !rank.IsZero() {
		t.Fatalf("rank of evicted low value should be 0, got %s", rank)
	}

	// Middle of window: midrank(0.002) = (2*2 + 1) / (2*5) = 0.5.
	rank = rp.PercentileRank(mustDecimal("0.002000"))
	want := mustDecimal("0.5")
	if rank.Cmp(want) != 0 {
		t.Fatalf("rank of mid-window value should be 0.5, got %s", rank)
	}

	// Top of window: midrank(0.004) = (2*4 + 1) / (2*5) = 0.9.
	rank = rp.PercentileRank(mustDecimal("0.004000"))
	want = mustDecimal("0.9")
	if rank.Cmp(want) != 0 {
		t.Fatalf("rank of highest in window should be 0.9, got %s", rank)
	}
}

func TestRateToBucket_SubBucketPrecision(t *testing.T) {
	// Inputs with precision finer than 1e-6 are rounded via half-even by Rescale.
	// Pin this behavior to detect any change in the decimal library.

	// 0.0010009 rounds to 0.001001 (digit beyond 1e-6 is 9 > 5 → round up).
	got := rateToBucket(mustDecimal("0.0010009"))
	wantBucket := rateToBucket(mustDecimal("0.001001"))
	if got != wantBucket {
		t.Fatalf("rateToBucket(0.0010009) = %d, want %d (same as 0.001001)", got, wantBucket)
	}

	// 0.0010005 rounds to 0.001000 (half-even: 1000 is even → stays).
	got = rateToBucket(mustDecimal("0.0010005"))
	wantBucket = rateToBucket(mustDecimal("0.001000"))
	if got != wantBucket {
		t.Fatalf("rateToBucket(0.0010005) = %d, want %d (same as 0.001000)", got, wantBucket)
	}

	// Negative: -0.0010009 rounds to -0.001001.
	got = rateToBucket(mustDecimal("-0.0010009"))
	wantBucket = rateToBucket(mustDecimal("-0.001001"))
	if got != wantBucket {
		t.Fatalf("rateToBucket(-0.0010009) = %d, want %d (same as -0.001001)", got, wantBucket)
	}
}
