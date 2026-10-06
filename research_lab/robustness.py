"""Robustness statistics for simulation-only strategy selection."""
import math
import random
from itertools import combinations
from statistics import NormalDist

NORMAL = NormalDist()
EULER_GAMMA = 0.5772156649015329

def _finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non_finite_metric")
    return value

def trade_metrics(trades):
    pnl = [_finite(t.get("profit", 0)) for t in trades]
    wins = [x for x in pnl if x > 0]
    losses = [-x for x in pnl if x < 0]
    gross_profit, gross_loss = sum(wins), sum(losses)
    return {
        "closed_trades": len(pnl),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(pnl) * 100, 4) if pnl else None,
        "gross_profit": round(gross_profit, 6),
        "gross_loss": round(gross_loss, 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "expectancy": round(sum(pnl) / len(pnl), 6) if pnl else None,
    }
def curve_returns(curve):
    values = [_finite(point["equity"]) for point in curve]
    result = []
    for before, after in zip(values, values[1:]):
        if before <= 0:
            raise ValueError("invalid_equity_curve")
        result.append(after / before - 1)
    return result

def sharpe_components(returns):
    values = [_finite(x) for x in returns]
    if len(values) < 3:
        return {"sharpe": None, "skew": None, "kurtosis": None}
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    if variance <= 0:
        return {"sharpe": None, "skew": None, "kurtosis": None}
    std = math.sqrt(variance)
    skew = sum(((x - mean) / std) ** 3 for x in values) / len(values)
    kurtosis = sum(((x - mean) / std) ** 4 for x in values) / len(values)
    return {"sharpe": mean / std, "skew": skew, "kurtosis": kurtosis}

def deflated_sharpe_probability(returns, trials=1, trial_sharpes=None):
    stats = sharpe_components(returns)
    sr = stats["sharpe"]
    n = len(returns)
    if sr is None or n < 3:
        return None
    samples = [x for x in (trial_sharpes or []) if x is not None and math.isfinite(x)]
    trials = max(int(trials), len(samples), 1)
    if samples:
        avg = sum(samples) / len(samples)
        variance = sum((x - avg) ** 2 for x in samples) / max(1, len(samples) - 1)
        sigma = math.sqrt(variance)
    else:
        avg, sigma = 0.0, 0.0
    if trials <= 1 or sigma == 0:
        benchmark = 0.0
    else:
        a = NORMAL.inv_cdf(1 - 1 / trials)
        b = NORMAL.inv_cdf(1 - 1 / (trials * math.e))
        benchmark = avg + sigma * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)
    denom = 1 - stats["skew"] * sr + ((stats["kurtosis"] - 1) / 4) * sr * sr
    if denom <= 0:
        return None
    z = (sr - benchmark) * math.sqrt(n - 1) / math.sqrt(denom)
    return round(NORMAL.cdf(z), 6)

def monte_carlo_trade_risk(trades, initial=100.0, paths=1000, seed=20261006):
    pnl = [_finite(t.get("profit", 0)) for t in trades]
    if len(pnl) < 5:
        return {"state": "insufficient_sample", "trades": len(pnl)}
    rng = random.Random(seed)
    terminal, drawdowns = [], []
    for _ in range(paths):
        equity = peak = _finite(initial)
        worst = 0.0
        for _ in pnl:
            equity += rng.choice(pnl)
            peak = max(peak, equity)
            if peak > 0:
                worst = max(worst, (peak - equity) / peak)
        terminal.append(equity)
        drawdowns.append(worst * 100)
    terminal.sort()
    drawdowns.sort()
    q05 = terminal[max(0, int(paths * 0.05) - 1)]
    q95dd = drawdowns[min(paths - 1, int(paths * 0.95))]
    return {
        "state": "ok",
        "paths": paths,
        "probability_of_loss": round(sum(x < initial for x in terminal) / paths, 6),
        "terminal_equity_p05": round(q05, 4),
        "drawdown_p95_pct": round(q95dd, 4),
    }
def probability_of_backtest_overfitting(strategy_windows):
    if len(strategy_windows) < 2:
        return None
    lengths = {len(v) for v in strategy_windows.values()}
    if len(lengths) != 1:
        raise ValueError("unaligned_strategy_windows")
    n = lengths.pop()
    if n < 4 or n % 2:
        return None
    names = sorted(strategy_windows)
    half = n // 2
    logits = []
    all_idx = range(n)
    for train_idx in combinations(all_idx, half):
        test_idx = [i for i in all_idx if i not in train_idx]
        train_scores = {
            name: sum(strategy_windows[name][i] for i in train_idx) / half
            for name in names
        }
        chosen = max(names, key=lambda name: (train_scores[name], name))
        test_scores = {
            name: sum(strategy_windows[name][i] for i in test_idx) / half
            for name in names
        }
        ordered = sorted(names, key=lambda name: (test_scores[name], name))
        rank = ordered.index(chosen) + 1
        omega = (rank - 0.5) / len(names)
        logits.append(math.log(omega / (1 - omega)))
    return round(sum(value <= 0 for value in logits) / len(logits), 6)

def promotion_gate(result, benchmark_return, trial_sharpes=None, pbo=None):
    trades = result.get("trades", [])
    metrics = trade_metrics(trades)
    returns = curve_returns(result.get("curve", []))
    dsr = deflated_sharpe_probability(
        returns,
        trials=max(1, len(trial_sharpes or [])),
        trial_sharpes=trial_sharpes,
    )
    mc = monte_carlo_trade_risk(trades)
    reasons = []
    if metrics["closed_trades"] < 30:
        reasons.append("insufficient_trades")
    if result.get("return_pct", -999) <= max(0.0, benchmark_return):
        reasons.append("fails_cash_or_benchmark")
    if metrics["profit_factor"] is None or metrics["profit_factor"] < 1.2:
        reasons.append("profit_factor_below_1_2")
    if result.get("max_drawdown_pct", 100) > 5:
        reasons.append("drawdown_above_5pct")
    if dsr is None or dsr < 0.90:
        reasons.append("deflated_sharpe_not_convincing")
    if pbo is not None and pbo > 0.50:
        reasons.append("backtest_overfitting_risk")
    if mc.get("state") != "ok" or mc.get("probability_of_loss", 1) > 0.35:
        reasons.append("monte_carlo_risk")
    return {
        "state": "research_promising" if not reasons else "rejected",
        "reasons": reasons,
        "metrics": metrics,
        "deflated_sharpe_probability": dsr,
        "pbo": pbo,
        "monte_carlo": mc,
        "automatic_live_deployment": False,
        "real_money_eligible": False,
    }
