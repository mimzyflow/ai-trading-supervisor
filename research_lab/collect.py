"""Allowlisted public Kraken data only. Closed bars are append-only."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from supervisor.api import NoRedirect
from .data import validate, canonical_hash
from .crypto_universe import discover_eur_universe


def fetch_crypto(previous=None, now=None, opener=None, selected=None, minimum_history=2, max_assets=None):
    now = now or datetime.now(timezone.utc)
    opener = opener or build_opener(NoRedirect()).open
    assets = []
    selected = selected or [('BTC/EUR', 'XBTEUR'), ('ETH/EUR', 'ETHEUR')]
    if not isinstance(selected, list) or not 1 <= len(selected) <= 20:
        raise ValueError('invalid_crypto_research_universe')
    for name, pair in selected:
        request = Request('https://api.kraken.com/0/public/OHLC?' + urlencode({'pair': pair, 'interval': 1440}), method='GET')
        with opener(request, timeout=10) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('data_response_too_large')
        payload = json.loads(raw)
        if payload.get('error'):
            raise ValueError('public_data_provider_error')
        groups = [rows for key, rows in payload['result'].items() if key != 'last']
        if len(groups) != 1:
            raise ValueError('ambiguous_data_pair')
        bars = []
        # The final Kraken candle is explicitly unfinished.
        for row in groups[0][:-1]:
            opened = datetime.fromtimestamp(int(row[0]), timezone.utc)
            closed = opened + timedelta(days=1)
            if closed <= now:
                bars.append({'open_at': opened.isoformat(), 'close_at': closed.isoformat(),
                             **dict(zip(['open', 'high', 'low', 'close'], map(float, row[1:5]))), 'volume': float(row[6])})
        if previous:
            old = next((a for a in previous['assets'] if a['id'] == name), None)
            if old:
                merged = {b['open_at']: b for b in old['bars']}
                for bar in bars:
                    if bar['open_at'] in merged and canonical_hash(merged[bar['open_at']]) != canonical_hash(bar):
                        raise ValueError('closed_history_revision_requires_review')
                    merged[bar['open_at']] = bar
                bars = [merged[key] for key in sorted(merged)]
        if any((datetime.fromisoformat(b['open_at']) - datetime.fromisoformat(a['open_at'])).total_seconds() != 86400 for a, b in zip(bars, bars[1:])):
            raise ValueError('daily_data_gap')
        if len(bars) >= minimum_history:
            assets.append({'id': name, 'asset_class': 'crypto', 'currency': 'EUR', 'lot_size': 0.00000001, 'bars': bars})
    if max_assets is not None:
        assets = assets[:max_assets]
    if not assets:
        raise ValueError('no_crypto_assets_with_required_history')
    # Different listing dates are expected. Research only uses the common closed
    # daily history so every portfolio decision sees the same sessions.
    common = set.intersection(*(set(b['open_at'] for b in a['bars']) for a in assets))
    if len(common) < minimum_history:
        raise ValueError('insufficient_common_crypto_history')
    for asset in assets:
        asset['bars'] = [b for b in asset['bars'] if b['open_at'] in common]
    bundle = {'schema_version': 1, 'currency': 'EUR', 'provider': 'kraken_public_ohlc', 'calendar_verified': True,
              'corporate_actions_verified': True, 'historical_universe_verified': False,
              'universe_policy': 'fixed_at_freeze', 'future_membership_tracking': True, 'assets': assets}
    return validate(bundle, now)


def fetch_crypto_broad(previous=None, now=None, opener=None, limit=12):
    # Scan deeper than the final portfolio so newly listed high-turnover assets
    # cannot collapse the historical development window.
    discovery = discover_eur_universe(opener=opener, limit=min(20, max(limit, 18)))
    candidates = [(row['id'], row['pair']) for row in discovery['selected']]
    bundle = fetch_crypto(previous=previous, now=now, opener=opener, selected=candidates,
                          minimum_history=600, max_assets=limit)
    discovery['selected_for_research'] = [a['id'] for a in bundle['assets']]
    discovery['minimum_history_sessions'] = 600
    bundle['universe_discovery'] = discovery
    return bundle
