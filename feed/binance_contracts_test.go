package feed

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"testing"
	"time"
)

// TestBinanceDataFeed_ExchangeInfo_Live fetches raw Binance USDT-M futures
// exchange info and prints a summary for inspection.
//
// Run with:
//
//	go test -v -run TestBinanceDataFeed_ExchangeInfo_Live -timeout 30s ./feed/
func TestBinanceDataFeed_ExchangeInfo_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live API test in short mode")
	}

	const url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
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
	// Print first 2000 bytes to avoid flooding output
	if len(body) > 2000 {
		fmt.Printf("[ExchangeInfo] raw response (first 2000 bytes):\n%s\n...\n", string(body[:2000]))
	} else {
		fmt.Printf("[ExchangeInfo] raw response:\n%s\n", string(body))
	}
}

// TestBinanceDataFeed_Ticker24h_Live fetches raw Binance 24hr ticker data.
//
// Run with:
//
//	go test -v -run TestBinanceDataFeed_Ticker24h_Live -timeout 30s ./feed/
func TestBinanceDataFeed_Ticker24h_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live API test in short mode")
	}

	const url = "https://fapi.binance.com/fapi/v1/ticker/24hr"

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
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
	if len(body) > 2000 {
		fmt.Printf("[Ticker24h] raw response (first 2000 bytes):\n%s\n...\n", string(body[:2000]))
	} else {
		fmt.Printf("[Ticker24h] raw response:\n%s\n", string(body))
	}
}

// TestBinanceDataFeed_PremiumIndex_Live fetches raw Binance premium index data.
//
// Run with:
//
//	go test -v -run TestBinanceDataFeed_PremiumIndex_Live -timeout 30s ./feed/
func TestBinanceDataFeed_PremiumIndex_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live API test in short mode")
	}

	const url = "https://fapi.binance.com/fapi/v1/premiumIndex"

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
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
	if len(body) > 2000 {
		fmt.Printf("[PremiumIndex] raw response (first 2000 bytes):\n%s\n...\n", string(body[:2000]))
	} else {
		fmt.Printf("[PremiumIndex] raw response:\n%s\n", string(body))
	}
}
