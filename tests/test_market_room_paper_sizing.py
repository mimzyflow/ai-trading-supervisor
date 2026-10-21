import unittest
from datetime import datetime, timedelta, timezone

from research_lab.equity_paper import advance, new_state
from research_lab.worker import market_room_paper_execution

START = datetime(2025, 12, 1, tzinfo=timezone.utc)
SPEC = {'family': 'trend_breakout', 'fast': 10, 'slow': 50, 'breakout': 10, 'stop_loss': .05, 'max_hold': 30}


def schb_like_bundle(base=29.5):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(70):
        p = base + i * .05
        bars.append({'open_at': (start + timedelta(days=i)).isoformat(),
                     'close_at': (start + timedelta(days=i, hours=6)).isoformat(),
                     'open': p, 'high': p, 'low': p * .99, 'close': p, 'volume': 100000})
    return {'assets': [{'id': 'SCHB', 'currency': 'USD', 'asset_class': 'etf', 'price_basis': 'raw',
                        'lot_size': 1, 'bars': bars}]}


def run(state, **kwargs):
    bundle = schb_like_bundle()
    now = datetime.fromisoformat(bundle['assets'][0]['bars'][-1]['close_at'])
    return advance(bundle, state, SPEC, now=now, max_drawdown=None, loss_stops=False,
                   execution_revision='market_room_no_loss_stops_v1', **kwargs)


class MarketRoomPaperSizingTests(unittest.TestCase):
    def test_legacy_sizing_cannot_buy_schb(self):
        state = run(new_state(START, initial=116.0), allocation=10 * 1.16)  # anciens défauts : min 1 USD
        self.assertEqual(state['positions'], {})

    def test_new_sizing_buys_whole_schb_shares(self):
        state = new_state(START, initial=116.0)
        state = run(state, **market_room_paper_execution(state))
        self.assertEqual(state['positions']['SCHB']['quantity'], 3)
        self.assertGreaterEqual(state['cash'], 0)
        self.assertLessEqual(state['positions']['SCHB']['cost'], 116.0 * 0.9)

    def test_defaults_are_paper_safe_and_configurable(self):
        kw = market_room_paper_execution({'initial_cash': 116.0})
        self.assertEqual(kw, {'allocation': 116.0, 'fee': 0.001, 'min_commission': 0.0, 'slippage': 0.001})
        self.assertEqual(market_room_paper_execution({'initial_cash': 116.0}, min_commission=1.0)['min_commission'], 1.0)
        for bad in ({'fee': 0.5}, {'min_commission': -1}, {'slippage': 1}):
            with self.assertRaises(ValueError):
                market_room_paper_execution({'initial_cash': 116.0}, **bad)
        with self.assertRaises(ValueError):
            market_room_paper_execution({})

    def test_equity_paper_defaults_unchanged_for_existing_callers(self):
        import inspect
        params = inspect.signature(advance).parameters
        self.assertEqual(params['min_commission'].default, 1)
        self.assertEqual(params['allocation'].default, 10)


if __name__ == '__main__':
    unittest.main()
