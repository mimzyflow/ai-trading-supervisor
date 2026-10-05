"""Canonical daily OHLCV bundles; raw equity prices and corporate actions."""
import hashlib
import json
import math
from datetime import datetime, timezone


def stamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone_required')
    return parsed.astimezone(timezone.utc)


def finite(value, minimum=None):
    if isinstance(value, bool):
        raise ValueError('boolean_number')
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError('invalid_number')
    return result


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate(bundle, now=None):
    now = now or datetime.now(timezone.utc)
    if bundle.get('schema_version') != 1 or bundle.get('currency') not in {'EUR', 'USD'}:
        raise ValueError('invalid_bundle')
    assets = bundle.get('assets')
    if not isinstance(assets, list) or not 1 <= len(assets) <= 32:
        raise ValueError('research_universe_size_invalid')
    ids, dates = set(), None
    for asset in assets:
        asset_id = asset.get('id', '')
        if not isinstance(asset_id, str) or not asset_id or len(asset_id) > 64 or asset_id in ids:
            raise ValueError('invalid_asset_id')
        ids.add(asset_id)
        if asset.get('asset_class') not in {'crypto', 'stock', 'etf'} or asset.get('currency') != bundle['currency']:
            raise ValueError('asset_or_currency_mismatch')
        if asset.get('asset_class') != 'crypto' and asset.get('price_basis') != 'raw':
            raise ValueError('equity_raw_prices_required')
        lot = finite(asset.get('lot_size', 1), 0.00000001)
        if asset.get('asset_class') != 'crypto' and lot < 1 and asset.get('fractional_supported') is not True:
            raise ValueError('fractional_support_not_verified')
        bars = asset.get('bars')
        if not isinstance(bars, list) or not 2 <= len(bars) <= 10000:
            raise ValueError('invalid_bar_count')
        previous = None
        sessions = []
        for bar in bars:
            opened, closed = stamp(bar['open_at']), stamp(bar['close_at'])
            if opened >= closed or closed > now or (previous is not None and opened < previous):
                raise ValueError('unclosed_duplicate_or_unordered_session')
            previous = closed
            sessions.append(opened.date().isoformat())
            prices = {k: finite(bar[k], 0.00000001) for k in ['open', 'high', 'low', 'close']}
            if prices['high'] < max(prices.values()) or prices['low'] > min(prices.values()):
                raise ValueError('invalid_ohlc_geometry')
            bar.update(prices, volume=finite(bar['volume'], 0), open_at=opened.isoformat(), close_at=closed.isoformat())
            if bar['volume'] == 0:
                raise ValueError('zero_volume_session_requires_review')
            finite(bar.get('split_ratio', 1), 0.00000001)
            dividend = finite(bar.get('dividend_per_share', 0), 0)
            if dividend and stamp(bar['dividend_paid_at']) < opened:
                raise ValueError('invalid_dividend_payment')
        if len(set(sessions)) != len(sessions):
            raise ValueError('daily_sessions_required')
        if dates is not None and sessions != dates:
            raise ValueError('inconsistent_portfolio_calendar')
        dates = sessions
    return bundle


def subset(bundle, start, end):
    return {**bundle, 'assets': [{**asset, 'bars': asset['bars'][start:end]} for asset in bundle['assets']]}
