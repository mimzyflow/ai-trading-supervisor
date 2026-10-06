"""Portfolio-risk helpers for brokerless paper simulation only."""
import math

def _returns(asset, index, lookback=30):
    bars = asset["bars"]
    start = max(1, index - lookback + 1)
    values = []
    for i in range(start, index + 1):
        prev = float(bars[i - 1]["close"])
        cur = float(bars[i]["close"])
        if prev > 0:
            values.append(cur / prev - 1)
    return values

def volatility(asset, index, lookback=30):
    values = _returns(asset, index, lookback)
    if len(values) < 5:
        return None
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / max(1, len(values) - 1)
    return math.sqrt(max(0.0, variance))

def correlation(asset_a, asset_b, index, lookback=30):
    left, right = _returns(asset_a, index, lookback), _returns(asset_b, index, lookback)
    n = min(len(left), len(right))
    if n < 5:
        return None
    left, right = left[-n:], right[-n:]
    ml, mr = sum(left) / n, sum(right) / n
    cov = sum((a - ml) * (b - mr) for a, b in zip(left, right))
    vl = sum((a - ml) ** 2 for a in left)
    vr = sum((b - mr) ** 2 for b in right)
    if vl <= 0 or vr <= 0:
        return None
    return cov / math.sqrt(vl * vr)

def entry_budget(bundle, state, index, asset, equity, allocation=20,
                 max_gross_exposure=0.70, max_single_weight=0.20,
                 correlation_limit=0.85, target_daily_volatility=0.025):
    if equity <= 0:
        return 0.0, "invalid_equity"
    by_id = {item["id"]: item for item in bundle["assets"]}
    gross = 0.0
    for symbol, position in state["positions"].items():
        price = float(by_id[symbol]["bars"][index]["close"])
        gross += float(position["quantity"]) * price
    if gross / equity >= max_gross_exposure:
        return 0.0, "gross_exposure_limit"
    for symbol in state["positions"]:
        corr = correlation(asset, by_id[symbol], index)
        if corr is not None and corr >= correlation_limit:
            return 0.0, "correlation_limit"
    vol = volatility(asset, index)
    scale = 1.0 if not vol or vol <= target_daily_volatility else target_daily_volatility / vol
    budget = min(
        float(allocation) * scale,
        equity * max_single_weight,
        max(0.0, equity * max_gross_exposure - gross),
        float(state["cash"]),
    )
    return max(0.0, budget), "ok"
