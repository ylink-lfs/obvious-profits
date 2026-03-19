package feed

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/lxzan/gws"
	"golang.org/x/net/proxy"
)

type binanceRawPrinter struct {
	gws.BuiltinEventHandler
	count int
	ctx   context.Context
	done  chan struct{}
}

func (h *binanceRawPrinter) OnOpen(_ *gws.Conn) {
	fmt.Println("[BinanceTickerWS] connected")
}

func (h *binanceRawPrinter) OnClose(_ *gws.Conn, err error) {
	var ce *gws.CloseError
	if err != nil && !(errors.As(err, &ce) && ce.Code == 1000) {
		fmt.Printf("[BinanceTickerWS] closed with error: %v\n", err)
	}
	close(h.done)
}

func (h *binanceRawPrinter) OnMessage(_ *gws.Conn, message *gws.Message) {
	defer message.Close()
	h.count++
	fmt.Printf("[BinanceTickerWS #%d] %s\n", h.count, string(message.Bytes()))
}

// TestBinanceTickerWS_Live connects to Binance futures bookTicker and prints
// raw JSON messages for inspection.
//
// Run with:
//
//	go test -v -run TestBinanceTickerWS_Live -timeout 30s ./feed/
func TestBinanceTickerWS_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live websocket test in short mode")
	}

	const (
		symbol   = "btcusdt"
		duration = 3 * time.Second
	)

	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()

	h := &binanceRawPrinter{ctx: ctx, done: make(chan struct{})}

	uri := "wss://fstream.binance.com/ws/" + symbol + "@bookTicker"
	fmt.Printf("[BinanceTickerWS] connecting to %s\n", uri)

	socket, _, err := gws.NewClient(h, &gws.ClientOption{
		Addr:             uri,
		HandshakeTimeout: 10 * time.Second,
		NewDialer: func() (gws.Dialer, error) {
			return proxy.FromEnvironment(), nil
		},
	})
	if err != nil {
		t.Fatalf("dial error: %v", err)
	}

	go socket.ReadLoop()

	select {
	case <-ctx.Done():
		_ = socket.WriteClose(1000, nil)
		<-h.done
	case <-h.done:
	}

	t.Logf("received %d raw messages", h.count)
	if h.count == 0 {
		t.Error("expected at least one message, got none")
	}
}
