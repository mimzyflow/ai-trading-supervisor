"""Validate candle files before any new exploratory experiment."""
import argparse
import json
from pathlib import Path


def validate_frame(frame, timeframe, now=None):
    import pandas as pd
    columns = ["date", "open", "high", "low", "close", "volume"]
    if not all(c in frame for c in columns) or frame.empty:
        raise ValueError("missing_ohlcv")
    dates = pd.to_datetime(frame["date"], utc=True)
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("duplicate_or_unordered_candles")
    if frame[columns[1:]].isna().any().any() or frame[columns[1:]].isin([float('inf'), float('-inf')]).any().any() or (frame[["open", "high", "low", "close"]] <= 0).any().any() or (frame["volume"] < 0).any():
        raise ValueError("invalid_prices_or_volume")
    if ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("invalid_ohlc_geometry")
    minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}[timeframe]
    now = now or pd.Timestamp.now(tz="UTC")
    if (dates + pd.Timedelta(minutes=minutes) > now).any():
        raise ValueError("unfinished_or_future_candle")
    gaps = int((dates.diff().dropna() > pd.Timedelta(minutes=minutes)).sum())
    return {"rows": len(frame), "first": dates.iloc[0].isoformat(), "last": dates.iloc[-1].isoformat(), "gap_count": gaps, "zero_volume_rows": int((frame["volume"] == 0).sum())}


def main():
    import pandas as pd
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--timeframe", required=True, choices=["15m", "1h", "4h", "1d"])
    parser.add_argument("--pairs", nargs="+", required=True)
    args = parser.parse_args()
    result = {}
    for pair in args.pairs:
        p = args.data / (pair.replace("/", "_") + "-" + args.timeframe + ".feather")
        result[pair] = validate_frame(pd.read_feather(p), args.timeframe)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
