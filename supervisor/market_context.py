"""Small public-price context; raw research state stays private to its worker."""
import math
from .market_room import fresh


def market_features(bundle, now):
    """Only dated, closed observations enter the model's market context."""
    if not isinstance(bundle, dict) or not fresh(bundle.get('observed_at'), now, 96 * 3600):
        return []
    features = []
    for asset in bundle.get('assets', [])[:16]:
        try:
            bars = asset['bars']
            if len(bars) < 21 or not fresh(bars[-1]['close_at'], now, 96 * 3600):
                continue
            first, last = bars[-21]['close'], bars[-1]['close']
            if any(type(price) not in {float, int} or not math.isfinite(price) or price <= 0 for price in [first, last]):
                continue
            features.append({'symbol': asset['id'], 'last_closed_at': bars[-1]['close_at'],
                             'last_close': last, 'currency': bundle['currency'],
                             'return_20_sessions_pct': round((last / first - 1) * 100, 3)})
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return features

