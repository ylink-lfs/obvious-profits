package feed

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/lxzan/gws"
	"golang.org/x/net/proxy"

	"obvious-profits/utils"
)

type markPriceRawPrinter struct {
	gws.BuiltinEventHandler
	count int
	ctx   context.Context
	done  chan struct{}
}

func (h *markPriceRawPrinter) OnOpen(_ *gws.Conn) {
	fmt.Println("[BinanceMarkPriceWS] connected")
}

func (h *markPriceRawPrinter) OnClose(_ *gws.Conn, err error) {
	if err != nil && !utils.IsNormalWSClose(err) {
		fmt.Printf("[BinanceMarkPriceWS] closed with error: %v\n", err)
	}
	close(h.done)
}

func (h *markPriceRawPrinter) OnMessage(_ *gws.Conn, message *gws.Message) {
	defer message.Close()
	h.count++
	fmt.Printf("[BinanceMarkPriceWS #%d] %s\n", h.count, string(message.Bytes()))
}

// TestBinanceMarkPriceWS_Live connects to Binance futures markPrice stream
// and prints raw JSON messages for inspection.
//
// Run with:
//
//	go test -v -run TestBinanceMarkPriceWS_Live -timeout 30s ./feed/
func TestBinanceMarkPriceWS_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live websocket test in short mode")
	}

	const (
		symbol   = "btcusdt"
		duration = 5 * time.Second
	)

	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()

	h := &markPriceRawPrinter{ctx: ctx, done: make(chan struct{})}

	uri := "wss://fstream.binance.com/ws/" + symbol + "@markPrice"
	fmt.Printf("[BinanceMarkPriceWS] connecting to %s\n", uri)

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
