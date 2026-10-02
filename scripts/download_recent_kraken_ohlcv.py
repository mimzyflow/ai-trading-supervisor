from pathlib import Path
import ccxt
import pandas as pd

OUT = Path("backtests/recent")
OUT.mkdir(parents=True, exist_ok=True)
exchange = ccxt.kraken({"enableRateLimit": True})
for timeframe in ("15m", "1h", "4h"):
    for pair in ("BTC/EUR", "ETH/EUR"):
        rows = exchange.fetch_ohlcv(pair, timeframe, limit=720)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df.pop("timestamp"), unit="ms", utc=True)
        df = df[["date", "open", "high", "low", "close", "volume"]]
        target = OUT / f"{pair.replace('/', '_')}-{timeframe}.feather"
        df.to_feather(target)
        print(pair, timeframe, len(df), target)
