"""Allowlisted public Kraken data only. Closed bars are append-only."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from supervisor.api import NoRedirect
from .data import validate, canonical_hash


def fetch_crypto(previous=None, now=None, opener=None):
    now = now or datetime.now(timezone.utc)
    opener = opener or build_opener(NoRedirect()).open
    assets = []
    for name, pair in [('BTC/EUR', 'XBTEUR'), ('ETH/EUR', 'ETHEUR')]:
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
        assets.append({'id': name, 'asset_class': 'crypto', 'currency': 'EUR', 'lot_size': 0.00000001, 'bars': bars})
    bundle = {'schema_version': 1, 'currency': 'EUR', 'provider': 'kraken_public_ohlc', 'calendar_verified': True,
              'corporate_actions_verified': True, 'historical_universe_verified': False,
              'universe_policy': 'fixed_at_freeze', 'future_membership_tracking': True, 'assets': assets}
    return validate(bundle, now)
