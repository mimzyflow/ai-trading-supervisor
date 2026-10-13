"""Critères de validation fixés d'avance (simulation uniquement).

Lecture d'un résumé de compte (ex. bloc current_experiment de trading_status)
et verdict déterministe. Ne déclenche aucune action : le verdict n'autorise
jamais d'ordre réel (real_money_eligible reste False).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

THRESHOLDS = Path(__file__).resolve().parents[1] / 'config' / 'validation-thresholds.json'


def load_thresholds(path=THRESHOLDS):
    value = json.loads(Path(path).read_text())
    if (value.get('schema_version') != 1 or value.get('scope') != 'SIMULATION_ONLY'
            or value.get('real_money_eligible') is not False):
        raise ValueError('invalid_validation_thresholds')
    return value


def _date(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00').replace(' ', 'T'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def consecutive_losses(profits):
    count = 0
    for profit in reversed(list(profits)):
        if profit is None or profit > 0:
            break
        count += 1
    return count


def evaluate(stats, thresholds=None, now=None, initial_eur=100.0):
    """stats : closed_trades, profit_factor, max_drawdown_pct, realized_profit_eur,
    first_open_date, fees_paid_eur, recent_profits (ordre chronologique, optionnel).

    Retourne {'verdict': 'stop'|'continue'|'candidate', 'reasons': [...], 'real_money_eligible': False}.
    Donnée manquante = critère non satisfait (jamais supposé favorable).
    """
    t = thresholds or load_thresholds()
    now = now or datetime.now(timezone.utc)
    promo, stop = t['promotion'], t['stop']
    trades = stats.get('closed_trades')
    pf = stats.get('profit_factor')
    dd = stats.get('max_drawdown_pct')
    pnl = stats.get('realized_profit_eur')
    fees = stats.get('fees_paid_eur')

    stop_reasons = []
    if dd is not None and dd >= stop['max_drawdown_pct']:
        stop_reasons.append('drawdown_stop')
    if consecutive_losses(stats.get('recent_profits') or []) >= stop['max_consecutive_losses']:
        stop_reasons.append('consecutive_losses_stop')
    early = stop['min_profit_factor_after_trades']
    if trades is not None and trades >= early['trades'] and pf is not None and pf < early['profit_factor']:
        stop_reasons.append('profit_factor_stop')
    if stop_reasons:
        return {'verdict': 'stop', 'reasons': stop_reasons, 'real_money_eligible': False}

    reasons = []
    if trades is None or trades < promo['min_closed_trades']:
        reasons.append('insufficient_trades')
    first = _date(stats.get('first_open_date'))
    if first is None or (now - first).days < promo['min_observation_days']:
        reasons.append('insufficient_observation_days')
    if pf is None or pf <= promo['min_profit_factor']:
        reasons.append('profit_factor_below_threshold')
    if dd is None or dd >= promo['max_drawdown_pct']:
        reasons.append('drawdown_unknown_or_above_threshold')
    if pnl is None or pnl / initial_eur * 100 <= promo['min_net_return_pct']:
        reasons.append('net_return_not_positive')
    share = promo.get('max_fees_share_of_gross_profit_pct')
    if share is not None:
        if fees is None or pnl is None:
            reasons.append('fees_unknown')
        elif pnl + fees > 0 and fees / (pnl + fees) * 100 > share:
            reasons.append('fees_dominate_gross_profit')
    win_min = promo.get('min_win_rate_pct')
    if win_min is not None:
        wins = stats.get('wins')
        if not trades or wins is None or wins / trades * 100 < win_min:
            reasons.append('win_rate_below_threshold')
    return {'verdict': 'continue' if reasons else 'candidate', 'reasons': reasons, 'real_money_eligible': False}
