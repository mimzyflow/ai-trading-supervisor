import json
import unittest
from types import SimpleNamespace
from research_lab.paper_readiness import check


class ReadinessTests(unittest.TestCase):
    def inspect(self, overrides=None):
        responses = {'account': {'status': 'ACTIVE', 'currency': 'USD', 'cash': '100', 'equity': '100',
                                 'trading_blocked': False, 'account_blocked': False, 'trade_suspended_by_user': False, 'id': 'private-account'},
                     'positions': [], 'orders': [], 'clock': {'is_open': False},
                     'assets/TOY': {'class': 'us_equity', 'status': 'active', 'tradable': True}}
        responses.update(overrides or {})
        calls = []
        def request(method, path, **kwargs):
            self.assertEqual(method, 'GET')
            calls.append(path)
            return responses[path]
        return (lambda *a: SimpleNamespace(request=request)), calls

    def test_missing_keys_or_universe_never_contacts_provider(self):
        def forbidden(*a): self.fail('No connection without complete setup')
        for key, secret, symbols in [(None, None, ['TOY']), ('k', 's', []), ('k', 's', ['TOY', 'TOY'])]:
            result = check(key, secret, symbols, broker_factory=forbidden)
            self.assertEqual(result['state'], 'awaiting_setup')
            self.assertFalse(result['connection_verified'])

    def test_read_only_setup_can_pass_while_market_is_closed(self):
        factory, calls = self.inspect()
        result = check('k', 's', ['TOY'], broker_factory=factory)
        self.assertTrue(result['initial_setup_ready'])
        self.assertFalse(result['market_open'])
        self.assertFalse(result['broker_orders_activated'])
        self.assertFalse(result['strategy_validated'])
        self.assertFalse(result['real_money_eligible'])
        self.assertEqual(calls, ['account', 'positions', 'orders', 'clock', 'assets/TOY'])
        self.assertNotIn('private-account', json.dumps(result))

    def test_default_hundred_thousand_balance_is_not_experimental_hundred(self):
        factory, _ = self.inspect({'account': {'status': 'ACTIVE', 'currency': 'USD', 'cash': '100000',
            'equity': '100000', 'trading_blocked': False, 'account_blocked': False, 'trade_suspended_by_user': False}})
        result = check('k', 's', ['TOY'], broker_factory=factory)
        self.assertEqual(result['state'], 'setup_mismatch')
        self.assertFalse(result['checks']['cash_and_equity_match_initial'])

    def test_existing_position_order_or_wrong_currency_is_not_pristine_setup(self):
        for change in [{'positions': [{'symbol': 'TOY'}]}, {'orders': [{'id': 'pending'}]},
            {'account': {'status': 'ACTIVE', 'currency': 'EUR', 'cash': '100', 'equity': '100',
                         'trading_blocked': False, 'account_blocked': False, 'trade_suspended_by_user': False}}]:
            factory, _ = self.inspect(change)
            self.assertFalse(check('k', 's', ['TOY'], broker_factory=factory)['initial_setup_ready'])

    def test_invalid_or_excessive_initial_never_connects(self):
        def forbidden(*a): self.fail('Invalid budget must not connect')
        for initial in [0, 50, 101, True, float('nan')]:
            self.assertEqual(check('k', 's', ['TOY'], initial, forbidden)['state'], 'verification_failed')

    def test_upstream_error_never_exposes_private_text(self):
        def fail(*a): raise RuntimeError('private-key secret-value')
        result = check('private-key', 'secret-value', ['TOY'], broker_factory=fail)
        self.assertEqual(result['state'], 'verification_failed')
        self.assertNotIn('private-key', json.dumps(result))
        self.assertNotIn('secret-value', json.dumps(result))

    def test_unknown_or_blocked_trading_flags_cannot_pass(self):
        for field in ['trading_blocked', 'account_blocked', 'trade_suspended_by_user']:
            for value in [True, None]:
                factory, _ = self.inspect({'account': {'status': 'ACTIVE', 'currency': 'USD', 'cash': '100',
                    'equity': '100', 'trading_blocked': False, 'account_blocked': False,
                    'trade_suspended_by_user': False, field: value}})
                self.assertFalse(check('k', 's', ['TOY'], broker_factory=factory)['initial_setup_ready'])
