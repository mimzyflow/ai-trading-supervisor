from pathlib import Path
import ccxt
import pandas as pd

out = Path("backtests/alt_recent/BTC_EUR-4h.feather")
exchange = ccxt.kraken({"enableRateLimit": True})
rows = exchange.fetch_ohlcv("BTC/EUR", "4h", limit=720)
df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
df["date"] = pd.to_datetime(df.pop("timestamp"), unit="ms", utc=True)
df[["date", "open", "high", "low", "close", "volume"]].to_feather(out)
print(len(df), df["date"].min(), df["date"].max())
