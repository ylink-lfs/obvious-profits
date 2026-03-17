package feed

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	"github.com/bytedance/sonic"
	"github.com/govalues/decimal"
	"github.com/lxzan/gws"

	"obvious-profits/memory"
)

// GateOrderbookWS streams Gate.io futures full orderbook snapshots
// and applies them to a local L2Book.
//
// Subscribes to the "futures.order_book" channel in full-snapshot mode.
// For the skeleton stage this uses repeated full snapshots (level="20", accuracy="0").
// Incremental construction will be added in the future.
type GateOrderbookWS struct {
	gws.BuiltinEventHandler
	baseURL string
	symbol  string
	book    *memory.L2Book
	done    chan struct{}
	connErr chan error
}

func NewGateOrderbookWS(baseURL, symbol string, book *memory.L2Book) *GateOrderbookWS {
	return &GateOrderbookWS{baseURL: baseURL, symbol: symbol, book: book}
}

type gateOrderBookMsg struct {
	Time    int64           `json:"time"`
	Channel string          `json:"channel"`
	Event   string          `json:"event"`
	Result  json.RawMessage `json:"result"`
}

type gateOrderBookSnapshot struct {
	Contract string          `json:"contract"`
	Asks     []gateBookLevel `json:"asks"`
	Bids     []gateBookLevel `json:"bids"`
}

type gateBookLevel struct {
	Price string          `json:"p"`
	Size  decimal.Decimal `json:"s"`
}

func (g *GateOrderbookWS) OnOpen(socket *gws.Conn) {
	// Subscribe: futures.order_book with 20 levels, accuracy "0" (no grouping)
	sub := map[string]interface{}{
		"time":    time.Now().Unix(),
		"channel": "futures.order_book",
		"event":   "subscribe",
		"payload": []string{g.symbol, "20", "0"},
	}
	data, err := sonic.Marshal(sub)
	if err != nil {
		slog.Error("[GateOrderbookWS] marshal subscribe error", "error", err)
		return
	}
	if err := socket.WriteMessage(gws.OpcodeText, data); err != nil {
		slog.Error("[GateOrderbookWS] subscribe error", "error", err)
		return
	}
	slog.Info("[GateOrderbookWS] subscribed", "symbol", g.symbol, "levels", 20)
}

func (g *GateOrderbookWS) OnClose(socket *gws.Conn, err error) {
	if err != nil {
		select {
		case g.connErr <- fmt.Errorf("gate orderbook ws: %w", err):
		default:
		}
	}
	close(g.done)
}

func (g *GateOrderbookWS) OnMessage(socket *gws.Conn, message *gws.Message) {
	defer message.Close()

	var envelope gateOrderBookMsg
	if err := sonic.Unmarshal(message.Bytes(), &envelope); err != nil {
		slog.Error("[GateOrderbookWS] unmarshal envelope error", "error", err)
		return
	}

	if envelope.Channel != "futures.order_book" {
		return
	}

	// "all" = full snapshot, "update" = incremental delta
	switch envelope.Event {
	case "all":
		g.applySnapshot(envelope.Result)
	case "update":
		// For skeleton stage, also treat updates as full replace.
		// Future: apply incremental deltas properly.
		g.applySnapshot(envelope.Result)
	}
}

func (g *GateOrderbookWS) Run(ctx context.Context) error {
	slog.Info("[GateOrderbookWS] connecting", "url", g.baseURL)

	g.done = make(chan struct{})
	g.connErr = make(chan error, 1)

	socket, _, err := gws.NewClient(g, &gws.ClientOption{Addr: g.baseURL})
	if err != nil {
		return fmt.Errorf("gate orderbook ws dial: %w", err)
	}

	go socket.ReadLoop()

	select {
	case <-ctx.Done():
		_ = socket.WriteClose(1000, nil)
		<-g.done
		return nil
	case <-g.done:
		select {
		case err := <-g.connErr:
			if ctx.Err() != nil {
				return nil
			}
			return err
		default:
			return nil
		}
	}
}

func (g *GateOrderbookWS) applySnapshot(raw json.RawMessage) {
	var snap gateOrderBookSnapshot
	if err := sonic.Unmarshal(raw, &snap); err != nil {
		slog.Error("[GateOrderbookWS] unmarshal snapshot error", "error", err)
		return
	}

	bids := make([]memory.Level, 0, len(snap.Bids))
	for _, l := range snap.Bids {
		price, err := decimal.Parse(l.Price)
		if err != nil {
			slog.Error("[GateOrderbookWS] parse bid price error", "error", err, "raw", l.Price)
			continue
		}
		bids = append(bids, memory.Level{Price: price, Qty: l.Size})
	}

	asks := make([]memory.Level, 0, len(snap.Asks))
	for _, l := range snap.Asks {
		price, err := decimal.Parse(l.Price)
		if err != nil {
			slog.Error("[GateOrderbookWS] parse ask price error", "error", err, "raw", l.Price)
			continue
		}
		asks = append(asks, memory.Level{Price: price, Qty: l.Size})
	}

	g.book.ReplaceAll(bids, asks)
}
