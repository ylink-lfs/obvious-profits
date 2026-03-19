package feed

import (
	"testing"
)

// TestGateOrderbookWS_Live connects to Gate.io futures orderbook websocket and
// prints raw JSON messages for inspection.
//
// Run with:
//
//	go test -v -run TestGateOrderbookWS_Live -timeout 30s ./feed/
func TestGateOrderbookWS_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live websocket test in short mode")
	}

	// TODO: Don't implement for now because orderbook constuction logic is not ready yet.
}
