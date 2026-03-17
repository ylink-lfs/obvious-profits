package config

import (
	"fmt"
	"os"

	"github.com/govalues/decimal"
	"gopkg.in/yaml.v3"
)

type Config struct {
	Symbols  []SymbolPair  `yaml:"symbols"`
	Binance  BinanceConfig `yaml:"binance"`
	Gate     GateConfig    `yaml:"gate"`
	Alert    AlertConfig   `yaml:"alert"`
	Risk     RiskConfig    `yaml:"risk"`
	Pricing  PricingConfig `yaml:"pricing"`
	Cooldown int           `yaml:"cooldown_seconds"`
}

type SymbolPair struct {
	BinanceSymbol string `yaml:"binance_symbol"`
	GateSymbol    string `yaml:"gate_symbol"`
}

type BinanceConfig struct {
	FuturesWSBase string `yaml:"futures_ws_base"`
}

type GateConfig struct {
	FuturesWSBase               string `yaml:"futures_ws_base"`
	FuturesAPIBase              string `yaml:"futures_api_base"`
	APIKey                      string `yaml:"api_key"`
	APISecret                   string `yaml:"api_secret"`
	ContractCacheRefreshMinutes int    `yaml:"contract_cache_refresh_minutes"`
}

type AlertConfig struct {
	SpreadPctThreshold  decimal.Decimal `yaml:"spread_pct_threshold"`
	FundingAPRThreshold decimal.Decimal `yaml:"funding_apr_threshold"`
}

type RiskConfig struct {
	LeftSideBurialWeight decimal.Decimal `yaml:"left_side_burial_weight"`
	MaxPositionUSD       decimal.Decimal `yaml:"max_position_usd"`
	MaxImpactCostPct     decimal.Decimal `yaml:"max_impact_cost_pct"`
}

type PricingConfig struct {
	BudgetUSD               decimal.Decimal `yaml:"budget_usd"`
	GateSlippagePct         decimal.Decimal `yaml:"gate_slippage_pct"`
	BinanceSlippagePct      decimal.Decimal `yaml:"binance_slippage_pct"`
	GateTakerFeePct         decimal.Decimal `yaml:"gate_taker_fee_pct"`
	BinanceTakerFeePct      decimal.Decimal `yaml:"binance_taker_fee_pct"`
	BinanceMomentumDriftPct decimal.Decimal `yaml:"binance_momentum_drift_pct"`
	ExecutionPath           string          `yaml:"execution_path"`
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}
	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}
	return &cfg, nil
}
