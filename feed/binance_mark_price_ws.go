package feed

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/bytedance/sonic"
	"github.com/govalues/decimal"
	"github.com/lxzan/gws"

	"obvious-profits/core"
)

type binanceMarkPriceEvent struct {
	Event       string `json:"e"` // "markPriceUpdate"
	EventTime   int64  `json:"E"` // event time (ms)
	Symbol      string `json:"s"`
	MarkPrice   string `json:"p"`
	IndexPrice  string `json:"i"`
	FundingRate string `json:"r"` // estimated funding rate (not yet settled)
	NextFunding int64  `json:"T"` // next funding time (ms)
}

// BinanceMarkPriceWS streams Binance futures @markPrice data for a single symbol.
// It stores mark price, index price, and estimated funding rate into the provided
// AtomicPrice pointers for lock-free reads by other modules.
type BinanceMarkPriceWS struct {
	gws.BuiltinEventHandler
	baseURL     string
	symbol      string
	markPrice   *core.AtomicPrice
	indexPrice  *core.AtomicPrice
	fundingRate *core.AtomicPrice
	ctx         context.Context
	done        chan struct{}
	connErr     chan error
}

func NewBinanceMarkPriceWS(baseURL, symbol string, markPrice, indexPrice, fundingRate *core.AtomicPrice) *BinanceMarkPriceWS {
	return &BinanceMarkPriceWS{
		baseURL:     baseURL,
		symbol:      symbol,
		markPrice:   markPrice,
		indexPrice:  indexPrice,
		fundingRate: fundingRate,
	}
}

func (b *BinanceMarkPriceWS) OnOpen(socket *gws.Conn) {
	slog.Info("[BinanceMarkPriceWS] connected", "symbol", b.symbol)
}

func (b *BinanceMarkPriceWS) OnClose(socket *gws.Conn, err error) {
	if err != nil {
		select {
		case b.connErr <- fmt.Errorf("binance mark price ws: %w", err):
		default:
		}
	}
	close(b.done)
}

func (b *BinanceMarkPriceWS) OnMessage(socket *gws.Conn, message *gws.Message) {
	defer message.Close()

	var ev binanceMarkPriceEvent
	if err := sonic.Unmarshal(message.Bytes(), &ev); err != nil {
		slog.Error("[BinanceMarkPriceWS] unmarshal error", "error", err)
		return
	}

	if ev.MarkPrice != "" {
		if p, err := decimal.Parse(ev.MarkPrice); err == nil {
			b.markPrice.Store(p)
		}
	}
	if ev.IndexPrice != "" {
		if p, err := decimal.Parse(ev.IndexPrice); err == nil {
			b.indexPrice.Store(p)
		}
	}
	if ev.FundingRate != "" {
		if p, err := decimal.Parse(ev.FundingRate); err == nil {
			b.fundingRate.Store(p)
		}
	}
}

func (b *BinanceMarkPriceWS) Run(ctx context.Context) error {
	uri := fmt.Sprintf("%s/%s@markPrice", b.baseURL, b.symbol)
	slog.Info("[BinanceMarkPriceWS] connecting", "url", uri)

	b.ctx = ctx
	b.done = make(chan struct{})
	b.connErr = make(chan error, 1)

	socket, _, err := gws.NewClient(b, &gws.ClientOption{Addr: uri})
	if err != nil {
		return fmt.Errorf("binance mark price ws dial: %w", err)
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
