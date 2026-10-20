"""risk_halt_preserved : le seuil 5 % est une alerte persistante, jamais une liquidation."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_lab.equity_paper import (DEFAULT_HALT_ACTION, advance, load, new_state,
                                       save, summary)

SPEC = {'family': 'trend_breakout', 'fast': 2, 'slow': 3, 'breakout': 2, 'stop_loss': .10, 'max_hold': 30}


def bundle(count=5, price=10):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [{'open_at': (start + timedelta(days=i)).isoformat(),
             'close_at': (start + timedelta(days=i, hours=6)).isoformat(),
             'open': price, 'high': price, 'low': price, 'close': price, 'volume': 100000}
            for i in range(count)]
    return {'assets': [{'id': 'TEST', 'bars': bars}]}


def seeded(b, last_index, quantity=10):
    bars = b['assets'][0]['bars']
    state = new_state(last_session=bars[last_index]['close_at'])
    state['cash'] = 100 - quantity * 10
    state['positions']['TEST'] = {'quantity': quantity, 'cost': quantity * 10, 'entry_price': 10,
                                  'entry_session': bars[last_index]['close_at'], 'entry_index': last_index,
                                  'highest_price': 10}
    return state


def run(b, s, **kwargs):
    now = datetime.fromisoformat(b['assets'][0]['bars'][-1]['close_at'])
    return advance(b, s, SPEC, now=now, fee=0, min_commission=0, slippage=0, **kwargs)


class RiskHaltPreservedTests(unittest.TestCase):
    def breach(self):
        b = bundle()
        b['assets'][0]['bars'][-1].update(open=9.3, high=9.3, low=9.3, close=9.3)
        s = seeded(b, 3)
        run(b, s)
        return b, s

    def test_default_is_alert_only(self):
        self.assertEqual(DEFAULT_HALT_ACTION, 'alert_only')

    def test_breach_records_preserved_halt_without_liquidation(self):
        _, s = self.breach()
        self.assertTrue(s['halted'])
        self.assertTrue(s['risk_halt_preserved'])
        self.assertEqual(s['halt_action'], 'alert_only')
        self.assertIn('TEST', s['positions'])
        self.assertEqual(s['positions']['TEST']['quantity'], 10)
        self.assertFalse([t for t in s['trades'] if str(t.get('reason', '')).startswith('risk_halt_')])
        self.assertEqual(len(s['risk_alerts']), 1)
        self.assertEqual(s['risk_alerts'][0]['action'], 'notify_only')
        self.assertAlmostEqual(s['equity'], 93)
        info = summary(s)
        self.assertTrue(info['risk_halt_preserved'])
        self.assertEqual(info['state'], 'paper_halted')

    def test_halt_survives_restart_and_recovery_without_selling_or_duplicate_alert(self):
        _, s = self.breach()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'state.json'
            save(path, s)
            restored = load(path)
        nxt = bundle(count=7)
        for bar in nxt['assets'][0]['bars'][4:]:
            bar.update(open=10.5, high=10.5, low=10.5, close=10.5)
        restored['last_session'] = nxt['assets'][0]['bars'][4]['close_at']
        run(nxt, restored)
        self.assertTrue(restored['halted'])
        self.assertTrue(restored['risk_halt_preserved'])
        self.assertIn('TEST', restored['positions'])
        self.assertEqual(len(restored['risk_alerts']), 1)
        self.assertFalse([t for t in restored['trades'] if str(t.get('reason', '')).startswith('risk_halt_')])

    def test_historical_breach_is_preserved_not_liquidated(self):
        b = bundle()
        s = seeded(b, 3, quantity=1)
        s['max_drawdown_pct'] = 6
        run(b, s)
        self.assertTrue(s['halted'])
        self.assertTrue(s['risk_halt_preserved'])
        self.assertIn('TEST', s['positions'])
        self.assertEqual(s['max_drawdown_pct'], 6)

    def test_legacy_liquidation_only_on_explicit_request(self):
        b = bundle()
        b['assets'][0]['bars'][-1].update(open=9.3, high=9.3, low=9.3, close=9.3)
        s = seeded(b, 3)
        run(b, s, halt_action='liquidate')
        self.assertEqual(s['positions'], {})
        self.assertEqual(s['trades'][0]['reason'], 'risk_halt_open')

    def test_unknown_halt_action_is_refused(self):
        b = bundle()
        with self.assertRaises(ValueError):
            run(b, seeded(b, 3), halt_action='stop_everything')


if __name__ == '__main__':
    unittest.main()
