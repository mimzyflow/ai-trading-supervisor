"""Bounded, reproducible backtests. This command can never start live trading."""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

IMAGE = "freqtradeorg/freqtrade:2026.9@sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def command(root, data, output, strategy, timerange, fee, pairs, timeframe):
    if not 0 < fee <= 0.02 or timeframe not in {"15m", "1h", "4h", "1d"}:
        raise ValueError("invalid_research_parameters")
    if not strategy.isidentifier() or not pairs or any(not p.endswith("/EUR") or not p[:-4].isalnum() for p in pairs):
        raise ValueError("invalid_strategy_or_pairs")
    return ["docker", "run", "--rm",
            "-e", "FREQTRADE__DRY_RUN=true", "-e", "FREQTRADE__EXCHANGE__KEY=", "-e", "FREQTRADE__EXCHANGE__SECRET=",
            "-v", str(root / "user_data/config.dryrun.json") + ":/project/config.dryrun.json:ro",
            "-v", str(root / "user_data/strategies") + ":/project/strategies:ro",
            "-v", str(data) + ":/data:ro", "-v", str(output) + ":/results",
            IMAGE, "backtesting", "--config", "/project/config.dryrun.json",
            "--strategy-path", "/project/strategies", "--strategy", strategy,
            "--datadir", "/data", "--timeframe", timeframe, "--timerange", timerange,
            "--fee", str(fee), "--enable-protections", "--cache", "none", "--export", "trades",
            "--backtest-directory", "/results", "--pairs", *pairs]


def manifest(root, data, strategy, pairs, timeframe, timerange, fee, membership):
    files = [data / (pair.replace("/", "_") + "-" + timeframe + ".feather") for pair in pairs]
    if any(not p.is_file() for p in files):
        raise ValueError("missing_data")
    return {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "image": IMAGE, "strategy": strategy, "strategy_sha256": digest(root / "user_data/strategies" / (strategy + ".py")),
        "config_sha256": digest(root / "user_data/config.dryrun.json"),
        "timeframe": timeframe, "timerange": timerange, "pairs": pairs,
        "fee_per_side": fee, "round_trip_fee_approx": 2 * fee,
        "protections_enabled": True, "cache": "none", "starting_wallet_eur": 100,
        "max_open_trades": -1, "position_count_limit": None, "stake_eur": 10, "historical_membership_verified": membership,
        "slippage_model": "not_modelled_default_backtest", "purpose": "exploratory_only",
        "real_money_eligible": False,
        "data": [{"file": p.name, "sha256": digest(p), "bytes": p.stat().st_size} for p in files],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--timerange", required=True)
    parser.add_argument("--timeframe", choices=["15m", "1h", "4h", "1d"], required=True)
    parser.add_argument("--fee", type=float, default=0.008)
    parser.add_argument("--pairs", nargs="+", required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = args.data.resolve()
    # No ad-hoc file or CLI flag can certify historical universe membership.
    membership = False
    meta_path = data / "manifest.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())
        if metadata.get("historical_membership_verified") is not False:
            raise ValueError("historical_membership_requires_separate_review")
    output = root / "research_results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%f")
    output.mkdir(parents=True)
    # The pinned image runs as ftuser (UID/GID 1000). Keep its package environment.
    # Root invocations on Oracle give only this new result directory to ftuser.
    if os.geteuid() == 0:
        os.chown(output, 1000, 1000)
    info = manifest(root, data, args.strategy, args.pairs, args.timeframe, args.timerange, args.fee, membership)
    argv = command(root, data, output, args.strategy, args.timerange, args.fee, args.pairs, args.timeframe)
    info["command"] = argv
    (output / "manifest.json").write_text(json.dumps(info, indent=2))
    if args.prepare_only:
        print("Manifest prepared: " + str(output / "manifest.json"))
        return 0
    # Never inherit exchange/API overrides into a research invocation.
    env = {k: v for k, v in os.environ.items() if not k.startswith("FREQTRADE__")}
    preflight = ["docker", "run", "--rm", "--entrypoint", "python", "-v", str(root / "scripts/check_market_data.py") + ":/check_market_data.py:ro", "-v", str(data) + ":/data:ro", IMAGE,
                 "/check_market_data.py", "--data", "/data", "--timeframe", args.timeframe, "--pairs", *args.pairs]
    validation = subprocess.run(preflight, env=env, capture_output=True, text=True, timeout=120)
    if validation.returncode != 0:
        info["exit_code"] = validation.returncode
        info["data_validation"] = "failed"
        (output / "manifest.json").write_text(json.dumps(info, indent=2))
        (output / "data-validation.log").write_text(validation.stdout + validation.stderr)
        return validation.returncode
    info["data_validation"] = json.loads(validation.stdout)
    with (output / "run.log").open("w") as log:
        result = subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    info["exit_code"] = result.returncode
    info["finished_at"] = datetime.now(timezone.utc).isoformat()
    info["outputs"] = [{"file": p.name, "sha256": digest(p)} for p in output.glob("*.zip")]
    if result.returncode == 0 and not info["outputs"]:
        info["exit_code"] = 1
    (output / "manifest.json").write_text(json.dumps(info, indent=2))
    print(json.dumps({"exit_code": info["exit_code"], "manifest": str(output / "manifest.json"), "real_money_eligible": False}))
    return info["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
