package execution

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/govalues/decimal"

	"obvious-profits/config"
	"obvious-profits/core"
	"obvious-profits/risk"
)

type OrderType string

const (
	OrderFOK OrderType = "fok"
	OrderIOC OrderType = "ioc"
)

type OrderSide string

const (
	OrderBuy  OrderSide = "buy"
	OrderSell OrderSide = "sell"
)

type OrderRequest struct {
	Symbol  string
	Side    OrderSide
	Type    OrderType
	Price   decimal.Decimal
	SizeUSD decimal.Decimal
	Signal  core.TriggerSignal
	Impact  risk.ImpactResult
}

type OrderResult struct {
	Success   bool
	OrderID   string
	FilledQty decimal.Decimal
	AvgPrice  decimal.Decimal
	Error     string
}

// GateAPI handles authenticated order placement on Gate.io futures.
type GateAPI struct {
	cfg     config.GateConfig
	tracker *LatencyTracker
}

func NewGateAPI(cfg config.GateConfig, tracker *LatencyTracker) *GateAPI {
	return &GateAPI{cfg: cfg, tracker: tracker}
}

// PlaceOrder submits a FOK/IOC order to Gate.io futures.
// TODO: Implement actual Gate.io API v4 authenticated request (HMAC-SHA512).
func (g *GateAPI) PlaceOrder(ctx context.Context, req OrderRequest) OrderResult {
	g.tracker.Mark("order_submit")

	slog.Info("[GateAPI] placing order",
		"side", req.Side, "symbol", req.Symbol,
		"size_usd", req.SizeUSD, "price", req.Price,
		"type", req.Type, "reason", req.Signal.Reason)

	if g.cfg.APIKey == "" || g.cfg.APISecret == "" {
		return OrderResult{Success: false, Error: "API credentials not configured"}
	}

	// TODO: POST /futures/usdt/orders with signed request
	g.tracker.Mark("order_sent")

	return OrderResult{
		Success: false,
		Error:   fmt.Sprintf("TODO: implement Gate.io API call for %s", req.Symbol),
	}
}
