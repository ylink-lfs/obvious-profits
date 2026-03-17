package feed

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/bytedance/sonic"
	"github.com/govalues/decimal"
	"github.com/lxzan/gws"

	"obvious-profits/core"
)

type binanceBookTicker struct {
	Symbol   string `json:"s"`
	BidPrice string `json:"b"`
	BidQty   string `json:"B"`
	AskPrice string `json:"a"`
	AskQty   string `json:"A"`
	Time     int64  `json:"T"`
}

// BinanceTickerWS streams Binance futures bookTicker data and emits core.Ticker events.
// If askPrice is non-nil, it is updated atomically on every message so other
// modules can read the latest ask price lock-free without a second connection.
type BinanceTickerWS struct {
	gws.BuiltinEventHandler
	baseURL  string
	symbol   string
	out      chan<- core.Ticker
	askPrice *core.AtomicPrice // optional; nil = disabled
	ctx      context.Context
	done     chan struct{}
	connErr  chan error
}

func NewBinanceTickerWS(baseURL, symbol string, out chan<- core.Ticker, askPrice *core.AtomicPrice) *BinanceTickerWS {
	return &BinanceTickerWS{baseURL: baseURL, symbol: symbol, out: out, askPrice: askPrice}
}

func (b *BinanceTickerWS) OnOpen(socket *gws.Conn) {
	slog.Info("[BinanceTickerWS] connected", "symbol", b.symbol)
}

func (b *BinanceTickerWS) OnClose(socket *gws.Conn, err error) {
	if err != nil {
		select {
		case b.connErr <- fmt.Errorf("binance ticker ws: %w", err):
		default:
		}
	}
	close(b.done)
}

func (b *BinanceTickerWS) OnMessage(socket *gws.Conn, message *gws.Message) {
	defer message.Close()

	localTs := time.Now()
	var bt binanceBookTicker
	if err := sonic.Unmarshal(message.Bytes(), &bt); err != nil {
		slog.Error("[BinanceTickerWS] unmarshal error", "error", err)
		return
	}

	ask, err := decimal.Parse(bt.AskPrice)
	if err != nil {
		slog.Error("[BinanceTickerWS] parse ask price error", "error", err, "raw", bt.AskPrice)
		return
	}
	bid, err := decimal.Parse(bt.BidPrice)
	if err != nil {
		slog.Error("[BinanceTickerWS] parse bid price error", "error", err, "raw", bt.BidPrice)
		return
	}
	askQty, err := decimal.Parse(bt.AskQty)
	if err != nil {
		slog.Error("[BinanceTickerWS] parse ask qty error", "error", err, "raw", bt.AskQty)
		return
	}
	bidQty, err := decimal.Parse(bt.BidQty)
	if err != nil {
		slog.Error("[BinanceTickerWS] parse bid qty error", "error", err, "raw", bt.BidQty)
		return
	}

	ticker := core.Ticker{
		Symbol:     bt.Symbol,
		Bid:        bid,
		BidQty:     bidQty,
		Ask:        ask,
		AskQty:     askQty,
		ExchangeTs: time.UnixMilli(bt.Time),
		LocalTs:    localTs,
	}

	if b.askPrice != nil {
		b.askPrice.Store(ask)
	}

	select {
	case b.out <- ticker:
	case <-b.ctx.Done():
	}
}

func (b *BinanceTickerWS) Run(ctx context.Context) error {
	uri := fmt.Sprintf("%s/%s@bookTicker", b.baseURL, b.symbol)
	slog.Info("[BinanceTickerWS] connecting", "url", uri)

	b.ctx = ctx
	b.done = make(chan struct{})
	b.connErr = make(chan error, 1)

	socket, _, err := gws.NewClient(b, &gws.ClientOption{Addr: uri})
	if err != nil {
		return fmt.Errorf("binance ticker ws dial: %w", err)
	}

	go socket.ReadLoop()

	select {
	case <-ctx.Done():
		_ = socket.WriteClose(1000, nil)
		<-b.done
		return nil
	case <-b.done:
		select {
		case err := <-b.connErr:
			if ctx.Err() != nil {
				return nil
			}
			return err
		default:
			return nil
		}
	}
}
