"""Pure parsing for a fixed, diagnostic-only equity universe.

Yahoo is one public source, not an independently verified price/action history.
XNYS regular sessions are used as a documented proxy for regular US sessions.
No import or function in this module downloads prices or connects to a broker.
"""
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from importlib.metadata import version
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .data import canonical_hash, stamp, validate

# Fixed before each experiment. Broad, liquid, higher-volatility research basket;
# inclusion is not a recommendation and results may not be used to cherry-pick winners.
SYMBOLS = ('SOFI', 'U', 'PLUG', 'OPEN', 'FUBO', 'NIO', 'MARA', 'RIOT')
START_DATE = '2021-06-01'
END_DATE = '2026-10-02'
CALENDAR_VERSION = '4.13.2'
MAX_RESPONSE_BYTES = 2_000_000
MARKET_TIMEZONE = 'America/New_York'
LIMITATIONS = [
    'Diagnostic universe fixed before simulation; not a recommendation or profitability selection.',
    'One Yahoo source is not independent price or corporate-action verification.',
    'No announced events does not prove corporate-action history is complete.',
    'Yahoo OHLC may be split-adjusted; any announced action requires review and is refused.',
    'Raw price basis is conditional on no announced actions, not independently certified.',
    'XNYS regular sessions are a proxy for regular US sessions; issuer-specific halts are not verified.',
    'exchange_calendars is a community-maintained schedule, not proof of executable prices.',
    'Historical universe and survivorship are unverified; no broker or real-money eligibility.',
]


def chart_url(symbol):
    if symbol not in SYMBOLS:
        raise ValueError('equity_symbol_not_allowed')
    market = ZoneInfo(MARKET_TIMEZONE)
    start = datetime.combine(date.fromisoformat(START_DATE), datetime.min.time(), market)
    end = datetime.combine(date.fromisoformat(END_DATE) + timedelta(days=1), datetime.min.time(), market)
    query = urlencode({'period1': int(start.timestamp()), 'period2': int(end.timestamp()),
                       'interval': '1d', 'events': 'div,splits,capitalGains',
                       'includePrePost': 'false', 'includeAdjustedClose': 'true'})
    return 'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol + '?' + query


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('equity_invalid_number')
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('equity_duplicate_json_key')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('equity_invalid_number')


def _sessions(calendar, observed_at):
    sessions = calendar.get('sessions') if isinstance(calendar, dict) else None
    if not isinstance(sessions, list) or not 2 <= len(sessions) <= 10_000:
        raise ValueError('equity_calendar_unavailable')
    result = []
    previous = None
    market = ZoneInfo(MARKET_TIMEZONE)
    for item in sessions:
        if not isinstance(item, dict):
            raise ValueError('equity_invalid_calendar')
        day = item.get('date')
        try:
            opened, closed = stamp(item['open_at']), stamp(item['close_at'])
            parsed_day = date.fromisoformat(day)
        except (KeyError, TypeError, ValueError):
            raise ValueError('equity_invalid_calendar') from None
        local_open, local_close = opened.astimezone(market), closed.astimezone(market)
        if (str(parsed_day) != day or not START_DATE <= day <= END_DATE or
                local_open.date() != parsed_day or local_close.date() != parsed_day or
                (local_open.hour, local_open.minute, local_open.second, local_open.microsecond) != (9, 30, 0, 0) or
                (local_close.hour, local_close.minute, local_close.second, local_close.microsecond) not in
                {(13, 0, 0, 0), (16, 0, 0, 0)} or opened >= closed or
                (previous is not None and day <= previous)):
            raise ValueError('equity_invalid_calendar')
        if closed > observed_at:
            raise ValueError('equity_unclosed_session')
        result.append({'date': day, 'open_at': opened.isoformat(), 'close_at': closed.isoformat()})
        previous = day
    return result


def load_calendar(observed_at=None):
    """Load the optional, pinned local schedule; does not make network calls."""
    observed_at = stamp(observed_at or datetime.now(timezone.utc).isoformat())
    try:
        installed = version('exchange_calendars')
        if installed != CALENDAR_VERSION:
            raise ValueError('equity_calendar_version_mismatch')
        import exchange_calendars as xcals
        calendar = xcals.get_calendar('XNYS', start=START_DATE, end=END_DATE)
        schedule = calendar.schedule.loc[START_DATE:END_DATE]
        sessions = [{'date': label.date().isoformat(), 'open_at': row['open'].isoformat(),
                     'close_at': row['close'].isoformat()} for label, row in schedule.iterrows()]
        result = {'name': 'XNYS', 'timezone': MARKET_TIMEZONE, 'package': 'exchange_calendars',
                  'version': installed, 'observed_at': observed_at.isoformat(),
                  'source_url': 'https://pypi.org/project/exchange_calendars/4.13.2/',
                  'sessions': sessions, 'verified': True,
                  'verification': 'exact_session_coverage_and_hours_against_pinned_XNYS_schedule',
                  'independently_verified': False,
                  'dependencies': {name: version(name) for name in ('pandas', 'numpy')}}
        result['sessions'] = _sessions(result, observed_at)
        if result['sessions'][0]['date'] != START_DATE or result['sessions'][-1]['date'] != END_DATE:
            raise ValueError('equity_calendar_range_incomplete')
        result['schedule_sha256'] = canonical_hash(result['sessions'])
        return result
    except ValueError:
        raise
    except Exception:
        raise ValueError('equity_calendar_unavailable') from None


def parse_chart(raw, symbol, sessions, observed_at):
    """Refuse partial charts/actions; never fill a missing bar or alter prices."""
    chart_url(symbol)
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('equity_response_too_large_or_invalid')
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_constant)
        chart = payload['chart']
        if chart['error'] is not None:
            raise ValueError('equity_provider_error')
        results = chart['result']
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise ValueError('equity_invalid_chart')
        result = results[0]
        meta = result['meta']
        if (meta['symbol'] != symbol or meta['currency'] != 'USD' or
                meta['instrumentType'] != 'EQUITY' or meta['exchangeTimezoneName'] != MARKET_TIMEZONE or
                meta['dataGranularity'] != '1d'):
            raise ValueError('equity_provider_identity_mismatch')
        events = result.get('events', {})
        if not isinstance(events, dict):
            raise ValueError('equity_invalid_events')
        for kind, entries in events.items():
            if kind not in {'splits', 'dividends', 'capitalGains'} or not isinstance(entries, dict):
                raise ValueError('equity_invalid_events')
            if entries:
                raise ValueError('equity_announced_action_requires_review')
        timestamps = result['timestamp']
        quotes = result['indicators']['quote']
        if not isinstance(timestamps, list) or not isinstance(quotes, list) or len(quotes) != 1:
            raise ValueError('equity_incomplete_chart')
        quote = quotes[0]
        if not isinstance(quote, dict) or any(not isinstance(quote.get(key), list) or
                len(quote[key]) != len(timestamps) for key in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('equity_incomplete_ohlcv')
        expected = {session['date']: session for session in sessions}
        bars, seen = [], []
        market = ZoneInfo(MARKET_TIMEZONE)
        for index, epoch in enumerate(timestamps):
            _number(epoch)
            if int(epoch) != epoch:
                raise ValueError('equity_invalid_timestamp')
            provider_time = datetime.fromtimestamp(epoch, timezone.utc)
            day = provider_time.astimezone(market).date().isoformat()
            if provider_time > observed_at:
                raise ValueError('equity_future_bar')
            if day not in expected or (seen and day <= seen[-1]):
                raise ValueError('equity_unexpected_duplicate_or_unordered_session')
            session = expected[day]
            if provider_time != stamp(session['open_at']):
                raise ValueError('equity_provider_session_time_mismatch')
            prices = {key: _number(quote[key][index]) for key in ('open', 'high', 'low', 'close', 'volume')}
            bars.append({'open_at': session['open_at'], 'close_at': session['close_at'], **prices})
            seen.append(day)
        if seen != list(expected):
            raise ValueError('equity_missing_sessions')
        return {'id': symbol, 'currency': 'USD', 'asset_class': 'stock', 'price_basis': 'raw',
                'lot_size': 1, 'bars': bars}
    except ValueError:
        raise
    except (KeyError, TypeError, OverflowError, OSError, AttributeError):
        raise ValueError('equity_invalid_or_incomplete_chart') from None


def build_diagnostic_bundle(raw_by_symbol, calendar, observed_at=None, source_observed_at=None):
    observed_at = stamp(observed_at or datetime.now(timezone.utc).isoformat())
    if not isinstance(raw_by_symbol, dict) or set(raw_by_symbol) != set(SYMBOLS):
        raise ValueError('equity_fixed_universe_required')
    sessions = _sessions(calendar, observed_at)
    calendar_verified = (calendar.get('verified') is True and calendar.get('name') == 'XNYS' and
                         calendar.get('version') == CALENDAR_VERSION and
                         calendar.get('timezone') == MARKET_TIMEZONE and
                         calendar.get('schedule_sha256') == canonical_hash(sessions) and
                         sessions[0]['date'] == START_DATE and sessions[-1]['date'] == END_DATE)
    sources, assets = [], []
    for symbol in SYMBOLS:
        source_time = stamp((source_observed_at or {}).get(symbol, observed_at.isoformat()))
        if source_time > observed_at:
            raise ValueError('equity_future_source_observation')
        if any(stamp(session['close_at']) > source_time for session in sessions):
            raise ValueError('equity_unclosed_source_session')
        assets.append(parse_chart(raw_by_symbol[symbol], symbol, sessions, source_time))
        sources.append({'symbol': symbol, 'url': chart_url(symbol), 'method': 'GET',
                        'observed_at': source_time.isoformat(),
                        'sha256': hashlib.sha256(raw_by_symbol[symbol]).hexdigest(),
                        'raw_file': 'raw/' + symbol + '.json'})
    evidence = {key: value for key, value in calendar.items() if key != 'sessions'}
    bundle = {'schema_version': 1, 'currency': 'USD', 'provider': 'yahoo_public_chart',
              'observed_at': observed_at.isoformat(), 'diagnostic_only': True,
              'calendar_verified': calendar_verified, 'corporate_actions_verified': False,
              'historical_universe_verified': False, 'broker_connected': False,
              'real_money_eligible': False, 'date_range': {'start': START_DATE, 'end': END_DATE},
              'assets': assets, 'provenance': {'sources': sources, 'calendar': evidence,
                                              'limitations': list(LIMITATIONS)}}
    return validate(bundle, now=observed_at)
