"""Read-only initial setup check. Never submits or activates broker orders."""
from .data import finite
from .paper_broker import PaperBroker


def check(key=None, secret=None, symbols=(), initial=100, broker_factory=PaperBroker):
    result = {'state': 'awaiting_setup', 'mode': 'PAPER', 'currency': 'USD',
              'connection_verified': False, 'initial_setup_ready': False,
              'broker_orders_activated': False, 'real_money_eligible': False,
              'strategy_validated': False, 'checks': {}}
    checks = result['checks']
    try:
        initial = finite(initial, 0.01)
        if initial != 100:
            raise ValueError('initial_limit')
        checks['credentials_present'] = bool(key and secret)
        checks['one_or_two_distinct_symbols'] = 1 <= len(symbols) <= 2 and len(set(symbols)) == len(symbols)
        if not checks['credentials_present'] or not checks['one_or_two_distinct_symbols']:
            return result
        broker = broker_factory(key, secret, symbols)
        account = broker.request('GET', 'account')
        positions = broker.request('GET', 'positions')
        orders = broker.request('GET', 'orders', query={'status': 'open', 'limit': 500})
        clock = broker.request('GET', 'clock')
        checks['account_active'] = account.get('status') == 'ACTIVE'
        checks['trading_unblocked'] = all(account.get(k) is False for k in
            ['trading_blocked', 'account_blocked', 'trade_suspended_by_user'])
        checks['currency_usd'] = account.get('currency') == 'USD'
        checks['cash_and_equity_match_initial'] = all(abs(finite(account[k], 0) - initial) < 0.005 for k in ['cash', 'equity'])
        checks['no_existing_positions'] = isinstance(positions, list) and not positions
        checks['no_pending_orders'] = isinstance(orders, list) and not orders
        checks['clock_readable'] = isinstance(clock.get('is_open'), bool)
        # A closed market does not prevent checking connectivity on a weekend.
        result['market_open'] = clock.get('is_open') if checks['clock_readable'] else None
        assets = [broker.request('GET', 'assets/' + symbol) for symbol in symbols]
        checks['assets_tradable_us_equities'] = all(a.get('class') == 'us_equity' and
            a.get('status') == 'active' and a.get('tradable') is True for a in assets)
        result['connection_verified'] = True
        result['initial_setup_ready'] = all(checks.values())
        result['state'] = 'initial_setup_ready' if result['initial_setup_ready'] else 'setup_mismatch'
    except Exception as exc:
        # Never return account identities, credentials or upstream error text.
        result.update(state='verification_failed', error_type=type(exc).__name__)
    return result
