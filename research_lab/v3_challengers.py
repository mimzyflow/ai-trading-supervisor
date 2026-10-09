"""Predeclared V3 challenger matrix. Simulation/research only."""
from datetime import datetime, timezone

from .data import subset
from .engine import simulate
from .research import costs
from .robustness import (
    curve_returns,
    probability_of_backtest_overfitting,
    promotion_gate,
    sharpe_components,
)

CHALLENGERS = {
    "regime_momentum": {
        "family": "trend_breakout", "fast": 10, "slow": 50, "breakout": 20,
        "stop_loss": 0.035, "max_hold": 45, "take_profit": 0.08,
        "trailing_activation": 0.04, "trailing_distance": 0.02,
        "min_atr_pct": 0.01, "max_atr_pct": 0.10, "min_volume_ratio": 1.10,
    },
    "triple_barrier": {
        "family": "trend_breakout", "fast": 20, "slow": 100, "breakout": 20,
        "stop_loss": 0.03, "max_hold": 30, "take_profit": 0.07,
        "trailing_activation": 0.035, "trailing_distance": 0.018,
        "min_atr_pct": 0.008, "max_atr_pct": 0.09, "min_volume_ratio": 1.20,
    },
    "slow_breakout": {
        "family": "trend_breakout", "fast": 30, "slow": 120, "breakout": 55,
        "stop_loss": 0.04, "max_hold": 60, "take_profit": 0.10,
        "trailing_activation": 0.05, "trailing_distance": 0.025,
        "min_atr_pct": 0.006, "max_atr_pct": 0.08, "min_volume_ratio": 1.0,
    },
}

def _compact(result):
    return {
        key: result.get(key)
        for key in (
            "return_pct", "profit", "equity", "profit_factor",
            "max_drawdown_pct", "closed_trades", "halted", "entry_attempts"
        )
    }

def _positive_concentration(trades):
    by_asset = {}
    for trade in trades:
        profit = float(trade.get("profit", 0))
        if profit > 0:
            by_asset[trade["asset"]] = by_asset.get(trade["asset"], 0.0) + profit
    total = sum(by_asset.values())
    return max(by_asset.values()) / total if total and by_asset else 0.0
def _window_ranges(count):
    start = max(200, count // 3)
    available = count - start
    if available < 160:
        raise ValueError("insufficient_v3_window_history")
    width = available // 4
    ranges = []
    for index in range(4):
        left = start + index * width
        right = count if index == 3 else start + (index + 1) * width
        ranges.append((left, right))
    return ranges

def evaluate(bundle, now=None):
    now = now or datetime.now(timezone.utc)
    count = len(bundle["assets"][0]["bars"])
    ranges = _window_ranges(count)
    strategy_windows = {name: [] for name in CHALLENGERS}
    window_details = {name: [] for name in CHALLENGERS}

    for left, right in ranges:
        view = subset(bundle, 0, right)
        benchmark = simulate(
            view, {"family": "buy_hold"}, start_index=left,
            risk_control=False, **costs(bundle)
        )
        for name, spec in CHALLENGERS.items():
            result = simulate(view, spec, start_index=left, **costs(bundle))
            strategy_windows[name].append(result["return_pct"])
            window_details[name].append({
                "start_index": left, "end_index": right,
                "result": _compact(result),
                "benchmark_return_pct": benchmark["return_pct"],
            })
    pbo = probability_of_backtest_overfitting(strategy_windows)
    full_benchmark = simulate(
        bundle, {"family": "buy_hold"}, start_index=ranges[0][0],
        risk_control=False, **costs(bundle)
    )
    full = {}
    trial_sharpes = []
    raw_results = {}
    for name, spec in CHALLENGERS.items():
        result = simulate(bundle, spec, start_index=ranges[0][0], **costs(bundle))
        raw_results[name] = result
        trial_sharpes.append(sharpe_components(curve_returns(result["curve"]))["sharpe"])

    for name, result in raw_results.items():
        gate = promotion_gate(
            result,
            benchmark_return=full_benchmark["return_pct"],
            trial_sharpes=trial_sharpes,
            pbo=pbo,
        )
        unstable = any(item["result"]["return_pct"] <= 0 for item in window_details[name])
        concentration = _positive_concentration(result["trades"])
        if unstable:
            gate["reasons"].append("negative_independent_window")
        if concentration > 0.65:
            gate["reasons"].append("positive_pnl_concentration")
        gate["state"] = "research_promising" if not gate["reasons"] else "rejected"
        full[name] = {
            "spec": CHALLENGERS[name],
            "result": _compact(result),
            "gate": gate,
            "positive_pnl_top_asset_share": round(concentration, 6),
            "windows": window_details[name],
        }
    promising = [name for name, value in full.items() if value["gate"]["state"] == "research_promising"]
    return {
        "schema_version": 1,
        "observed_at": now.isoformat(),
        "state": "candidate_for_forward_shadow" if promising else "all_rejected",
        "challengers": full,
        "promising": promising,
        "pbo": pbo,
        "benchmark": _compact(full_benchmark),
        "selection_policy": {
            "minimum_closed_trades": 30,
            "minimum_profit_factor": 1.2,
            "maximum_drawdown_pct": 5,
            "minimum_deflated_sharpe_probability": 0.90,
            "maximum_pbo": 0.50,
            "maximum_positive_pnl_asset_share": 0.65,
            "negative_independent_window_allowed": False,
        },
        "automatic_live_deployment": False,
        "real_money_eligible": False,
    }
