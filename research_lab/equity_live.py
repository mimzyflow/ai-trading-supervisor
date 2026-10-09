"""Public, brokerless US equity daily data for prospective paper trading."""
import json, hashlib, math
from datetime import datetime, timezone
from urllib.request import Request, build_opener
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from supervisor.api import NoRedirect
from .data import validate
from .equity_data import SYMBOLS, MAX_RESPONSE_BYTES, MARKET_TIMEZONE

URL='https://query1.finance.yahoo.com/v8/finance/chart/'
MAX_CORPORATE_ACTIONS = 256

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

def live_url(symbol):
    if symbol not in SYMBOLS: raise ValueError('equity_symbol_not_allowed')
    return URL+symbol+'?'+urlencode({'range':'2y','interval':'1d','events':'div,splits','includePrePost':'false'})

def fetch(symbol, opener=None):
    url=live_url(symbol); opener=opener or build_opener(NoRedirect()).open
    req=Request(url,headers={'User-Agent':'EquityPaper/1.0','Accept':'application/json'},method='GET')
    with opener(req,timeout=12) as r:
        if r.status!=200 or r.geturl()!=url: raise ValueError('equity_live_http_refused')
        raw=r.read(MAX_RESPONSE_BYTES+1)
    if len(raw)>MAX_RESPONSE_BYTES: raise ValueError('equity_response_too_large_or_invalid')
    return raw

def parse(raw,symbol,observed_at):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('equity_response_too_large_or_invalid')
    try: result=json.loads(raw)['chart']['result'][0]
    except Exception: raise ValueError('equity_live_invalid_json') from None
    meta=result.get('meta',{})
    if meta.get('symbol')!=symbol or meta.get('currency')!='USD' or meta.get('instrumentType')!='EQUITY': raise ValueError('equity_live_identity')
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

def collect(now=None, opener=None):
    now=now or datetime.now(timezone.utc); assets=[]; sources=[]
    for symbol in SYMBOLS:
        raw=fetch(symbol,opener); assets.append(parse(raw,symbol,now)); sources.append({'symbol':symbol,'url':live_url(symbol),'observed_at':now.isoformat(),'sha256':hashlib.sha256(raw).hexdigest()})
    common=set.intersection(*(set(b['close_at'] for b in a['bars']) for a in assets)); common=sorted(common)
    if len(common)<260: raise ValueError('equity_live_common_history_short')
    for a in assets:
        by={b['close_at']:b for b in a['bars']}; a['bars']=[by[d] for d in common]
    bundle={'schema_version':1,'currency':'USD','provider':'yahoo_public_chart','observed_at':now.isoformat(),'diagnostic_only':True,'broker_connected':False,'real_money_eligible':False,'corporate_actions_verified':False,'assets':assets,'provenance':{'sources':sources,'purpose':'prospective_brokerless_paper_only'}}
    return validate(bundle,now=now)
