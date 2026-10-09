"""Persistent brokerless equity paper portfolio. No account and no order API."""
import json, math, os, tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .data import finite, stamp
from .engine import check_spec
from .portfolio_risk import entry_budget

SCHEMA = 1
PAPER_ENGINE_VERSION = 2
EXECUTION_REVISION = 'paper_engine_v2'
MARKET_TIMEZONE = ZoneInfo('America/New_York')

def new_state(now=None, initial=100, last_session=None):
    now = now or datetime.now(timezone.utc)
    return {'schema_version': SCHEMA, 'created_at': now.isoformat(), 'updated_at': now.isoformat(),
            'mode': 'BROKERLESS_PAPER', 'currency': 'USD', 'initial_cash': initial, 'cash': initial,
            'positions': {}, 'trades': [], 'equity': initial, 'peak_equity': initial,
            'max_drawdown_pct': 0.0, 'last_session': last_session, 'real_money_eligible': False,
            'paper_engine_version': PAPER_ENGINE_VERSION, 'execution_revision': EXECUTION_REVISION,
            'execution_revision_started_at': now.isoformat(), 'halted': False, 'halt_reason': None}

def load(path, now=None, last_session=None):
    path=Path(path)
    if not path.exists(): return new_state(now, last_session=last_session)
    value=json.loads(path.read_text())
    if value.get('schema_version') != SCHEMA or value.get('mode') != 'BROKERLESS_PAPER' or value.get('real_money_eligible') is not False:
        raise ValueError('invalid_equity_paper_state')
    return value

def save(path, state):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix='.equity-paper-', delete=False) as f:
        json.dump(state,f,indent=2,allow_nan=False); f.flush(); os.fsync(f.fileno()); tmp=Path(f.name)
    os.chmod(tmp,0o600); os.replace(tmp,path)

def _history(asset, i, n): return asset['bars'][max(0,i-n):i]
def _entry(asset,i,spec):
    h=_history(asset,i,max(spec['slow'],spec['breakout']+1))
    if len(h)<max(spec['slow'],spec['breakout']+1): return False
    fast=sum(x['close'] for x in h[-spec['fast']:])/spec['fast']; slow=sum(x['close'] for x in h[-spec['slow']:])/spec['slow']
    entry = fast>slow and h[-1]['close']>max(x['high'] for x in h[-spec['breakout']-1:-1])
    if entry and 'min_volume_ratio' in spec:
        volume_window = h[-20:]
        mean_volume = sum(bar['volume'] for bar in volume_window) / len(volume_window)
        entry = mean_volume > 0 and h[-1]['volume'] >= mean_volume * spec['min_volume_ratio']
    if entry and ('min_atr_pct' in spec or 'max_atr_pct' in spec):
        sample = h[-15:]
        ranges = []
        for j in range(1, len(sample)):
            high, low, previous = sample[j]['high'], sample[j]['low'], sample[j - 1]['close']
            ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
        atr_pct = (sum(ranges) / len(ranges)) / h[-1]['close'] if ranges else 0
        entry = spec.get('min_atr_pct', 0) <= atr_pct <= spec.get('max_atr_pct', 1)
    return entry
def _exit(asset,i,spec):
    h=_history(asset,i,spec['slow']); return len(h)>=spec['slow'] and h[-1]['close']<sum(x['close'] for x in h[-spec['slow']:])/spec['slow']

def _position_ages(state, dates):
    """Recover legacy age from known sessions, never a sliding bundle index."""
    if not state['positions']:
        return None
    known = {stamp(session): index for index, session in enumerate(dates)}
    last = stamp(state['last_session']) if state.get('last_session') else None
    if last not in known:
        return 'age_history_unavailable'
    recovered = {}
    for symbol, position in state['positions'].items():
        if 'held_sessions' in position:
            if (type(position['held_sessions']) is not int or position['held_sessions'] < 0
                    or not position.get('held_as_of') or stamp(position['held_as_of']) != last):
                return 'age_anchor_mismatch'
            continue
        entered = stamp(position['entry_session']) if position.get('entry_session') else None
        if entered not in known or entered > last:
            return 'age_history_unavailable'
        recovered[symbol] = known[last] - known[entered]
    # Apply the additive migration only once every position has known age.
    for symbol, age in recovered.items():
        state['positions'][symbol]['held_sessions'] = age
        state['positions'][symbol]['held_as_of'] = state['last_session']
    return None

def _corporate_action_block(assets, state, dates, now):
    """Refuse new action sessions before touching the persisted financial state."""
    last = stamp(state['last_session']) if state.get('last_session') else None
    fresh = [stamp(session) for session in dates
             if stamp(session) <= now and (last is None or stamp(session) > last)]
    first_day = last.astimezone(MARKET_TIMEZONE).date() if last else None
    end_day = fresh[-1].astimezone(MARKET_TIMEZONE).date() if fresh else None
    for asset in assets:
        actions = asset.get('corporate_actions', [])
        if not isinstance(actions, list) or len(actions) > 256:
            return 'corporate_action_metadata_invalid'
        for action in actions:
            if (not isinstance(action, dict) or action.get('kind') not in {'split', 'dividend'}
                    or not isinstance(action.get('date'), str)):
                return 'corporate_action_metadata_invalid'
            try:
                day = date.fromisoformat(action['date'])
            except ValueError:
                return 'corporate_action_metadata_invalid'
            if day.isoformat() != action['date']:
                return 'corporate_action_metadata_invalid'
            epoch = action.get('provider_epoch')
            if epoch is not None:
                try:
                    if type(epoch) is not int or epoch < 0:
                        return 'corporate_action_metadata_invalid'
                    provider_day = datetime.fromtimestamp(epoch, timezone.utc).astimezone(MARKET_TIMEZONE).date()
                except (OverflowError, OSError, ValueError):
                    return 'corporate_action_metadata_invalid'
                if provider_day != day:
                    return 'corporate_action_metadata_invalid'
            if end_day is not None and day <= end_day and (first_day is None or day > first_day):
                return 'corporate_action_requires_review'
    return None

def advance(bundle,state,spec,fee=.001,min_commission=1,slippage=.001,allocation=10,reserve_ratio=.10,max_drawdown=.05,now=None,risk_model=False,
            loss_stops=True, advisory=None, execution_revision=EXECUTION_REVISION):
    check_spec(spec); now=now or datetime.now(timezone.utc)
    max_drawdown = finite(max_drawdown, 0.00000001) if max_drawdown is not None else None
    if max_drawdown is not None and max_drawdown > .05:
        raise ValueError('invalid_paper_drawdown_limit')
    assets=bundle['assets']; dates=[x['close_at'] for x in assets[0]['bars']]
    if any([x['close_at'] for x in a['bars']]!=dates for a in assets): raise ValueError('paper_sessions_must_align')
    if any(stamp(left) >= stamp(right) for left, right in zip(dates, dates[1:])):
        raise ValueError('paper_sessions_must_increase')
    by_id = {asset['id']: asset for asset in assets}
    blocked = _corporate_action_block(assets, state, dates, now)
    if not blocked:
        blocked = ('position_market_data_unavailable' if set(state['positions']) - set(by_id)
                   else _position_ages(state, dates))
    state['paper_engine_version'] = PAPER_ENGINE_VERSION
    if state.get('execution_revision') != execution_revision:
        state['execution_revision'] = execution_revision
        state['execution_revision_started_at'] = now.isoformat()
    state['blocked_reason'] = blocked
    state['halted'] = bool(state.get('halted'))
    state.setdefault('halt_reason', None)
    # A historical breach remains a breach even if the legacy portfolio recovered.
    if max_drawdown is not None and state['max_drawdown_pct'] >= max_drawdown * 100:
        state['halted'] = True
        state['halt_reason'] = state['halt_reason'] or 'portfolio_drawdown'
    if blocked:
        state['updated_at'] = now.isoformat()
        return state

    def marked_equity(index, field):
        return state['cash'] + sum(position['quantity'] * by_id[symbol]['bars'][index][field]
                                   for symbol, position in state['positions'].items())

    def record_drawdown(equity):
        state['peak_equity'] = max(state['peak_equity'], equity)
        state['max_drawdown_pct'] = max(state['max_drawdown_pct'],
            (state['peak_equity'] - equity) / state['peak_equity'] * 100)

    def breached(equity):
        return max_drawdown is not None and (state['peak_equity'] - equity) / state['peak_equity'] + 1e-12 >= max_drawdown

    def sell(asset, session, price, reason):
        position = state['positions'].pop(asset['id'])
        gross = position['quantity'] * price * (1 - slippage)
        # No paper borrowing if the asset becomes virtually worthless.
        commission = max(min_commission, gross * fee)
        if max_drawdown is None:
            commission = min(commission, gross + state['cash'])
        proceeds = gross - commission
        state['cash'] += proceeds
        state['trades'].append({'asset': asset['id'], 'side': 'closed',
            'entry_session': position['entry_session'], 'exit_session': session,
            'quantity': position['quantity'], 'profit': proceeds - position['cost'], 'reason': reason})

    def halt_and_liquidate(index, session, field):
        state['halted'] = True
        state['halt_reason'] = state['halt_reason'] or 'portfolio_drawdown'
        for symbol in list(state['positions']):
            asset = by_id[symbol]
            sell(asset, session, asset['bars'][index][field], 'risk_halt_' + field)

    for i,session in enumerate(dates):
        if stamp(session)>now or (state['last_session'] and stamp(session)<=stamp(state['last_session'])): continue
        ai = advisory if advisory and advisory.get('as_of') and stamp(advisory['as_of']) <= stamp(session) else None
        for position in state['positions'].values():
            position['held_sessions'] += 1
            position['held_as_of'] = session
        # Liquidate a known opening breach before consulting future intraday prices.
        at_open = marked_equity(i, 'open')
        record_drawdown(at_open)
        if state['halted'] or breached(at_open):
            halt_and_liquidate(i, session, 'open')
        for a in assets:
            p=state['positions'].get(a['id']); bar=a['bars'][i]
            if not p:
                continue
            reason, exit_price = None, None
            stop = p['entry_price'] * (1 - spec['stop_loss'])
            # Position stops protect V2 too; risk_model only controls entry sizing.
            if loss_stops and bar['open'] <= stop:
                reason, exit_price = 'stop_loss_gap', bar['open']
            elif loss_stops and bar['low'] <= stop:
                reason, exit_price = 'stop_loss', stop
            previous_high = p.get('highest_price', p['entry_price'])
            activation, distance = spec.get('trailing_activation'), spec.get('trailing_distance')
            if loss_stops and reason is None and activation is not None and distance is not None and previous_high >= p['entry_price'] * (1 + activation):
                trail = previous_high * (1 - distance)
                if bar['open'] <= trail:
                    reason, exit_price = 'trailing_stop_gap', bar['open']
                elif bar['low'] <= trail:
                    reason, exit_price = 'trailing_stop', trail
            target = spec.get('take_profit')
            if reason is None and target is not None:
                target_price = p['entry_price'] * (1 + target)
                if bar['open'] >= target_price:
                    reason, exit_price = 'take_profit_gap', bar['open']
                elif bar['high'] >= target_price:
                    reason, exit_price = 'take_profit', target_price
            timed_out = p['held_sessions'] >= spec['max_hold']
            if reason is None and ai and ai.get('exit'):
                reason, exit_price = 'market_room_sell', bar['close']
            if reason is None and (_exit(a,i,spec) or timed_out):
                reason, exit_price = ('time_limit' if timed_out else 'trend_exit'), bar['close']
            if reason is not None:
                sell(a, session, exit_price, reason)
            else:
                p['highest_price'] = max(previous_high, bar['high'])
        equity_before = marked_equity(i, 'close')
        record_drawdown(equity_before)
        if state['halted'] or breached(equity_before):
            halt_and_liquidate(i, session, 'close')
        else:
            for a in assets:
                if a['id'] in state['positions'] or not _entry(a,i,spec) or (ai and not ai.get('allow_entry')): continue
                bar=a['bars'][i]; price=bar['close']*(1+slippage)
                usable=max(0,state['equity']*(1-reserve_ratio)-sum(p['cost'] for p in state['positions'].values()))
                budget=min(allocation * (ai['stake_multiplier'] if ai else 1),state['cash'],usable)
                if risk_model:
                    risk_budget,_=entry_budget(bundle,state,i,a,equity_before,allocation=allocation)
                    budget=min(budget,risk_budget)
                qty=math.floor(max(0,budget-min_commission)/(price*(1+fee)))
                if qty<=0: continue
                value=qty*price; cost=value+max(min_commission,value*fee)
                if cost>budget: continue
                state['cash']-=cost
                state['positions'][a['id']]={'quantity':qty,'cost':cost,'entry_price':price,
                    'entry_session':session,'entry_index':i,'highest_price':price,
                    'held_sessions':0,'held_as_of':session, 'advisory_id': ai.get('id') if ai else None}
                # Stop this session's remaining entries as soon as fill costs breach risk.
                equity_after_entry = marked_equity(i, 'close')
                record_drawdown(equity_after_entry)
                if breached(equity_after_entry):
                    halt_and_liquidate(i, session, 'close')
                    break
        state['equity'] = marked_equity(i, 'close')
        record_drawdown(state['equity'])
        state['last_session'] = session
    state['updated_at']=now.isoformat(); return state

def summary(state):
    closed=state['trades']; wins=sum(t['profit']>0 for t in closed); losses=sum(t['profit']<=0 for t in closed)
    gains=sum(t['profit'] for t in closed if t['profit']>0)
    gross_loss=-sum(t['profit'] for t in closed if t['profit']<0)
    status = 'paper_blocked' if state.get('blocked_reason') else ('paper_halted' if state.get('halted') else 'paper_active')
    return {'state':status,'mode':state['mode'],'equity':round(state['equity'],4),
            'return_pct':round((state['equity']/state['initial_cash']-1)*100,4),
            'cash':round(state['cash'],4),'open_positions':len(state['positions']),
            'closed_trades':len(closed),'wins':wins,'losses':losses,
            'win_rate_pct':round(wins/len(closed)*100,4) if closed else None,
            'profit_factor':round(gains/gross_loss,4) if gross_loss else None,
            'expectancy':round(sum(t['profit'] for t in closed)/len(closed),4) if closed else None,
            'max_drawdown_pct':round(state['max_drawdown_pct'],4),
            'halted':bool(state.get('halted')), 'halt_reason':state.get('halt_reason'),
            'blocked_reason':state.get('blocked_reason'),
            'paper_engine_version':state.get('paper_engine_version',1),
            'execution_revision':state.get('execution_revision','legacy'),
            'execution_revision_started_at':state.get('execution_revision_started_at'),
            'execution_model':'prior_closed_signal_current_close_paper_fills_with_intraday_exit_hypotheses',
            'performance_history_preserved':True,
            'last_session':state['last_session'],'real_money_eligible':False}
