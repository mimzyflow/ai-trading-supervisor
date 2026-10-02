from pathlib import Path
import argparse
import pandas as pd

PAIR_PREFIXES = {
    "BTC/EUR": "XBTEUR",
    "ETH/EUR": "ETHEUR",
}
TIMEFRAME_NAMES = {
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
}


def convert(source_dir: Path, output_dir: Path, minutes: int) -> None:
    timeframe = TIMEFRAME_NAMES[minutes]
    output_dir.mkdir(parents=True, exist_ok=True)
    for pair, prefix in PAIR_PREFIXES.items():
        source = source_dir / f"{prefix}_{minutes}.csv"
        df = pd.read_csv(
            source,
            header=None,
            names=["timestamp", "open", "high", "low", "close", "volume", "trades"],
        )
        df["date"] = pd.to_datetime(df.pop("timestamp"), unit="s", utc=True)
        df = df[["date", "open", "high", "low", "close", "volume"]]
        target = output_dir / f"{pair.replace('/', '_')}-{timeframe}.feather"
        df.to_feather(target)
        print(pair, timeframe, len(df), df["date"].min(), df["date"].max(), target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--minutes", type=int, choices=sorted(TIMEFRAME_NAMES), default=60)
    args = parser.parse_args()
    convert(args.source_dir, args.output_dir, args.minutes)


if __name__ == "__main__":
    main()
