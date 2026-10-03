from pathlib import Path
import json

import ccxt
import pandas as pd

UNIVERSE = Path("backtests/alt_universe.json")
OUT = Path("backtests/alt_recent")
OUT.mkdir(parents=True, exist_ok=True)

rows = json.loads(UNIVERSE.read_text())
excluded = {"PAXG", "USDG", "USDT", "USDC", "DAI", "EURT"}
selected = [
    row for row in rows
    if row["symbol"] not in excluded
    and row["market_cap_rank"] >= 60
    and row["market_cap_rank"] <= 180
    and row["kraken_quote_volume_eur_24h"] >= 200_000
    and row["spread_bps"] <= 35
]
selected = selected[:24]
selected_pairs = []

exchange = ccxt.kraken({"enableRateLimit": True})
print("pairs", len(selected))
for row in selected:
    pair = row["pair"]
    data = exchange.fetch_ohlcv(pair, "4h", limit=720)
    if len(data) < 260:
        print("skip", pair, "candles", len(data))
        continue
    df = pd.DataFrame(
        data,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["date"] = pd.to_datetime(df.pop("timestamp"), unit="ms", utc=True)
    # Kraken includes the unfinished candle. Never backtest that row.
    closed_before = pd.Timestamp.now(tz="UTC").floor("4h")
    df = df[df["date"] < closed_before].copy()
    target = OUT / f"{pair.replace('/', '_')}-4h.feather"
    df[["date", "open", "high", "low", "close", "volume"]].to_feather(target)
    selected_pairs.append(pair)
    print(
        pair,
        "rank=", row["market_cap_rank"],
        "cap_m€=", round(row["market_cap_eur"] / 1e6),
        "candles=", len(df),
    )

(OUT / "manifest.json").write_text(json.dumps({
    "captured_at": pd.Timestamp.now(tz="UTC").isoformat(),
    "pairs": selected_pairs,
    "timeframe": "4h",
    "universe_basis": "current_snapshot_not_historical",
    "historical_membership_verified": False,
}, indent=2))
