"""Long-only daily simulator: prior-close decisions, next-open execution.

It never sends orders. Emergency drawdown exits occur at the next open;
gaps and modeled costs can therefore exceed the halt threshold.
"""
import math
from .data import finite, validate, stamp

TEMPLATES = tuple({'family': 'trend_breakout', 'fast': fast, 'slow': slow,
                   'breakout': window, 'stop_loss': 0.05, 'max_hold': 60}
                  for fast, slow in [(20, 100), (50, 200)] for window in [20, 55])


def check_spec(spec):
    if spec.get('family') not in {'trend_breakout', 'buy_hold', 'cash'}:
        raise ValueError('unknown_template')
    if spec['family'] == 'trend_breakout':
        for key in ['fast', 'slow', 'breakout', 'max_hold']:
            if type(spec.get(key)) is not int or not 2 <= spec[key] <= 250:
                raise ValueError('invalid_template_parameter')
        if spec['fast'] >= spec['slow'] or not 0.005 <= finite(spec['stop_loss']) <= 0.10:
            raise ValueError('invalid_template_risk')


def simulate(bundle, spec, fee=0.008, min_commission=0, slippage=0.001,
             initial=100, allocation=20, max_drawdown=0.05, close_at_end=True,
             start_index=0, risk_control=True):
    validate(bundle)
    check_spec(spec)
    initial, allocation = finite(initial, 0.00000001), finite(allocation, 0.00000001)
    if initial > 100 or allocation > 20 or allocation * len(bundle['assets']) > initial * 0.4 + 1e-8:
        raise ValueError('simulation_budget_exceeded')
    fee, min_commission, slippage = finite(fee, 0), finite(min_commission, 0), finite(slippage, 0)
    if fee > 0.02 or slippage > 0.02 or not 0 < max_drawdown <= 0.05:
        raise ValueError('invalid_cost_or_risk_limit')
    cash, peak, worst = initial, initial, 0.0
    positions, receivables, trades, curve = {}, [], [], []
    halted, halt_pending, entry_attempts = False, False, 0
    assets = bundle['assets']
    if type(start_index) is not int or not 0 <= start_index < len(assets[0]['bars']):
        raise ValueError('invalid_test_start')

    def signal_history(asset, index):
        # Adjust only splits already effective by this session, never future actions.
        ratio = finite(asset['bars'][index].get('split_ratio', 1))
        history = []
        for bar in reversed(asset['bars'][:index]):
            history.append({key: bar[key] / ratio for key in ['close', 'high']})
            ratio *= finite(bar.get('split_ratio', 1))
        return list(reversed(history))

    def commission(value):
        return max(min_commission, value * fee)

    def sell(asset, bar, price, reason):
        nonlocal cash
        position = positions.pop(asset['id'])
        gross = position['quantity'] * price * (1 - slippage)
        proceeds = gross - commission(gross)
        cash += proceeds
        trades.append({'asset': asset['id'], 'entry_session': position['entry'],
                       'exit_session': bar['open_at'], 'reason': reason,
                       'profit': proceeds - position['cost'] + position['dividends'], 'quantity': position['quantity']})

    def buy(asset, bar, index):
        nonlocal cash, entry_attempts
        entry_attempts += 1
        price = finite(bar['open']) * (1 + slippage)
        lot = finite(asset.get('lot_size', 1), 0.00000001)
        budget = min(allocation, cash)
        quantity = math.floor(max(0, (budget - min_commission)) / (price * (1 + fee)) / lot) * lot
        quantity = min(quantity, math.floor(bar['volume'] * 0.01 / lot) * lot)
        if quantity <= 0:
            return
        value = quantity * price
        cost = value + commission(value)
        if cost > budget + 1e-8:
            return
        cash -= cost
        positions[asset['id']] = {'quantity': quantity, 'cost': cost, 'price': price,
                                  'entry': bar['open_at'], 'index': index, 'dividends': 0.0}

    for i in range(len(assets[0]['bars'])):
        current = [(asset, asset['bars'][i]) for asset in assets]
        # Only raw prices are accepted: splits change quantity/basis, not wealth.
        for asset, bar in current:
            position = positions.get(asset['id'])
            if position:
                split = finite(bar.get('split_ratio', 1))
                position['quantity'] *= split
                position['price'] /= split
                dividend = finite(bar.get('dividend_per_share', 0))
                if dividend:
                    amount = position['quantity'] * dividend
                    receivables.append((stamp(bar['dividend_paid_at']), amount))
                    position['dividends'] += amount
                    position['price'] = max(0.00000001, position['price'] - dividend)
        earliest = min(stamp(bar['open_at']) for _, bar in current)
        cash += sum(amount for paid, amount in receivables if paid <= earliest)
        receivables = [(paid, amount) for paid, amount in receivables if paid > earliest]
        at_open = cash + sum(amount for _, amount in receivables) + sum(
            positions[a['id']]['quantity'] * b['open'] for a, b in current if a['id'] in positions)
        if risk_control and (halt_pending or (peak - at_open) / peak >= max_drawdown):
            halted = True
        for asset, bar in current:
            position = positions.get(asset['id'])
            if not position:
                continue
            previous = signal_history(asset, i)
            trend_exit = False
            if spec['family'] == 'trend_breakout' and len(previous) >= spec['slow']:
                trend_exit = previous[-1]['close'] < sum(b['close'] for b in previous[-spec['slow']:]) / spec['slow']
            if halted or trend_exit or (spec['family'] == 'trend_breakout' and i - position['index'] >= spec['max_hold']):
                sell(asset, bar, bar['open'], 'risk_halt' if halted else 'trend_exit')
        if not halted and i >= start_index:
            for asset, bar in current:
                if asset['id'] in positions or bar['volume'] <= 0:
                    continue
                entry = spec['family'] == 'buy_hold' and i == start_index
                if spec['family'] == 'trend_breakout' and i >= max(spec['slow'], spec['breakout'] + 1):
                    previous = signal_history(asset, i)
                    fast = sum(b['close'] for b in previous[-spec['fast']:]) / spec['fast']
                    slow = sum(b['close'] for b in previous[-spec['slow']:]) / spec['slow']
                    breakout = max(b['high'] for b in previous[-spec['breakout']-1:-1])
                    entry = fast > slow and previous[-1]['close'] > breakout
                if entry:
                    buy(asset, bar, i)
        if spec['family'] == 'trend_breakout':
            for asset, bar in current:
                position = positions.get(asset['id'])
                if position:
                    stop = position['price'] * (1 - spec['stop_loss'])
                    if bar['low'] <= stop:
                        sell(asset, bar, min(stop, bar['open']), 'stop_loss')
        equity = cash + sum(amount for _, amount in receivables) + sum(
            positions[a['id']]['quantity'] * b['close'] for a, b in current if a['id'] in positions)
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
        halt_pending = risk_control and worst >= max_drawdown
        if i >= start_index:
            curve.append({'date': current[0][1]['close_at'], 'equity': equity})
    if close_at_end:
        for asset, bar in current:
            if asset['id'] in positions:
                sell(asset, {**bar, 'open_at': bar['close_at']}, bar['close'], 'fixed_horizon')
        equity = cash + sum(amount for _, amount in receivables)
        worst = max(worst, (peak - equity) / peak)
        curve[-1]['equity'] = equity
    gains = sum(t['profit'] for t in trades if t['profit'] > 0)
    losses = -sum(t['profit'] for t in trades if t['profit'] < 0)
    return {'return_pct': (equity / initial - 1) * 100, 'profit': equity - initial,
            'equity': equity, 'cash': cash, 'receivables': sum(amount for _, amount in receivables),
            'profit_factor': gains / losses if losses else None,
            'max_drawdown_pct': worst * 100, 'closed_trades': len(trades),
            'open_positions': len(positions), 'halted': halted or halt_pending,
            'entry_attempts': entry_attempts, 'trades': trades, 'curve': curve,
            'execution_model': 'prior-close_signal_next-open_with_costs', 'real_money_eligible': False}
