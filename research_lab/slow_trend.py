"""Rotation mensuelle lente (tendance), simulation uniquement.

Règle figée avant test :
- décision à la clôture de la PREMIÈRE séance de chaque mois (données <= cette clôture) ;
- exécution à l'ouverture de la séance suivante ;
- candidat retenu = actif au meilleur momentum 90 séances, seulement si sa clôture
  est au-dessus de sa SMA200 quotidienne ; sinon cash ;
- crypto : quantités fractionnaires ; actions/ETF : parts entières ;
- frais par côté + glissement par côté explicites ; commission minimale optionnelle ;
- alertes de baisse 5 % et 10 % en notify_only : aucune vente, aucun arrêt.
Aucun ordre, aucune clé, aucun courtier.
"""
import math

MOMENTUM_DAYS = 90
SMA_DAYS = 200
ALERT_LEVELS_PCT = (5.0, 10.0)


def _check_series(series):
    if not series:
        raise ValueError('empty_universe')
    dates = [b['date'] for b in next(iter(series.values()))]
    for bars in series.values():
        if [b['date'] for b in bars] != dates:
            raise ValueError('sessions_must_align')
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError('sessions_must_increase')
    return dates


def align(series):
    """Keep only dates common to every asset (crypto vs. missing days)."""
    common = set.intersection(*(set(b['date'] for b in bars) for bars in series.values()))
    return {k: [b for b in bars if b['date'] in common] for k, bars in series.items()}


def choose(series, index, momentum_days=MOMENTUM_DAYS, sma_days=SMA_DAYS):
    """Causal choice using closes up to and including `index` only."""
    if index < max(momentum_days, sma_days - 1):
        return None, {}
    details = {}
    best, best_mom = None, None
    for name, bars in series.items():
        close = bars[index]['close']
        sma = sum(b['close'] for b in bars[index - sma_days + 1:index + 1]) / sma_days
        mom = close / bars[index - momentum_days]['close'] - 1
        details[name] = {'close': close, 'sma200': sma, 'momentum90': mom, 'above_sma': close > sma}
        if close > sma and (best_mom is None or mom > best_mom):
            best, best_mom = name, mom
    return best, details


def unadjust_splits(bars, splits):
    """Yahoo `close` est ajusté des divisions ; reconstruit des prix bruts.

    `splits` : liste de (date_iso, ratio). Les prix antérieurs à une division sont
    multipliés par son ratio ; la séance de division porte `split_ratio`.
    Les dividendes ne sont pas réinvestis (prix hors dividendes).
    """
    out = []
    for bar in bars:
        factor = 1.0
        for day, ratio in splits:
            if bar['date'] < day:
                factor *= ratio
        raw = {**bar, **{k: bar[k] * factor for k in ('open', 'high', 'low', 'close')}}
        raw.pop('split_ratio', None)
        ratio_today = [r for d, r in splits if d == bar['date']]
        if ratio_today:
            raw['split_ratio'] = ratio_today[0]
        out.append(raw)
    return out


def max_affordable_price(allocation, fee=0.0, min_commission=0.0):
    """Highest share price that still buys 1 whole share with this order size."""
    return max(0.0, (allocation - min_commission) / (1 + fee))


def simulate(series, initial=100.0, fee=0.0025, slippage=0.0010, min_commission=0.0,
             whole_units=False, start_date=None, end_date=None, rule='rotation'):
    """rule='rotation' (stratégie) ou 'buy_hold' (référence équipondérée, achat unique)."""
    for value in (fee, slippage, min_commission):
        if isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid_cost')
    if fee > 0.02 or slippage > 0.02 or initial > 100:
        raise ValueError('simulation_bounds_exceeded')
    dates = _check_series(series)
    first = next((i for i, d in enumerate(dates) if not start_date or d >= start_date), None)
    last = max((i for i, d in enumerate(dates) if not end_date or d <= end_date), default=None)
    if first is None or last is None or last <= first:
        raise ValueError('empty_window')
    cash, holding, qty = float(initial), None, 0.0
    trades, curve, alerts = [], [], []
    peak, max_dd = initial, 0.0

    def mark(i, field='close'):
        return cash + (qty * series[holding][i][field] if holding else 0.0)

    def sell(i, reason):
        nonlocal cash, holding, qty
        price = series[holding][i]['open'] * (1 - slippage)
        gross = qty * price
        commission = max(min_commission, gross * fee) if gross > 0 else 0.0
        cash += gross - commission
        trades.append({'date': dates[i], 'side': 'sell', 'asset': holding, 'qty': qty,
                       'price': price, 'commission': commission, 'reason': reason})
        holding, qty = None, 0.0

    def buy(i, name, budget):
        nonlocal cash, holding, qty
        price = series[name][i]['open'] * (1 + slippage)
        spend = max(0.0, budget - min_commission)
        units = spend / (price * (1 + fee))
        if whole_units:
            units = math.floor(units + 1e-12)
        if units <= 0:
            trades.append({'date': dates[i], 'side': 'skipped', 'asset': name,
                           'reason': 'order_below_one_unit', 'price': price})
            return
        value = units * price
        commission = max(min_commission, value * fee)
        if value + commission > cash + 1e-9:
            return
        cash -= value + commission
        holding, qty = name, units
        trades.append({'date': dates[i], 'side': 'buy', 'asset': name, 'qty': units,
                       'price': price, 'commission': commission, 'reason': rule})

    pending = None  # None = rien à faire ; sinon ('target', nom ou None pour cash)
    for i in range(first, last + 1):
        if holding and series[holding][i].get('split_ratio'):
            # Prix bruts non ajustés : une division multiplie les parts détenues.
            qty *= float(series[holding][i]['split_ratio'])
        if pending is not None:
            target = pending[1]
            pending = None
            if rule == 'buy_hold':
                buy(i, target, cash)
            elif target != holding:
                if holding:
                    sell(i, 'rebalance' if target else 'to_cash')
                if target:
                    buy(i, target, cash)
        equity = mark(i)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak else 0.0
        max_dd = max(max_dd, dd)
        for level in ALERT_LEVELS_PCT:
            if dd >= level and not any(a['level_pct'] == level and a['peak'] == peak for a in alerts):
                alerts.append({'date': dates[i], 'level_pct': level, 'peak': peak,
                               'drawdown_pct': round(dd, 4), 'action': 'notify_only'})
        curve.append({'date': dates[i], 'equity': equity})
        if i == last:
            break
        month_start = i == first or dates[i][:7] != dates[i - 1][:7]
        if rule == 'buy_hold':
            # Référence : achat unique du premier actif listé (nouvel essai mensuel
            # tant qu'une part entière n'est pas achetable), conservé jusqu'à la fin.
            if holding is None and month_start:
                pending = ('target', next(iter(series)))
            continue
        if month_start:
            target, _ = choose(series, i)
            if target != holding:
                pending = ('target', target)
    final = curve[-1]['equity']
    sells = [t for t in trades if t['side'] == 'sell']
    return {'initial': initial, 'final': round(final, 4), 'return_pct': round((final / initial - 1) * 100, 4),
            'max_drawdown_pct': round(max_dd, 4), 'trades': trades,
            'orders': sum(t['side'] in ('buy', 'sell') for t in trades),
            'round_trips': len(sells), 'alerts': alerts, 'start': dates[first], 'end': dates[last],
            'curve': curve}

