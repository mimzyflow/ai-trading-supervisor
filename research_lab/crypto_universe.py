"""Public Kraken EUR universe discovery for research only, never order routing."""
import json
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from supervisor.api import NoRedirect

MAX_RESPONSE = 4_000_000
EXCLUDED_BASES = {'EUR','USD','GBP','CHF','CAD','AUD','JPY','USDT','USDC','DAI','PYUSD','EURT','EURQ'}


def _get(path, query=None, opener=None):
    opener = opener or build_opener(NoRedirect()).open
    url = 'https://api.kraken.com/0/public/' + path
    if query:
        url += '?' + urlencode(query)
    request = Request(url, headers={'Accept':'application/json','User-Agent':'TradingResearch/2.0'}, method='GET')
    with opener(request, timeout=12) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('kraken_public_response_refused')
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('kraken_public_response_too_large')
    payload = json.loads(raw)
    if payload.get('error'):
        raise ValueError('kraken_public_provider_error')
    return payload['result']


def discover_eur_universe(opener=None, limit=12):
    """Evaluate every currently listed EUR spot pair, then rank by turnover.

    Ranking is fixed before strategy simulation. It is a liquidity screen, not
    a return screen, so historical winners are not selected after seeing P/L.
    """
    if type(limit) is not int or not 2 <= limit <= 20:
        raise ValueError('invalid_crypto_universe_limit')
    pairs = _get('AssetPairs', opener=opener)
    eligible = []
    for code, meta in pairs.items():
        ws = meta.get('wsname') or ''
        if not ws.endswith('/EUR') or meta.get('status') != 'online' or '.d' in code.lower():
            continue
        base = ws.split('/')[0].upper()
        if base in EXCLUDED_BASES:
            continue
        eligible.append((code, ws))
    if len(eligible) < limit:
        raise ValueError('insufficient_kraken_eur_universe')
    ticker = _get('Ticker', {'pair': ','.join(code for code, _ in eligible)}, opener)
    ranked = []
    for code, ws in eligible:
        row = ticker.get(code)
        if row is None:
            # Kraken may canonicalize pair keys; fall back to wsname matching.
            row = next((v for k,v in ticker.items() if k == code), None)
        if not row:
            continue
        try:
            last = float(row['c'][0]); volume = float(row['v'][1])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        turnover = last * volume
        if turnover > 0:
            ranked.append({'pair': code, 'id': ws, 'turnover_24h_eur': turnover})
    ranked.sort(key=lambda x: (-x['turnover_24h_eur'], x['id']))
    if len(ranked) < limit:
        raise ValueError('insufficient_kraken_ticker_data')
    return {'evaluated_pairs': len(eligible), 'selected': ranked[:limit],
            'selection_rule': 'top_current_24h_eur_turnover_excluding_fiat_and_stablecoins',
            'return_data_used_for_selection': False}
