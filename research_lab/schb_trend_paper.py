"""Portefeuille papier actions de la salle de marché : ETF SCHB seul, tendance lente.

SIMULATION UNIQUEMENT : aucun courtier, aucun ordre, aucune clé.
Plan versionné ``market_room_schb_slow_trend_v1``. Il remplace, pour le compte papier
de 100 EUR, l'ancienne liste SOFI/U/PLUG/OPEN/FUBO/NIO/MARA/RIOT sans modifier le plan
de recherche actions figé (univers ``equity_data.SYMBOLS``), ni le témoin, ni les V3.

Règle (research_lab.slow_trend.choose) : à la clôture de la première séance de chaque
mois, SCHB est retenu si sa clôture est au-dessus de sa SMA200 quotidienne, sinon cash.
Exécution à l'ouverture de la séance suivante, en parts entières. À la création du plan,
une décision initiale est prise sur la dernière séance close. Alertes de baisse 5 % et
10 % : notify_only, aucune vente forcée.
"""
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from supervisor.api import NoRedirect
from .data import stamp
from .slow_trend import ALERT_LEVELS_PCT, SMA_DAYS, choose

SYMBOL = 'SCHB'
PLAN_ID = 'market_room_schb_slow_trend_v1'
SCHEMA = 1
URL = 'https://query1.finance.yahoo.com/v8/finance/chart/'
MAX_RESPONSE_BYTES = 2_000_000
MIN_HISTORY = SMA_DAYS + 10
MARKET_TIMEZONE = 'America/New_York'
FEE = 0.001
SLIPPAGE = 0.001
MIN_COMMISSION = 0.0
LEGACY_SYMBOLS = ('SOFI', 'U', 'PLUG', 'OPEN', 'FUBO', 'NIO', 'MARA', 'RIOT')


# ---------- données Yahoo (publiques, sans clé) ----------
def chart_url():
    return URL + SYMBOL + '?' + urlencode({'range': '2y', 'interval': '1d', 'events': 'div,splits',
                                           'includePrePost': 'false'})


def fetch(opener=None):
    url = chart_url()
    opener = opener or build_opener(NoRedirect()).open
    req = Request(url, headers={'User-Agent': 'EquityPaper/1.0', 'Accept': 'application/json'}, method='GET')
    with opener(req, timeout=12) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('schb_http_refused')
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('schb_response_too_large')
    return raw


def _price(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def parse(raw, observed_at):
    """Séances closes uniquement ; >= MIN_HISTORY séances ; divisions conservées avec ratio."""
    try:
        result = json.loads(raw)['chart']['result'][0]
        meta = result['meta']
        quote = result['indicators']['quote'][0]
        stamps = result['timestamp']
    except Exception:
        raise ValueError('schb_invalid_json') from None
    if meta.get('symbol') != SYMBOL or meta.get('currency') != 'USD' or meta.get('instrumentType') != 'ETF':
        raise ValueError('schb_identity')
    market = ZoneInfo(MARKET_TIMEZONE)
    bars = []
    for i, t in enumerate(stamps):
        day = datetime.fromtimestamp(t, timezone.utc).astimezone(market).date()
        close_at = datetime(day.year, day.month, day.day, 16, 0, tzinfo=market).astimezone(timezone.utc)
        if close_at > observed_at:
            continue  # jamais de séance non close
        values = {k: quote[k][i] for k in ('open', 'high', 'low', 'close')}
        if not all(_price(v) for v in values.values()):
            continue
        if bars and bars[-1]['date'] >= day.isoformat():
            raise ValueError('schb_unordered_sessions')
        bars.append({'date': day.isoformat(), 'close_at': close_at.isoformat(), **values,
                     'volume': quote['volume'][i] or 0})
    if len(bars) < MIN_HISTORY:
        raise ValueError('schb_insufficient_history')
    splits = []
    for event in (result.get('events') or {}).get('splits', {}).values():
        num, den = event.get('numerator'), event.get('denominator')
        if not (_price(num) and _price(den)):
            raise ValueError('schb_invalid_split')
        day = datetime.fromtimestamp(event['date'], timezone.utc).astimezone(market).date().isoformat()
        splits.append([day, num / den])
    return {'schema_version': 1, 'symbol': SYMBOL, 'provider': 'yahoo_public_chart',
            'price_basis': 'yahoo_split_adjusted', 'observed_at': observed_at.isoformat(),
            'bars': bars, 'splits': sorted(splits), 'real_money_eligible': False,
            'sha256': hashlib.sha256(raw).hexdigest()}


def collect(now=None, opener=None):
    now = now or datetime.now(timezone.utc)
    return parse(fetch(opener), now)


def validate_bundle(bundle, now, max_market_age_hours=96):
    if not isinstance(bundle, dict) or bundle.get('symbol') != SYMBOL or bundle.get('real_money_eligible') is not False:
        raise ValueError('schb_bundle_invalid')
    bars = bundle.get('bars')
    if not isinstance(bars, list) or len(bars) < MIN_HISTORY:
        raise ValueError('schb_insufficient_history')
    dates = [b['date'] for b in bars]
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError('schb_unordered_sessions')
    if not all(_price(b[k]) for b in bars for k in ('open', 'high', 'low', 'close')):
        raise ValueError('schb_invalid_price')
    age = (now - stamp(bars[-1]['close_at'])).total_seconds()
    if not 0 <= age <= max_market_age_hours * 3600:
        raise ValueError('schb_market_data_stale')
    return bundle


# ---------- état papier ----------
def new_state(now, initial, last_session, supersedes=None):
    return {'schema_version': SCHEMA, 'plan_id': PLAN_ID, 'symbol': SYMBOL,
            'created_at': now.isoformat(), 'updated_at': now.isoformat(),
            'mode': 'BROKERLESS_PAPER', 'currency': 'USD', 'initial_cash': float(initial),
            'cash': float(initial), 'shares': 0, 'entry_cost': 0.0, 'positions': {},
            'trades': [], 'orders': [], 'alerts': [], 'pending': None, 'decisions': [],
            'applied_splits': [], 'equity': float(initial), 'peak_equity': float(initial),
            'max_drawdown_pct': 0.0, 'last_session': None, 'bootstrap_session': last_session,
            'real_money_eligible': False, 'execution_revision': PLAN_ID,
            'execution_revision_started_at': now.isoformat(), 'halted': False, 'halt_reason': None,
            'blocked_reason': None, 'supersedes': supersedes}


def legacy_snapshot(path):
    """Résumé lecture seule d'un ancien fichier (liste SOFI...). Jamais modifié ni repris."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        old = json.loads(path.read_text())
    except (OSError, ValueError):
        return {'file': path.name, 'readable': False}
    return {'file': path.name, 'readable': True, 'execution_revision': old.get('execution_revision'),
            'equity': old.get('equity'), 'last_session': old.get('last_session'),
            'open_symbols': sorted(old.get('positions', {}))[:20],
            'closed_trades': len(old.get('trades', [])), 'positions_carried_over': False}


def load(path):
    path = Path(path)
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if (value.get('schema_version') != SCHEMA or value.get('plan_id') != PLAN_ID
            or value.get('mode') != 'BROKERLESS_PAPER' or value.get('real_money_eligible') is not False):
        raise ValueError('invalid_schb_paper_state')
    return value


def save(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix='.schb-paper-', delete=False) as f:
        json.dump(state, f, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
        tmp = Path(f.name)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


# ---------- moteur ----------
def advance(state, bundle, now, fee=FEE, slippage=SLIPPAGE, min_commission=MIN_COMMISSION):
    for value in (fee, slippage, min_commission):
        if isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid_cost')
    if fee > 0.02 or slippage > 0.02 or min_commission > 5:
        raise ValueError('invalid_cost')
    bars = bundle['bars']
    series = {SYMBOL: bars}
    dates = [b['date'] for b in bars]

    def record_alerts(i):
        state['peak_equity'] = max(state['peak_equity'], state['equity'])
        peak = state['peak_equity']
        dd = (peak - state['equity']) / peak * 100 if peak else 0.0
        state['max_drawdown_pct'] = max(state['max_drawdown_pct'], dd)
        for level in ALERT_LEVELS_PCT:
            if dd >= level and not any(a['level_pct'] == level and a['peak'] == round(peak, 4) for a in state['alerts']):
                state['alerts'].append({'session': bars[i]['close_at'], 'level_pct': level, 'peak': round(peak, 4),
                                        'drawdown_pct': round(dd, 4), 'action': 'notify_only'})

    def decide(i, reason):
        target, details = choose(series, i)
        info = details.get(SYMBOL, {})
        state['decisions'].append({'session': bars[i]['close_at'], 'reason': reason,
                                   'target': target or 'cash', 'close': info.get('close'),
                                   'sma200': None if info.get('sma200') is None else round(info['sma200'], 4)})
        state['decisions'] = state['decisions'][-36:]
        holding = SYMBOL if state['shares'] else None
        state['pending'] = {'target': target, 'decided_at': bars[i]['close_at'], 'reason': reason} if target != holding else None

    def execute(i):
        order = state['pending']
        state['pending'] = None
        bar = bars[i]
        if order['target'] is None and state['shares']:
            price = bar['open'] * (1 - slippage)
            gross = state['shares'] * price
            commission = max(min_commission, gross * fee)
            state['cash'] += gross - commission
            profit = gross - commission - state['entry_cost']
            state['orders'].append({'session': bar['close_at'], 'side': 'sell', 'symbol': SYMBOL,
                                    'quantity': state['shares'], 'price': round(price, 6),
                                    'commission': round(commission, 6), 'reason': 'below_sma200_to_cash'})
            state['trades'].append({'symbol': SYMBOL, 'exit_session': bar['close_at'], 'quantity': state['shares'],
                                    'profit': round(profit, 6), 'reason': 'below_sma200_to_cash'})
            state['shares'], state['entry_cost'] = 0, 0.0
        elif order['target'] == SYMBOL and not state['shares']:
            price = bar['open'] * (1 + slippage)
            qty = math.floor(max(0.0, state['cash'] - min_commission) / (price * (1 + fee)) + 1e-12)
            if qty <= 0:
                state['orders'].append({'session': bar['close_at'], 'side': 'skipped', 'symbol': SYMBOL,
                                        'price': round(price, 6), 'reason': 'order_below_one_share'})
                return
            cost = qty * price + max(min_commission, qty * price * fee)
            state['cash'] -= cost
            state['shares'], state['entry_cost'] = qty, cost
            state['orders'].append({'session': bar['close_at'], 'side': 'buy', 'symbol': SYMBOL, 'quantity': qty,
                                    'price': round(price, 6), 'cost': round(cost, 6), 'reason': order['reason']})

    if state['last_session'] is None:
        # Décision initiale sur la dernière séance close connue à la création.
        anchor = state.get('bootstrap_session') or bars[-1]['close_at']
        idx = max((i for i, b in enumerate(bars) if stamp(b['close_at']) <= stamp(anchor)), default=None)
        if idx is None or idx < SMA_DAYS:
            raise ValueError('schb_insufficient_history')
        state['equity'] = state['cash']
        decide(idx, 'initial_allocation')
        state['last_session'] = bars[idx]['close_at']
    start = next((i for i, b in enumerate(bars) if stamp(b['close_at']) > stamp(state['last_session'])), None)
    if start is not None:
        for i in range(start, len(bars)):
            for day, ratio in bundle.get('splits', []):
                key = f'{day}:{ratio}'
                if day == dates[i] and key not in state['applied_splits']:
                    state['applied_splits'].append(key)
                    if state['shares']:
                        state['shares'] = int(round(state['shares'] * ratio))
            if state['pending']:
                execute(i)
            state['equity'] = state['cash'] + state['shares'] * bars[i]['close']
            record_alerts(i)
            if i > 0 and dates[i][:7] != dates[i - 1][:7]:
                decide(i, 'monthly_rebalance')
            state['last_session'] = bars[i]['close_at']
    state['positions'] = ({SYMBOL: {'quantity': state['shares'], 'cost': round(state['entry_cost'], 6)}}
                          if state['shares'] else {})
    state['updated_at'] = now.isoformat()
    return state


def summary(state):
    closed = state['trades']
    wins = sum(t['profit'] > 0 for t in closed)
    gains = sum(t['profit'] for t in closed if t['profit'] > 0)
    losses = -sum(t['profit'] for t in closed if t['profit'] < 0)
    return {'state': 'paper_active', 'mode': 'BROKERLESS_PAPER', 'plan_id': PLAN_ID, 'symbol': SYMBOL,
            'rule': 'monthly_sma200_whole_shares_or_cash',
            'equity': round(state['equity'], 4), 'return_pct': round((state['equity'] / state['initial_cash'] - 1) * 100, 4),
            'cash': round(state['cash'], 4), 'shares': state['shares'], 'open_positions': 1 if state['shares'] else 0,
            'closed_trades': len(closed), 'wins': wins, 'losses': len(closed) - wins,
            'win_rate_pct': round(wins / len(closed) * 100, 4) if closed else None,
            'profit_factor': round(gains / losses, 4) if losses else None,
            'expectancy': round(sum(t['profit'] for t in closed) / len(closed), 4) if closed else None,
            'max_drawdown_pct': round(state['max_drawdown_pct'], 4),
            'pending_target': (state['pending'] or {}).get('target', 'none') if state['pending'] else None,
            'alerts_notify_only': len(state['alerts']), 'halted': False, 'halt_reason': None,
            'blocked_reason': None, 'execution_revision': PLAN_ID,
            'execution_revision_started_at': state.get('execution_revision_started_at'),
            'last_session': state['last_session'], 'real_money_eligible': False}
