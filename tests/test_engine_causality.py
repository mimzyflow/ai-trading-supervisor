import copy
import unittest
from datetime import datetime, timedelta, timezone

from research_lab.engine import simulate


def bundle(prices, asset_class='crypto'):
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    bars = []
    for index, price in enumerate(prices):
        opened = start + timedelta(days=index)
        bars.append({'open_at': opened.isoformat(),
                     'close_at': (opened + timedelta(hours=20)).isoformat(),
                     'open': price, 'high': price * 1.01, 'low': price * .99,
                     'close': price, 'volume': 10000})
    return {'schema_version': 1, 'currency': 'EUR',
            'assets': [{'id': 'TOY', 'asset_class': asset_class, 'currency': 'EUR',
                        'price_basis': 'raw',
                        'lot_size': .00000001 if asset_class == 'crypto' else 1,
                        'bars': bars}]}


def spec(**changes):
    return {'family': 'trend_breakout', 'fast': 2, 'slow': 3, 'breakout': 2,
            'stop_loss': .10, 'max_hold': 10, 'take_profit': .08, **changes}


class EngineCausalityTests(unittest.TestCase):
    def test_execution_session_volume_cannot_change_opening_fill(self):
        for market in ['crypto', 'stock']:
            with self.subTest(market=market):
                data = bundle([5, 5, 5], market)
                changed = copy.deepcopy(data)
                changed['assets'][0]['bars'][1]['volume'] = 1
                before = simulate(data, {'family': 'buy_hold'}, start_index=1,
                                  fee=0, slippage=0)
                after = simulate(changed, {'family': 'buy_hold'}, start_index=1,
                                 fee=0, slippage=0)
                self.assertEqual(before['trades'], after['trades'])
                self.assertEqual(after['trades'][0]['quantity'], 4)

    def test_previous_session_volume_limits_opening_quantity_once(self):
        data = bundle([5, 5, 5], 'stock')
        data['assets'][0]['bars'][0]['volume'] = 100
        result = simulate(data, {'family': 'buy_hold'}, start_index=1,
                          fee=0, slippage=0)
        self.assertEqual(result['trades'][0]['quantity'], 1)

    def test_first_session_is_liquidity_warmup(self):
        data = bundle([5, 5, 5])
        result = simulate(data, {'family': 'buy_hold'}, fee=0, slippage=0)
        self.assertEqual(result['trades'][0]['entry_session'],
                         data['assets'][0]['bars'][1]['open_at'])
        self.assertEqual(result['curve'][0]['equity'], 100)

    def assert_open_exit_ignores_later_barriers(self, data, strategy, index, reason,
                                              risk_control=False):
        before = simulate(data, strategy, fee=0, slippage=0,
                          risk_control=risk_control)
        for change in ['take_profit', 'stop_loss', 'both']:
            with self.subTest(reason=reason, later_path=change):
                changed = copy.deepcopy(data)
                bar = changed['assets'][0]['bars'][index]
                if change in ['take_profit', 'both']:
                    bar['high'] = 18
                if change in ['stop_loss', 'both']:
                    bar['low'] = 5
                after = simulate(changed, strategy, fee=0, slippage=0,
                                 risk_control=risk_control)
                self.assertEqual(before['trades'][0], after['trades'][0])
                self.assertEqual(after['trades'][0]['reason'], reason)
                self.assertEqual(after['trades'][0]['exit_session'], bar['open_at'])

    def test_time_limit_at_open_precedes_intraday_stop_and_profit(self):
        self.assert_open_exit_ignores_later_barriers(
            bundle([8, 9, 10, 11, 11, 11, 11]), spec(max_hold=2), 5, 'time_limit')

    def test_prior_close_trend_exit_precedes_intraday_barriers(self):
        data = bundle([8, 9, 10, 11, 10, 11, 11])
        data['assets'][0]['bars'][4]['open'] = 11
        data['assets'][0]['bars'][4]['high'] = 11.11
        data['assets'][0]['bars'][4]['low'] = 9.99
        self.assert_open_exit_ignores_later_barriers(data, spec(), 5, 'trend_exit')

    def test_drawdown_exit_at_open_precedes_intraday_barriers(self):
        self.assert_open_exit_ignores_later_barriers(
            bundle([8, 9, 10, 11, 13.75, 10.7, 10.7]),
            spec(take_profit=.50), 5, 'risk_halt', risk_control=True)

    def test_intraday_stop_still_precedes_profit_when_no_open_exit_is_due(self):
        data = bundle([8, 9, 10, 11, 11, 11])
        data['assets'][0]['bars'][4].update(high=13, low=9.5)
        result = simulate(data, spec(), fee=0, slippage=0, risk_control=False)
        self.assertEqual(result['trades'][0]['reason'], 'stop_loss')
        self.assertAlmostEqual(result['trades'][0]['profit'], -2, places=6)


if __name__ == '__main__':
    unittest.main()
