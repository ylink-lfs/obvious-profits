package feed

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/bytedance/sonic"
	"github.com/lxzan/gws"
	"golang.org/x/net/proxy"

	"obvious-profits/utils"
)

type gateTickerRawPrinter struct {
	gws.BuiltinEventHandler
	symbol string
	count  int
	done   chan struct{}
}

func (h *gateTickerRawPrinter) OnOpen(socket *gws.Conn) {
	for _, channel := range []string{"futures.book_ticker", "futures.tickers"} {
		sub := map[string]interface{}{
			"time":    time.Now().Unix(),
			"channel": channel,
			"event":   "subscribe",
			"payload": []string{h.symbol},
		}
		data, _ := sonic.Marshal(sub)
		_ = socket.WriteMessage(gws.OpcodeText, data)
		fmt.Printf("[GateTickerWS] subscribed to %s / %s\n", h.symbol, channel)
	}
}

func (h *gateTickerRawPrinter) OnClose(_ *gws.Conn, err error) {
	if err != nil && !utils.IsNormalWSClose(err) {
		fmt.Printf("[GateTickerWS] closed with error: %v\n", err)
	}
	close(h.done)
}

func (h *gateTickerRawPrinter) OnMessage(_ *gws.Conn, message *gws.Message) {
	defer message.Close()
	h.count++
	fmt.Printf("[GateTickerWS #%d] %s\n", h.count, string(message.Bytes()))
}

// TestGateTickerWS_Live connects to Gate.io futures websocket, subscribes to
// book_ticker and tickers channels, and prints raw JSON messages for inspection.
//
// Run with:
//
//	go test -v -run TestGateTickerWS_Live -timeout 30s ./feed/
func TestGateTickerWS_Live(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping live websocket test in short mode")
	}

	const (
		baseURL  = "wss://fx-ws.gateio.ws/v4/ws/usdt"
		symbol   = "BTC_USDT"
		duration = 3 * time.Second
	)

	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()

	h := &gateTickerRawPrinter{symbol: symbol, done: make(chan struct{})}

	fmt.Printf("[GateTickerWS] connecting to %s\n", baseURL)
	socket, _, err := gws.NewClient(h, &gws.ClientOption{
		Addr:             baseURL,
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
