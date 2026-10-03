from __future__ import annotations

import json
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from pathlib import Path

import ccxt

OUT = Path("backtests/alt_universe.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

def coingecko_markets():
    params = urllib.parse.urlencode({
        "vs_currency": "eur",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
    })
    req = urllib.request.Request(
        "https://api.coingecko.com/api/v3/coins/markets?" + params,
        headers={"User-Agent": "ai-trading-supervisor/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

markets = coingecko_markets()
by_symbol = {}
for coin in markets:
    symbol = str(coin.get("symbol") or "").upper()
    if symbol:
        by_symbol.setdefault(symbol, coin)

exchange = ccxt.kraken({"enableRateLimit": True})
exchange.load_markets()
tickers = exchange.fetch_tickers()

rows = []
excluded = {"BTC", "ETH", "USDT", "USDC", "DAI", "EURT", "PYUSD", "USDG"}
for pair, market in exchange.markets.items():
    if not market.get("spot") or not market.get("active") or market.get("quote") != "EUR":
        continue
    base = market.get("base")
    if not base or base in excluded or base not in by_symbol:
        continue
    coin = by_symbol[base]
    cap = coin.get("market_cap") or 0
    rank = coin.get("market_cap_rank") or 9999
    ticker = tickers.get(pair) or {}
    bid = ticker.get("bid")
    ask = ticker.get("ask")
    last = ticker.get("last")
    base_volume = ticker.get("baseVolume") or 0
    quote_volume = ticker.get("quoteVolume")
    if not quote_volume and last and base_volume:
        quote_volume = last * base_volume
    quote_volume = float(quote_volume or 0)
    spread_bps = None
    if bid and ask and bid > 0 and ask >= bid:
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10000

    # Research tier: smaller than mega-caps, but not micro-illiquid.
    if not (40 <= rank <= 250):
        continue
    if cap and not (75_000_000 <= cap <= 8_000_000_000):
        continue
    if quote_volume < 150_000:
        continue
    if spread_bps is None or spread_bps > 80:
        continue

    rows.append({
        "pair": pair,
        "symbol": base,
        "market_cap_rank": rank,
        "market_cap_eur": cap,
        "kraken_quote_volume_eur_24h": round(quote_volume, 2),
        "spread_bps": round(spread_bps, 2),
    })

rows.sort(key=lambda x: (x["market_cap_rank"], -x["kraken_quote_volume_eur_24h"]))
OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
OUT.with_suffix(".meta.json").write_text(json.dumps({
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "universe_basis": "current_snapshot_not_historical",
    "historical_membership_verified": False,
    "source": "CoinGecko markets + Kraken markets/tickers",
}, indent=2))
print(f"candidates={len(rows)}")
for row in rows[:30]:
    print(
        row["pair"],
        "rank=", row["market_cap_rank"],
        "cap_m€=", round(row["market_cap_eur"] / 1e6),
        "vol24h_k€=", round(row["kraken_quote_volume_eur_24h"] / 1000),
        "spread_bps=", row["spread_bps"],
    )
