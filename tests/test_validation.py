import unittest
from datetime import datetime, timezone

from supervisor.validation import load_thresholds, evaluate, consecutive_losses

NOW = datetime(2026, 12, 1, tzinfo=timezone.utc)
GOOD = {'closed_trades': 40, 'wins': 22, 'profit_factor': 1.5, 'max_drawdown_pct': 3.0,
        'realized_profit_eur': 4.0, 'fees_paid_eur': 2.0, 'first_open_date': '2026-10-13 10:00:00',
        'recent_profits': [0.01, -0.01, 0.02]}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.t = load_thresholds()

    def test_thresholds_fixed_and_simulation_only(self):
        self.assertEqual(self.t['promotion']['min_profit_factor'], 1.2)
        self.assertEqual(self.t['promotion']['max_drawdown_pct'], 5.0)
        self.assertGreaterEqual(self.t['promotion']['min_closed_trades'], 30)
        self.assertFalse(self.t['real_money_eligible'])

    def test_candidate_never_real_money(self):
        result = evaluate(GOOD, self.t, NOW)
        self.assertEqual(result, {'verdict': 'candidate', 'reasons': [], 'real_money_eligible': False})

    def test_current_market_room_state_is_continue_or_stop(self):
        # 23 clôtures, 1 gain, -2,92 EUR, DD 2,93 % : chiffres observés le 13/10.
        stats = {'closed_trades': 23, 'wins': 1, 'profit_factor': None, 'max_drawdown_pct': 2.9294,
                 'realized_profit_eur': -2.9196, 'fees_paid_eur': None, 'first_open_date': '2026-10-09 20:00:00',
                 'recent_profits': [-0.02] * 12}
        result = evaluate(stats, self.t, NOW)
        self.assertEqual(result['verdict'], 'stop')
        self.assertIn('consecutive_losses_stop', result['reasons'])

    def test_stop_rules(self):
        self.assertIn('drawdown_stop', evaluate({**GOOD, 'max_drawdown_pct': 5.0}, self.t, NOW)['reasons'])
        self.assertIn('profit_factor_stop', evaluate({**GOOD, 'profit_factor': 0.5}, self.t, NOW)['reasons'])
        self.assertEqual(evaluate({**GOOD, 'closed_trades': 10, 'profit_factor': 0.5}, self.t, NOW)['verdict'], 'continue')

    def test_missing_data_is_never_favourable(self):
        for key, reason in [('closed_trades', 'insufficient_trades'), ('profit_factor', 'profit_factor_below_threshold'),
                            ('max_drawdown_pct', 'drawdown_unknown_or_above_threshold'),
                            ('first_open_date', 'insufficient_observation_days'), ('fees_paid_eur', 'fees_unknown'),
                            ('realized_profit_eur', 'net_return_not_positive')]:
            with self.subTest(key=key):
                result = evaluate({**GOOD, key: None}, self.t, NOW)
                self.assertEqual(result['verdict'], 'continue')
                self.assertIn(reason, result['reasons'])

    def test_boundaries_and_fees(self):
        self.assertIn('profit_factor_below_threshold', evaluate({**GOOD, 'profit_factor': 1.2}, self.t, NOW)['reasons'])
        self.assertIn('insufficient_observation_days', evaluate(GOOD, self.t, datetime(2026, 11, 1, tzinfo=timezone.utc))['reasons'])
        self.assertIn('fees_dominate_gross_profit', evaluate({**GOOD, 'fees_paid_eur': 5.0}, self.t, NOW)['reasons'])

    def test_consecutive_losses(self):
        self.assertEqual(consecutive_losses([0.1, -0.1, 0.0, -0.2]), 3)
        self.assertEqual(consecutive_losses([-0.1, 0.1]), 0)
        self.assertEqual(consecutive_losses([]), 0)


if __name__ == '__main__':
    unittest.main()
