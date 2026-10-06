#!/usr/bin/env python3
"""Run Freqtrade bias/recursive checks for predeclared V3 challengers only."""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.research_run import IMAGE

ALLOWED = {
    "MoussaV3RegimeMomentum": "1h",
    "MoussaV3TripleBarrier": "1h",
    "MoussaV3SlowBreakout": "4h",
}

def commands(root, data, output, strategy, timerange, pair):
    if strategy not in ALLOWED:
        raise ValueError("v3_strategy_not_predeclared")
    timeframe = ALLOWED[strategy]
    if not pair.endswith("/EUR") or not pair[:-4].isalnum():
        raise ValueError("invalid_pair")
    common = [
        "docker", "run", "--rm", "--network", "none",
        "-e", "FREQTRADE__DRY_RUN=true",
        "-e", "FREQTRADE__EXCHANGE__KEY=",
        "-e", "FREQTRADE__EXCHANGE__SECRET=",
        "-v", str(root / "user_data/config.dryrun.json") + ":/project/config.dryrun.json:ro",
        "-v", str(root / "user_data/strategies") + ":/project/strategies:ro",
        "-v", str(data) + ":/data:ro",
        "-v", str(output) + ":/results",
        IMAGE,
    ]
    strategy_args = [
        "--config", "/project/config.dryrun.json",
        "--strategy-path", "/project/strategies",
        "--strategy", strategy,
        "--datadir", "/data",
        "--timeframe", timeframe,
        "--timerange", timerange,
        "--fee", "0.008",
    ]
    lookahead = common + [
        "lookahead-analysis", *strategy_args,
        "--minimum-trade-amount", "5",
        "--targeted-trade-amount", "20",
        "--lookahead-analysis-exportfilename", "/results/lookahead.csv",
        "--pairs", pair,
    ]
    recursive = common + [
        "recursive-analysis", *strategy_args,
        "--startup-candle", "100", "200", "400", "800",
        "-p", pair,
    ]
    return lookahead, recursive

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--strategy", choices=sorted(ALLOWED), required=True)
    parser.add_argument("--timerange", required=True)
    parser.add_argument("--pair", default="BTC/EUR")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = args.data.resolve()
    output = root / "research_results" / ("audit-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    output.mkdir(parents=True, exist_ok=False)
    lookahead, recursive = commands(root, data, output, args.strategy, args.timerange, args.pair)
    env = {k: v for k, v in os.environ.items() if not k.startswith("FREQTRADE__")}
    results = {}
    for name, argv in [("lookahead", lookahead), ("recursive", recursive)]:
        log = output / (name + ".log")
        with log.open("w") as handle:
            completed = subprocess.run(argv, env=env, stdout=handle, stderr=subprocess.STDOUT, timeout=1800)
        results[name] = {"exit_code": completed.returncode, "log": log.name}
        if completed.returncode != 0:
            break
    payload = {
        "strategy": args.strategy,
        "pair": args.pair,
        "timeframe": ALLOWED[args.strategy],
        "timerange": args.timerange,
        "results": results,
        "automatic_live_deployment": False,
        "real_money_eligible": False,
    }
    (output / "audit.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload))
    return 0 if all(item["exit_code"] == 0 for item in results.values()) and len(results) == 2 else 1

if __name__ == "__main__":
    raise SystemExit(main())
