#!/usr/bin/env python3
"""Freqtrade lookahead-analysis + recursive-analysis, simulation only.

Usage (box locale, freqtrade installé, données OHLCV déjà téléchargées) :
  python3 scripts/run_bias_checks.py --strategy MoussaDailyTrend \
      --data /chemin/data/kraken --timerange 20250301-20261019 --output research_results/bias

Usage via l'image Docker épinglée (Oracle/Mac, sur décision de Moussa) :
  python3 scripts/run_bias_checks.py --runner docker ...

Garanties : dry_run forcé, clés vides, réseau coupé en Docker, liste blanche de
stratégies, aucune écriture hors du dossier de sortie. Aucun ordre possible.
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

IMAGE = "freqtradeorg/freqtrade:2026.9"
ALLOWED = {
    "MoussaDailyTrend": ("1d", "user_data/config.daily-trend.research.json", ("BTC/EUR", "ETH/EUR")),
    "MoussaMonthlyRotation": ("1d", "user_data/config.monthly-rotation.research.json", ("BTC/EUR", "ETH/EUR")),
    "MoussaV3RegimeMomentum": ("1h", "user_data/config.dryrun.json", ("ETH/EUR",)),
    "MoussaV3TripleBarrier": ("1h", "user_data/config.dryrun.json", ("ETH/EUR",)),
    "MoussaV3SlowBreakout": ("4h", "user_data/config.dryrun.json", ("ETH/EUR",)),
}
SAFE_ENV = {"FREQTRADE__DRY_RUN": "true", "FREQTRADE__EXCHANGE__KEY": "", "FREQTRADE__EXCHANGE__SECRET": ""}


def _check(strategy, timerange, pairs):
    if strategy not in ALLOWED:
        raise ValueError("strategy_not_predeclared")
    if not (len(timerange) == 17 and timerange[8] == "-" and timerange.replace("-", "").isdigit()):
        raise ValueError("invalid_timerange")
    for pair in pairs:
        base, _, quote = pair.partition("/")
        if quote != "EUR" or not base.isalnum():
            raise ValueError("invalid_pair")


def commands(root, data, output, strategy, timerange, pairs=None, runner="local", fee=None, data_format="json"):
    timeframe, config, default_pairs = ALLOWED.get(strategy, (None, None, ()))
    pairs = list(pairs or default_pairs)
    _check(strategy, timerange, pairs)
    root, data, output = Path(root), Path(data), Path(output)
    if runner == "docker":
        prefix = ["docker", "run", "--rm", "--network", "none"]
        for key, value in SAFE_ENV.items():
            prefix += ["-e", f"{key}={value}"]
        prefix += ["-v", f"{root / config}:/project/config.json:ro",
                   "-v", f"{root / 'user_data/strategies'}:/project/strategies:ro",
                   "-v", f"{data}:/data:ro", "-v", f"{output}:/results", IMAGE]
        cfg, strat_dir, data_dir, out_dir = "/project/config.json", "/project/strategies", "/data", "/results"
    elif runner == "local":
        prefix = ["freqtrade"]
        cfg, strat_dir, data_dir, out_dir = str(root / config), str(root / "user_data/strategies"), str(data), str(output)
    else:
        raise ValueError("invalid_runner")
    user = [] if runner == "docker" else ["--userdir", str(output / "userdir")]
    common = user + ["--config", cfg, "--strategy-path", strat_dir, "--strategy", strategy,
              "--datadir", data_dir, "--timeframe", timeframe, "--timerange", timerange,
              "--data-format-ohlcv", data_format]
    if fee is not None:
        common += ["--fee", str(fee)]
    lookahead = prefix + ["lookahead-analysis", *common, "--pairs", *pairs,
                          "--minimum-trade-amount", "2", "--targeted-trade-amount", "10",
                          "--lookahead-analysis-exportfilename", f"{out_dir}/lookahead-{strategy}.csv"]
    recursive = prefix + ["recursive-analysis", *common, "--pairs", pairs[0],
                          "--startup-candle", "120", "240", "400"]
    return lookahead, recursive


def run(cmds, env=None):
    env = {**(env or os.environ), **SAFE_ENV}
    results = []
    for cmd in cmds:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
        results.append({"command": cmd[cmd.index("lookahead-analysis") if "lookahead-analysis" in cmd else cmd.index("recursive-analysis")],
                        "exit_code": proc.returncode, "stdout_tail": proc.stdout[-6000:], "stderr_tail": proc.stderr[-3000:]})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True, choices=sorted(ALLOWED))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--timerange", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner", choices=("local", "docker"), default="local")
    parser.add_argument("--pairs", nargs="*")
    parser.add_argument("--fee", type=float)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    if args.runner == "local":
        # Scratch user directory inside the output folder: never writes into the repo.
        for sub in ("", "backtest_results", "data", "logs", "strategies", "hyperopt_results", "plot", "notebooks"):
            (args.output / "userdir" / sub).mkdir(parents=True, exist_ok=True)
    cmds = commands(root, args.data, args.output, args.strategy, args.timerange, args.pairs, args.runner, args.fee)
    results = run(cmds)
    summary = {"schema_version": 1, "observed_at": datetime.now(timezone.utc).isoformat(),
               "strategy": args.strategy, "timerange": args.timerange, "runner": args.runner,
               "dry_run_forced": True, "results": results,
               "passed": all(item["exit_code"] == 0 for item in results)}
    (args.output / f"bias-{args.strategy}.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "results"} |
                     {"exit_codes": [r["exit_code"] for r in results]}))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
