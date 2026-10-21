import ast
import datetime as dt
import json
import unittest
from pathlib import Path

from research_lab.slow_trend import (align, choose, max_affordable_price, simulate,
                                     unadjust_splits)

ROOT = Path(__file__).resolve().parents[1]


def bars(prices, start='2020-01-01'):
    day = dt.date.fromisoformat(start)
    out = []
    for i, p in enumerate(prices):
        d = (day + dt.timedelta(days=i)).isoformat()
        out.append({'date': d, 'open': p, 'high': p, 'low': p, 'close': p, 'volume': 1})
    return out


class SlowTrendTests(unittest.TestCase):
    def test_choose_is_causal(self):
        a = bars([100 + i for i in range(400)])
        b = bars([100 + 0.5 * i for i in range(400)])
        series = align({'A': a, 'B': b})
        ref = choose(series, 300)
        mutated = {'A': a[:301] + bars([1] * 99, a[301]['date']), 'B': b}
        self.assertEqual(choose(align(mutated), 300), ref)
        self.assertEqual(ref[0], 'A')

    def test_cash_below_sma200(self):
        down = bars([500 - i for i in range(400)])
        self.assertIsNone(choose({'A': down}, 350)[0])
        result = simulate({'A': down}, start_date='2020-09-01')
        self.assertEqual(result['orders'], 0)
        self.assertAlmostEqual(result['final'], 100.0)

    def test_whole_units_and_skip(self):
        expensive = bars([150 + i for i in range(400)])
        result = simulate({'X': expensive}, start_date='2020-09-01', whole_units=True)
        self.assertEqual(result['orders'], 0)
        self.assertTrue(any(t['side'] == 'skipped' for t in result['trades']))
        cheap = bars([30 + 0.1 * i for i in range(400)])
        buys = [t for t in simulate({'X': cheap}, start_date='2020-09-01', whole_units=True)['trades'] if t['side'] == 'buy']
        self.assertTrue(buys and all(float(t['qty']).is_integer() for t in buys))

    def test_split_unadjust(self):
        raw = unadjust_splits(bars([10.0] * 4), [('2020-01-03', 2.0)])
        self.assertEqual([b['close'] for b in raw], [20.0, 20.0, 10.0, 10.0])
        self.assertEqual(raw[2].get('split_ratio'), 2.0)

    def test_alerts_are_notify_only(self):
        prices = [100 + i for i in range(300)] + [399 - 3 * i for i in range(40)]
        result = simulate({'A': bars(prices)}, start_date='2020-08-01', rule='buy_hold')
        self.assertTrue(result['alerts'])
        self.assertTrue(all(a['action'] == 'notify_only' for a in result['alerts']))
        self.assertEqual([t['side'] for t in result['trades']], ['buy'])

    def test_costs_validated_and_doubled_costs_cost_more(self):
        with self.assertRaises(ValueError):
            simulate({'A': bars([1] * 300)}, fee=0.5)
        s = {'A': bars([100 + i for i in range(400)])}
        base = simulate(s, start_date='2020-09-01', rule='buy_hold')
        doubled = simulate(s, start_date='2020-09-01', rule='buy_hold', fee=0.005, slippage=0.002)
        self.assertLess(doubled['final'], base['final'])

    def test_legacy_paper_order_cannot_buy_above_about_10_usd(self):
        # worker.py : allocation 10 EUR (~11.6 USD), commission minimale 1 USD.
        limit = max_affordable_price(11.6, 0.001, 1.0)
        self.assertLess(limit, 10.7)
        self.assertGreater(max_affordable_price(100.0, 0.0035, 0.0), 29.51)

    def test_monthly_rotation_strategy_static(self):
        src = (ROOT / 'user_data/strategies/MoussaMonthlyRotation.py').read_text()
        tree = ast.parse(src)
        names = {n.targets[0].id: ast.literal_eval(n.value) for c in tree.body if isinstance(c, ast.ClassDef)
                 for n in c.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and isinstance(n.value, (ast.Constant, ast.UnaryOp))}
        self.assertEqual(names['timeframe'], '1d')
        self.assertEqual(names['stoploss'], -1.0)
        self.assertFalse(names['can_short'])
        self.assertIn('monthly_rotation_strategy_is_simulation_only', src)
        self.assertIn('min(max_stake, 20.0', src)
        cfg = json.loads((ROOT / 'user_data/config.monthly-rotation.research.json').read_text())
        self.assertTrue(cfg['dry_run'])
        self.assertEqual(cfg['exchange']['key'], '')
        self.assertEqual(cfg['exchange']['secret'], '')
        self.assertIn('MoussaMonthlyRotation', (ROOT / 'scripts/run_bias_checks.py').read_text())


if __name__ == '__main__':
    unittest.main()
