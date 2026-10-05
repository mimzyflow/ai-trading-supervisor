"""Persistent brokerless equity paper portfolio. No account and no order API."""
import json, math, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from .data import finite, stamp
from .engine import check_spec

SCHEMA = 1

def new_state(now=None, initial=100, last_session=None):
    now = now or datetime.now(timezone.utc)
    return {'schema_version': SCHEMA, 'created_at': now.isoformat(), 'updated_at': now.isoformat(),
            'mode': 'BROKERLESS_PAPER', 'currency': 'USD', 'initial_cash': initial, 'cash': initial,
            'positions': {}, 'trades': [], 'equity': initial, 'peak_equity': initial,
            'max_drawdown_pct': 0.0, 'last_session': last_session, 'real_money_eligible': False}

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
    return fast>slow and h[-1]['close']>max(x['high'] for x in h[-spec['breakout']-1:-1])
def _exit(asset,i,spec):
    h=_history(asset,i,spec['slow']); return len(h)>=spec['slow'] and h[-1]['close']<sum(x['close'] for x in h[-spec['slow']:])/spec['slow']

def advance(bundle,state,spec,fee=.001,min_commission=1,slippage=.001,allocation=10,reserve_ratio=.10,max_drawdown=.05,now=None):
    check_spec(spec); now=now or datetime.now(timezone.utc)
    assets=bundle['assets']; dates=[x['close_at'] for x in assets[0]['bars']]
    if any([x['close_at'] for x in a['bars']]!=dates for a in assets): raise ValueError('paper_sessions_must_align')
    for i,session in enumerate(dates):
        if stamp(session)>now or (state['last_session'] and session<=state['last_session']): continue
        # Prior-close signal, current session close as conservative paper fill; never future data.
        for a in assets:
            p=state['positions'].get(a['id']); bar=a['bars'][i]
            if p and (_exit(a,i,spec) or i-p['entry_index']>=spec['max_hold']):
                gross=p['quantity']*bar['close']*(1-slippage); commission=max(min_commission,gross*fee); proceeds=gross-commission
                state['cash']+=proceeds; state['trades'].append({'asset':a['id'],'side':'closed','entry_session':p['entry_session'],'exit_session':session,'quantity':p['quantity'],'profit':proceeds-p['cost'],'reason':'trend_or_time_exit'}); del state['positions'][a['id']]
        equity_before=state['cash']+sum(p['quantity']*next(a for a in assets if a['id']==k)['bars'][i]['close'] for k,p in state['positions'].items())
        if (state['peak_equity']-equity_before)/state['peak_equity'] < max_drawdown:
            for a in assets:
                if a['id'] in state['positions'] or not _entry(a,i,spec): continue
                bar=a['bars'][i]; price=bar['close']*(1+slippage); usable=max(0,state['equity']*(1-reserve_ratio)-sum(p['cost'] for p in state['positions'].values())); budget=min(allocation,state['cash'],usable)
                qty=math.floor(max(0,budget-min_commission)/(price*(1+fee)))
                if qty<=0: continue
                value=qty*price; cost=value+max(min_commission,value*fee)
                if cost>budget: continue
                state['cash']-=cost; state['positions'][a['id']]={'quantity':qty,'cost':cost,'entry_price':price,'entry_session':session,'entry_index':i}
        equity=state['cash']+sum(p['quantity']*next(a for a in assets if a['id']==k)['bars'][i]['close'] for k,p in state['positions'].items())
        state['equity']=equity; state['peak_equity']=max(state['peak_equity'],equity); state['max_drawdown_pct']=max(state['max_drawdown_pct'],(state['peak_equity']-equity)/state['peak_equity']*100); state['last_session']=session
    state['updated_at']=now.isoformat(); return state

def summary(state):
    closed=state['trades']; wins=sum(t['profit']>0 for t in closed); losses=sum(t['profit']<=0 for t in closed)
    return {'state':'paper_active','mode':state['mode'],'equity':round(state['equity'],4),'return_pct':round((state['equity']/state['initial_cash']-1)*100,4),'cash':round(state['cash'],4),'open_positions':len(state['positions']),'closed_trades':len(closed),'wins':wins,'losses':losses,'max_drawdown_pct':round(state['max_drawdown_pct'],4),'last_session':state['last_session'],'real_money_eligible':False}
