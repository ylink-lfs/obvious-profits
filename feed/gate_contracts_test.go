package feed

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"testing"
	"time"
)

// TestContractCache_Live fetches raw Gate.io USDT-futures contracts JSON and
// prints the response body for inspection.
//
// Run with:
//
//	go test -v -run TestContractCache_Live -timeout 30s ./feed/
func TestContractCache_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live API test in short mode")
	}

	const url = "https://api.gateio.ws/api/v4/futures/usdt/contracts"

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		t.Fatalf("create request: %v", err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("fetch: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}

	t.Logf("status: %s  bytes: %d", resp.Status, len(body))
	fmt.Printf("[ContractCache] raw response:\n%s\n", string(body))
}
