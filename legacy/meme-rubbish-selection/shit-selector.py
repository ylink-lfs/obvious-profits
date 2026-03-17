#!/usr/bin/env python3
# coding: utf-8
"""
Crypto Distressed Asset Screener

Screens crypto futures contracts suitable for shorting:
- Positive funding rate (earn fees when shorting)
- Downtrend (24h drop > -0.5%)
- Retail long trap (long/short user ratio > 1.1)
- Sufficient liquidity (24h volume > 3M USDT)

Data source: Gate.io Futures API
"""

import requests
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# =============================================================================
# Configuration
# =============================================================================
API_HOST = "https://api.gateio.ws"
API_PREFIX = "/api/v4"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# Hard filter thresholds
MIN_VOLUME_24H_QUOTE = 3_000_000  # Min 24h volume (USDT)
MAX_LEVERAGE = 50                  # Max leverage (exclude BTC/ETH majors)
MIN_DROP_PERCENTAGE = 0.5         # Min drop %

MIN_FUNDING_RATE = 0               # Min funding rate (positive carry)

# Game theory filter thresholds
MIN_SHORT_USERS = 100              # Min short users (sample size)
MIN_LONG_SHORT_RATIO = 1.1         # Min L/S ratio (retail trap)


# =============================================================================
# Data Models
# =============================================================================
@dataclass
class ContractInfo:
    """Contract metadata"""
    name: str
    funding_rate: float
    long_users: int
    short_users: int
    leverage_max: int
    in_delisting: bool
    status: str


@dataclass
class TickerInfo:
    """Ticker data"""
    contract: str
    last: float
    change_percentage: float
    volume_24h_quote: float
    high_24h: float
    low_24h: float


@dataclass
class ScreenerResult:
    """Screener result"""
    ticker: str
    price: float
    change_24h: float
    volume_24h_m: float       # Volume in millions USDT
    funding_rate: float
    long_short_ratio: float   # Long/Short user ratio
    apr: float                # Annualized percentage rate


# =============================================================================
# API Fetchers
# =============================================================================
def fetch_contracts() -> list[dict]:
    """Fetch all contract metadata"""
    url = f"{API_HOST}{API_PREFIX}/futures/usdt/contracts"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_tickers() -> list[dict]:
    """Fetch all ticker data"""
    url = f"{API_HOST}{API_PREFIX}/futures/usdt/tickers"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


# =============================================================================
# Data Parsers
# =============================================================================
def parse_contract(raw: dict) -> Optional[ContractInfo]:
    """Parse contract data with type conversion"""
    try:
        return ContractInfo(
            name=raw["name"],
            funding_rate=float(raw.get("funding_rate", 0)),
            long_users=int(raw.get("long_users", 0)),
            short_users=int(raw.get("short_users", 0)),
            leverage_max=int(raw.get("leverage_max", 0)),
            in_delisting=bool(raw.get("in_delisting", False)),
            status=raw.get("status", ""),
        )
    except (ValueError, KeyError):
        return None


def parse_ticker(raw: dict) -> Optional[TickerInfo]:
    """Parse ticker data with type conversion"""
    try:
        return TickerInfo(
            contract=raw["contract"],
            last=float(raw.get("last", 0)),
            change_percentage=float(raw.get("change_percentage", 0)),
            volume_24h_quote=float(raw.get("volume_24h_quote", 0)),
            high_24h=float(raw.get("high_24h", 0)),
            low_24h=float(raw.get("low_24h", 0)),
        )
    except (ValueError, KeyError):
        return None


# =============================================================================
# Screener Pipeline
# =============================================================================
def apply_hard_filters(contract: ContractInfo, ticker: TickerInfo) -> bool:
    """Apply hard filters. Returns True if passed."""
    if contract.status != "trading" or contract.in_delisting:
        return False
    if contract.leverage_max > MAX_LEVERAGE:
        return False
    if ticker.volume_24h_quote <= MIN_VOLUME_24H_QUOTE:
        return False
    if contract.funding_rate <= MIN_FUNDING_RATE:
        return False
    if ticker.change_percentage >= MIN_DROP_PERCENTAGE:
        return False
    return True


def calculate_metrics(contract: ContractInfo, ticker: TickerInfo) -> Optional[ScreenerResult]:
    """Calculate game theory metrics. Returns None if not qualified."""
    if contract.short_users <= MIN_SHORT_USERS:
        return None
    long_short_ratio = contract.long_users / contract.short_users
    if long_short_ratio <= MIN_LONG_SHORT_RATIO:
        return None
    # APR = funding_rate * 3 periods/day * 365 days * 100%
    apr = contract.funding_rate * 3 * 365 * 100
    return ScreenerResult(
        ticker=contract.name,
        price=ticker.last,
        change_24h=ticker.change_percentage,
        volume_24h_m=ticker.volume_24h_quote / 1_000_000,
        funding_rate=contract.funding_rate,
        long_short_ratio=long_short_ratio,
        apr=apr,
    )


def run_screener() -> list[ScreenerResult]:
    """Run the full screening pipeline"""
    raw_contracts = fetch_contracts()
    raw_tickers = fetch_tickers()
    
    contracts = {c.name: c for c in (parse_contract(r) for r in raw_contracts) if c}
    tickers = {t.contract: t for t in (parse_ticker(r) for r in raw_tickers) if t}
    joined_keys = set(contracts.keys()) & set(tickers.keys())
    
    passed_hard_filter = [
        (contracts[name], tickers[name])
        for name in joined_keys
        if apply_hard_filters(contracts[name], tickers[name])
    ]
    
    results = [
        result
        for contract, ticker in passed_hard_filter
        if (result := calculate_metrics(contract, ticker))
    ]
    
    results.sort(key=lambda x: x.apr, reverse=True)
    return results


def print_results(results: list[ScreenerResult]) -> None:
    """Print results table"""
    if not results:
        print("No qualifying targets found.")
        return
    now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Screening Results as of {now_time} +0800")
    header = (
        f"{'Ticker':<15} "
        f"{'Price':>12} "
        f"{'24h Chg%':>10} "
        f"{'Vol(M)':>10} "
        f"{'FundRate':>12} "
        f"{'L/S Ratio':>10} "
        f"{'APR%':>10}"
    )
    print(header)
    print("-" * len(header))
    
    for r in results:
        row = (
            f"{r.ticker:<15} "
            f"{r.price:>12.4f} "
            f"{r.change_24h:>9.2f}% "
            f"{r.volume_24h_m:>10.2f} "
            f"{r.funding_rate:>12.6f} "
            f"{r.long_short_ratio:>10.2f} "
            f"{r.apr:>9.2f}%"
        )
        print(row)
    print("-" * len(header))
    print(f"Total: {len(results)} targets")


def main():
    """Main entry point"""
    try:
        results = run_screener()
        print_results(results)
    except requests.RequestException as e:
        print(f"API request failed: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
