"""Public, brokerless US equity daily data for prospective paper trading."""
import json, hashlib, math
from datetime import datetime, timezone
from urllib.request import Request, build_opener
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from supervisor.api import NoRedirect
from .data import validate, finite, stamp
from .equity_data import SYMBOLS, MAX_RESPONSE_BYTES, MARKET_TIMEZONE

URL='https://query1.finance.yahoo.com/v8/finance/chart/'
MAX_CORPORATE_ACTIONS = 256
MAX_RECENT_REPAIRS = 2
ERROR_CODES = frozenset({
    'invalid_ohlc_geometry', 'invalid_number', 'boolean_number',
    'zero_volume_session_requires_review', 'unclosed_duplicate_or_unordered_session',
    'equity_live_invalid_events', 'equity_live_invalid_json', 'equity_live_identity',
    'equity_live_http_refused', 'equity_response_too_large_or_invalid',
    'equity_live_insufficient_closed_history', 'equity_live_common_history_short',
    'equity_recent_repair_outside_window', 'equity_recent_repair_missing_session',
    'equity_recent_repair_events_mismatch', 'equity_recent_repair_budget_exceeded',
    'equity_recent_repair_quotes_mismatch', 'equity_recent_repair_invalid_intraday',
})


def error_code(exc):
    """Never publish arbitrary exception messages or upstream response text."""
    code = str(exc) if isinstance(exc, ValueError) else ''
    return code if code in ERROR_CODES else None

def _corporate_actions(result):
    """Retain event dates without inventing raw prices, quantities or payments."""
    events = result.get('events', {})
    if not isinstance(events, dict) or set(events) - {'splits', 'dividends'}:
        raise ValueError('equity_live_invalid_events')
    actions = []
    market = ZoneInfo(MARKET_TIMEZONE)
    for provider_kind, entries in events.items():
        if not isinstance(entries, dict) or len(actions) + len(entries) > MAX_CORPORATE_ACTIONS:
            raise ValueError('equity_live_invalid_events')
        for event_id, event in entries.items():
            if not isinstance(event, dict):
                raise ValueError('equity_live_invalid_events')
            epoch = event.get('date')
            if (type(epoch) is not int or epoch < 0 or not isinstance(event_id, str)
                    or not event_id.isdecimal() or int(event_id) != epoch):
                raise ValueError('equity_live_invalid_events')
            try:
                day = datetime.fromtimestamp(epoch, timezone.utc).astimezone(market).date()
            except (OverflowError, OSError, ValueError):
                raise ValueError('equity_live_invalid_events') from None
            if not 1970 <= day.year <= 2100:
                raise ValueError('equity_live_invalid_events')
            fields = ('amount',) if provider_kind == 'dividends' else ('numerator', 'denominator')
            values = []
            for field in fields:
                value = event.get(field)
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value <= 0):
                    raise ValueError('equity_live_invalid_events')
                values.append(value)
            if provider_kind == 'splits' and 'splitRatio' in event:
                ratio = event['splitRatio']
                try:
                    left, right = ratio.split(':') if isinstance(ratio, str) and len(ratio) <= 40 else (None, None)
                    numerator, denominator = float(left), float(right)
                    if (not math.isfinite(numerator) or not math.isfinite(denominator)
                            or numerator <= 0 or denominator <= 0):
                        raise ValueError('equity_live_invalid_events')
                    ratio_value = numerator / denominator
                except (ValueError, TypeError, ZeroDivisionError):
                    raise ValueError('equity_live_invalid_events') from None
                if not math.isfinite(ratio_value) or not math.isclose(ratio_value, values[0] / values[1], rel_tol=1e-8):
                    raise ValueError('equity_live_invalid_events')
            actions.append({'kind':'dividend' if provider_kind == 'dividends' else 'split',
                            'date':day.isoformat(), 'provider_epoch':epoch})
    return sorted(actions, key=lambda item:(item['date'], item['kind'], item['provider_epoch']))

def live_url(symbol, *, recent=False):
    if symbol not in SYMBOLS: raise ValueError('equity_symbol_not_allowed')
    params = {'range': '5d' if recent else '2y', 'interval': '5m' if recent else '1d'}
    # Keep full corporate-action history on the primary request. Yahoo's
    # events-enabled response can return inconsistent recent OHLC quotes.
    if not recent:
        params['events'] = 'div,splits'
    params['includePrePost'] = 'false'
    return URL+symbol+'?'+urlencode(params)

def fetch(symbol, opener=None, *, recent=False):
    url=live_url(symbol, recent=recent); opener=opener or build_opener(NoRedirect()).open
    req=Request(url,headers={'User-Agent':'EquityPaper/1.0','Accept':'application/json'},method='GET')
    with opener(req,timeout=12) as r:
        if r.status!=200 or r.geturl()!=url: raise ValueError('equity_live_http_refused')
        raw=r.read(MAX_RESPONSE_BYTES+1)
    if len(raw)>MAX_RESPONSE_BYTES: raise ValueError('equity_response_too_large_or_invalid')
    return raw

def _chart(raw, symbol):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('equity_response_too_large_or_invalid')
    try: result=json.loads(raw)['chart']['result'][0]
    except Exception: raise ValueError('equity_live_invalid_json') from None
    meta=result.get('meta',{})
    if meta.get('symbol')!=symbol or meta.get('currency')!='USD' or meta.get('instrumentType')!='EQUITY': raise ValueError('equity_live_identity')
    return result


def parse(raw,symbol,observed_at):
    result = _chart(raw, symbol)
    actions = _corporate_actions(result)
    q=result['indicators']['quote'][0]; ts=result['timestamp']; market=ZoneInfo(MARKET_TIMEZONE); bars=[]
    for i,t in enumerate(ts):
        day=datetime.fromtimestamp(t,timezone.utc).astimezone(market).date()
        close_at=datetime(day.year,day.month,day.day,16,0,tzinfo=market).astimezone(timezone.utc)
        # Never consume today's/incomplete session before its regular close.
        if close_at>observed_at: continue
        vals={k:q[k][i] for k in ('open','high','low','close','volume')}
        if any(v is None or isinstance(v,bool) or not isinstance(v,(int,float)) for v in vals.values()): continue
        open_at=datetime(day.year,day.month,day.day,9,30,tzinfo=market).astimezone(timezone.utc)
        bars.append({'open_at':open_at.isoformat(),'close_at':close_at.isoformat(),**vals})
    if len(bars)<260: raise ValueError('equity_live_insufficient_closed_history')
    return {'id':symbol,'currency':'USD','asset_class':'stock','price_basis':'raw','lot_size':1,'bars':bars,
            'corporate_actions':actions, 'corporate_actions_verified':False, 'price_basis_verified':False}


def _asset_bundle(asset):
    return {'schema_version': 1, 'currency': 'USD', 'assets': [asset]}


def _repair_recent_geometry(asset, now, opener):
    """Recover only invalid extrema from a complete, matching intraday session."""
    broken = []
    for bar in asset['bars']:
        prices = {key: finite(bar[key], .00000001) for key in ('open', 'high', 'low', 'close')}
        if prices['high'] < max(prices.values()) or prices['low'] > min(prices.values()):
            broken.append(bar['close_at'])
    tail = {bar['close_at'] for bar in asset['bars'][-5:]}
    if not broken or any(session not in tail or not 0 <= (now - stamp(session)).total_seconds() <= 7*86400 for session in broken):
        raise ValueError('equity_recent_repair_outside_window')
    raw = fetch(asset['id'], opener, recent=True)
    result = _chart(raw, asset['id'])
    timestamps = result.get('timestamp')
    quote = result['indicators']['quote'][0]
    if (not isinstance(timestamps, list) or any(type(t) is not int for t in timestamps)
            or any(not isinstance(quote.get(key), list) or len(quote[key]) != len(timestamps)
                   for key in ('open', 'high', 'low', 'close', 'volume'))):
        raise ValueError('equity_recent_repair_invalid_intraday')
    broken_days = {stamp(session).date().isoformat() for session in broken}
    old_events = [event for event in asset['corporate_actions'] if event['date'] in broken_days]
    new_events = [event for event in _corporate_actions(result) if event['date'] in broken_days]
    if old_events != new_events:
        raise ValueError('equity_recent_repair_events_mismatch')
    fields = {}
    for bar in asset['bars']:
        if bar['close_at'] not in broken:
            continue
        opened, closed = int(stamp(bar['open_at']).timestamp()), int(stamp(bar['close_at']).timestamp())
        expected = list(range(opened, closed, 300))
        indexes = [i for i, t in enumerate(timestamps) if opened <= t < closed]
        # No silent gaps, early-close assumptions, duplicate ticks or after-hours.
        if len(expected) != 78 or [timestamps[i] for i in indexes] != expected:
            raise ValueError('equity_recent_repair_missing_session')
        rows = []
        for i in indexes:
            row = {key: finite(quote[key][i], .00000001) for key in ('open', 'high', 'low', 'close', 'volume')}
            if row['high'] < max(row[key] for key in ('open', 'low', 'close')) or row['low'] > min(row[key] for key in ('open', 'high', 'close')):
                raise ValueError('equity_recent_repair_invalid_intraday')
            rows.append(row)
        high, low = max(row['high'] for row in rows), min(row['low'] for row in rows)
        bad_high = bar['high'] < max(bar[key] for key in ('open', 'low', 'close'))
        bad_low = bar['low'] > min(bar[key] for key in ('open', 'high', 'close'))
        matches = lambda a, b: math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-6)
        if (not matches(bar['open'], rows[0]['open']) or not matches(bar['close'], rows[-1]['close'])
                or (not bad_high and not matches(bar['high'], high))
                or (not bad_low and not matches(bar['low'], low))
                or sum(row['volume'] for row in rows) > finite(bar['volume'], 0)):
            raise ValueError('equity_recent_repair_quotes_mismatch')
        fields[bar['close_at']] = []
        if bad_high:
            bar['high'] = high; fields[bar['close_at']].append('high')
        if bad_low:
            bar['low'] = low; fields[bar['close_at']].append('low')
    validate(_asset_bundle(asset), now)
    return {'reason': 'invalid_ohlc_geometry', 'sessions': broken,
            'method': 'verified_intraday_extrema', 'fields': fields,
            'url': live_url(asset['id'], recent=True), 'observed_at': now.isoformat(),
            'sha256': hashlib.sha256(raw).hexdigest()}


def collect(now=None, opener=None):
    now=now or datetime.now(timezone.utc); assets=[]; sources=[]; repairs=0
    for symbol in SYMBOLS:
        raw=fetch(symbol,opener); asset=parse(raw,symbol,now)
        source={'symbol':symbol,'url':live_url(symbol),'observed_at':now.isoformat(),'sha256':hashlib.sha256(raw).hexdigest()}
        try:
            validate(_asset_bundle(asset), now)
        except ValueError as exc:
            if error_code(exc) != 'invalid_ohlc_geometry':
                raise
            if repairs >= MAX_RECENT_REPAIRS:
                raise ValueError('equity_recent_repair_budget_exceeded') from None
            source['repair'] = _repair_recent_geometry(asset, now, opener)
            repairs += 1
        assets.append(asset); sources.append(source)
    common=set.intersection(*(set(b['close_at'] for b in a['bars']) for a in assets)); common=sorted(common)
    if len(common)<260: raise ValueError('equity_live_common_history_short')
    for a in assets:
        by={b['close_at']:b for b in a['bars']}; a['bars']=[by[d] for d in common]
    bundle={'schema_version':1,'currency':'USD','provider':'yahoo_public_chart','observed_at':now.isoformat(),'diagnostic_only':True,'broker_connected':False,'real_money_eligible':False,'corporate_actions_verified':False,'assets':assets,'provenance':{'sources':sources,'purpose':'prospective_brokerless_paper_only'}}
    return validate(bundle,now=now)
