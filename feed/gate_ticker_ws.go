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

	"obvious-profits/core"
)

// GateTickerWS streams Gate.io futures data over a single WS connection.
// It subscribes to both futures.book_ticker (best bid/ask) and futures.tickers
// (index price, indicative funding rate), emitting Ticker events for book updates
// and storing index/funding fields into the provided AtomicPrice pointers.
type GateTickerWS struct {
	gws.BuiltinEventHandler
	baseURL    string
	symbol     string
	out        chan<- core.Ticker
	indexPrice *core.AtomicPrice // populated from futures.tickers
	indicative *core.AtomicPrice // populated from futures.tickers
	ctx        context.Context
	done       chan struct{}
	connErr    chan error
}

func NewGateTickerWS(baseURL, symbol string, out chan<- core.Ticker, indexPrice, indicative *core.AtomicPrice) *GateTickerWS {
	return &GateTickerWS{
		baseURL:    baseURL,
		symbol:     symbol,
		out:        out,
		indexPrice: indexPrice,
		indicative: indicative,
	}
}

type gateTickerWSMessage struct {
	Time    int64           `json:"time"`
	Channel string          `json:"channel"`
	Event   string          `json:"event"`
	Result  json.RawMessage `json:"result"`
}

type gateBookTicker struct {
	Contract string          `json:"s"`
	BidPrice string          `json:"b"`
	BidSize  decimal.Decimal `json:"B"`
	AskPrice string          `json:"a"`
	AskSize  decimal.Decimal `json:"A"`
	T        int64           `json:"t"`
}

func (g *GateTickerWS) OnOpen(socket *gws.Conn) {
	// Subscribe to futures.book_ticker for best bid/ask
	bookSub := map[string]interface{}{
		"time":    time.Now().Unix(),
		"channel": "futures.book_ticker",
		"event":   "subscribe",
		"payload": []string{g.symbol},
	}
	data, err := sonic.Marshal(bookSub)
	if err != nil {
		slog.Error("[GateTickerWS] marshal book_ticker subscribe error", "error", err)
		return
	}
	if err := socket.WriteMessage(gws.OpcodeText, data); err != nil {
		slog.Error("[GateTickerWS] book_ticker subscribe error", "error", err)
		return
	}
	slog.Info("[GateTickerWS] subscribed", "symbol", g.symbol, "channel", "futures.book_ticker")

	// Subscribe to futures.tickers for index price + indicative funding rate
	tickerSub := map[string]interface{}{
		"time":    time.Now().Unix(),
		"channel": "futures.tickers",
		"event":   "subscribe",
		"payload": []string{g.symbol},
	}
	data, err = sonic.Marshal(tickerSub)
	if err != nil {
		slog.Error("[GateTickerWS] marshal tickers subscribe error", "error", err)
		return
	}
	if err := socket.WriteMessage(gws.OpcodeText, data); err != nil {
		slog.Error("[GateTickerWS] tickers subscribe error", "error", err)
		return
	}
	slog.Info("[GateTickerWS] subscribed", "symbol", g.symbol, "channel", "futures.tickers")
}

func (g *GateTickerWS) OnClose(socket *gws.Conn, err error) {
	if err != nil {
		select {
		case g.connErr <- fmt.Errorf("gate ticker ws: %w", err):
		default:
		}
	}
	close(g.done)
}

type gateTickersResult struct {
	Contract              string `json:"contract"`
	IndexPrice            string `json:"index_price"`
	FundingRateIndicative string `json:"funding_rate_indicative"`
}

func (g *GateTickerWS) OnMessage(socket *gws.Conn, message *gws.Message) {
	defer message.Close()

	localTs := time.Now()
	var envelope gateTickerWSMessage
	if err := sonic.Unmarshal(message.Bytes(), &envelope); err != nil {
		slog.Error("[GateTickerWS] unmarshal envelope error", "error", err)
		return
	}

	if envelope.Event != "update" {
		return
	}

	switch envelope.Channel {
	case "futures.book_ticker":
		g.handleBookTicker(envelope.Result, localTs)
	case "futures.tickers":
		g.handleTickers(envelope.Result)
	}
}

func (g *GateTickerWS) handleBookTicker(raw json.RawMessage, localTs time.Time) {
	var bt gateBookTicker
	if err := sonic.Unmarshal(raw, &bt); err != nil {
		slog.Error("[GateTickerWS] unmarshal book_ticker error", "error", err)
		return
	}

	bidPrice, err := decimal.Parse(bt.BidPrice)
	if err != nil {
		slog.Error("[GateTickerWS] parse bid price error", "error", err)
		return
	}
	askPrice, err := decimal.Parse(bt.AskPrice)
	if err != nil {
		slog.Error("[GateTickerWS] parse ask price error", "error", err)
		return
	}

	ticker := core.Ticker{
		Symbol:     g.symbol,
		Bid:        bidPrice,
		BidQty:     bt.BidSize,
		Ask:        askPrice,
		AskQty:     bt.AskSize,
		ExchangeTs: time.UnixMilli(bt.T),
		LocalTs:    localTs,
	}

	select {
	case g.out <- ticker:
	case <-g.ctx.Done():
	}
}

func (g *GateTickerWS) handleTickers(raw json.RawMessage) {
	// futures.tickers result can be a single object or an array
	var results []gateTickersResult
	if len(raw) > 0 && raw[0] == '[' {
		if err := sonic.Unmarshal(raw, &results); err != nil {
			slog.Error("[GateTickerWS] unmarshal tickers array error", "error", err)
			return
		}
	} else {
		var single gateTickersResult
		if err := sonic.Unmarshal(raw, &single); err != nil {
			slog.Error("[GateTickerWS] unmarshal ticker error", "error", err)
			return
		}
		results = []gateTickersResult{single}
	}

	for _, r := range results {
		if r.IndexPrice != "" {
			if p, err := decimal.Parse(r.IndexPrice); err == nil {
				g.indexPrice.Store(p)
			}
		}
		if r.FundingRateIndicative != "" {
			if p, err := decimal.Parse(r.FundingRateIndicative); err == nil {
				g.indicative.Store(p)
			}
		}
	}
}

func (g *GateTickerWS) Run(ctx context.Context) error {
	slog.Info("[GateTickerWS] connecting", "url", g.baseURL)

	g.ctx = ctx
	g.done = make(chan struct{})
	g.connErr = make(chan error, 1)

	socket, _, err := gws.NewClient(g, &gws.ClientOption{Addr: g.baseURL})
	if err != nil {
		return fmt.Errorf("gate ticker ws dial: %w", err)
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
