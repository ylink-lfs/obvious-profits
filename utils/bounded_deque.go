package utils

import (
	"sync"

	"github.com/gammazero/deque"
)

// BoundedDeque is a fixed-capacity, thread-safe FIFO buffer backed by
// gammazero/deque.  When the number of elements reaches capacity, the
// oldest element (front) is evicted on each new Push.
type BoundedDeque[T any] struct {
	mu  sync.RWMutex
	d   deque.Deque[T]
	cap int
}

// NewBoundedDeque creates a BoundedDeque with the given maximum capacity.
func NewBoundedDeque[T any](capacity int) *BoundedDeque[T] {
	return &BoundedDeque[T]{cap: capacity}
}

// Push appends v to the back.  If the deque is already at capacity the
// oldest element (front) is silently discarded.
func (bd *BoundedDeque[T]) Push(v T) {
	bd.mu.Lock()
	if bd.d.Len() >= bd.cap {
		bd.d.PopFront()
	}
	bd.d.PushBack(v)
	bd.mu.Unlock()
}

// Len returns the number of elements currently stored.
func (bd *BoundedDeque[T]) Len() int {
	bd.mu.RLock()
	n := bd.d.Len()
	bd.mu.RUnlock()
	return n
}

// At returns the element at index i (0 = oldest / front).
// Caller must ensure 0 <= i < Len(); panics otherwise.
func (bd *BoundedDeque[T]) At(i int) T {
	bd.mu.RLock()
	v := bd.d.At(i)
	bd.mu.RUnlock()
	return v
}

// Back returns the most recently pushed element.
// Panics if the deque is empty.
func (bd *BoundedDeque[T]) Back() T {
	bd.mu.RLock()
	v := bd.d.Back()
	bd.mu.RUnlock()
	return v
}
