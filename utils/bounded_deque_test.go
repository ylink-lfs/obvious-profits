package utils

import (
	"sync"
	"testing"
)

func TestBoundedDeque_CapacityOne(t *testing.T) {
	bd := NewBoundedDeque[int](1)

	bd.Push(10)
	if bd.Len() != 1 || bd.Back() != 10 {
		t.Fatal("single push failed")
	}

	bd.Push(20)
	if bd.Len() != 1 {
		t.Fatalf("expected Len 1, got %d", bd.Len())
	}
	if bd.At(0) != 20 {
		t.Fatalf("expected At(0)==20 after eviction, got %d", bd.At(0))
	}
	if bd.Back() != 20 {
		t.Fatalf("expected Back()==20, got %d", bd.Back())
	}

	// Third push: still only the latest survives.
	bd.Push(30)
	if bd.Len() != 1 || bd.At(0) != 30 || bd.Back() != 30 {
		t.Fatal("cap-1 deque should always hold only the latest element")
	}
}

func TestBoundedDeque_EvictionOrdering(t *testing.T) {
	bd := NewBoundedDeque[int](3)
	for i := range 3 {
		bd.Push(i) // [0, 1, 2]
	}

	bd.Push(3) // evict 0 -> [1, 2, 3]
	if bd.At(0) != 1 {
		t.Fatalf("front should be 1 after eviction, got %d", bd.At(0))
	}
	if bd.Back() != 3 {
		t.Fatalf("back should be 3, got %d", bd.Back())
	}

	bd.Push(4) // evict 1 -> [2, 3, 4]
	bd.Push(5) // evict 2 -> [3, 4, 5]
	for i := range 3 {
		want := i + 3
		if bd.At(i) != want {
			t.Fatalf("At(%d)=%d, want %d", i, bd.At(i), want)
		}
	}
}

func TestBoundedDeque_BackEmptyPanics(t *testing.T) {
	bd := NewBoundedDeque[int](5)
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("Back() on empty deque should panic")
		}
	}()
	bd.Back()
}

func TestBoundedDeque_AtOutOfBoundsPanics(t *testing.T) {
	bd := NewBoundedDeque[int](5)
	bd.Push(1)

	t.Run("index_equals_len", func(t *testing.T) {
		defer func() {
			if r := recover(); r == nil {
				t.Fatal("At(Len()) should panic")
			}
		}()
		bd.At(bd.Len())
	})

	t.Run("negative_index", func(t *testing.T) {
		defer func() {
			if r := recover(); r == nil {
				t.Fatal("At(-1) should panic")
			}
		}()
		bd.At(-1)
	})
}

func TestBoundedDeque_LenPinnedAtCapacity(t *testing.T) {
	const cap = 4
	bd := NewBoundedDeque[int](cap)
	for i := range cap * 3 {
		bd.Push(i)
		if bd.Len() > cap {
			t.Fatalf("Len %d exceeded capacity %d", bd.Len(), cap)
		}
	}
	if bd.Len() != cap {
		t.Fatalf("Len should be %d, got %d", cap, bd.Len())
	}
}

func TestBoundedDeque_ExactCapacityNoEviction(t *testing.T) {
	const cap = 5
	bd := NewBoundedDeque[int](cap)
	for i := range cap {
		bd.Push(i * 10)
	}
	if bd.Len() != cap {
		t.Fatalf("Len %d != cap %d", bd.Len(), cap)
	}
	for i := range cap {
		want := i * 10
		if bd.At(i) != want {
			t.Fatalf("At(%d)=%d, want %d", i, bd.At(i), want)
		}
	}
}

func TestBoundedDeque_ConcurrentSafety(t *testing.T) {
	const (
		cap      = 64
		writers  = 8
		readers  = 8
		opsPerGo = 1000
	)
	bd := NewBoundedDeque[int](cap)
	for i := range cap {
		bd.Push(i)
	}

	var startWg, doneWg sync.WaitGroup
	startWg.Add(1)
	doneWg.Add(writers + readers)

	for w := range writers {
		go func() {
			defer doneWg.Done()
			startWg.Wait()
			for i := range opsPerGo {
				bd.Push(w*opsPerGo + i)
			}
		}()
	}

	for range readers {
		go func() {
			defer doneWg.Done()
			startWg.Wait()
			for range opsPerGo {
				_ = bd.Len()
				_ = bd.Back()
			}
		}()
	}

	startWg.Done()
	doneWg.Wait()

	if bd.Len() != cap {
		t.Fatalf("Len should be %d after concurrent ops, got %d", cap, bd.Len())
	}
}

func TestBoundedDeque_ConcurrentPushAtEviction(t *testing.T) {
	const (
		cap      = 4
		writers  = 4
		readers  = 4
		opsPerGo = 2000
	)
	bd := NewBoundedDeque[int](cap)
	for i := range cap {
		bd.Push(i)
	}

	var startWg, doneWg sync.WaitGroup
	startWg.Add(1)
	doneWg.Add(writers + readers)

	for w := range writers {
		go func() {
			defer doneWg.Done()
			startWg.Wait()
			for i := range opsPerGo {
				bd.Push(w*opsPerGo + i)
			}
		}()
	}

	for range readers {
		go func() {
			defer doneWg.Done()
			startWg.Wait()
			for range opsPerGo {
				_ = bd.At(0)
			}
		}()
	}

	startWg.Done()
	doneWg.Wait()

	if bd.Len() != cap {
		t.Fatalf("Len should be %d after concurrent eviction, got %d", cap, bd.Len())
	}
}
