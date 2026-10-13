import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from supervisor import control_guards as g
from supervisor.paper_policy import POLICY_ID, CRYPTO_DB

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


class ControlGuardTests(unittest.TestCase):
    def test_defaults_and_bounds(self):
        with patch.dict(os.environ, {}, clear=True):
            s = g.settings()
        self.assertEqual(s['max_consecutive_losses'], 3)
        self.assertEqual(s['portfolio_loss_limit_pct'], 5.0)
        self.assertEqual(s['position_stop'], -0.03)
        for bad in ['0', '-2', 'abc', '999']:
            with patch.dict(os.environ, {'CONTROL_MAX_CONSECUTIVE_LOSSES': bad}):
                self.assertEqual(g.settings()['max_consecutive_losses'], 3)
        with patch.dict(os.environ, {'CONTROL_MAX_CONSECUTIVE_LOSSES': '5', 'CONTROL_POSITION_STOP': '0.1'}):
            self.assertEqual(g.settings()['max_consecutive_losses'], 5)
            self.assertEqual(g.settings()['position_stop'], -0.03)

    def test_consecutive_losses_pause_then_resume(self):
        closed = [(NOW - timedelta(hours=h), p) for h, p in [(10, 0.02), (5, -0.01), (3, -0.02), (1, 0.0)]]
        self.assertEqual(g.consecutive_loss_pause(closed, NOW, 3, 24), (True, 'consecutive_losses_pause'))
        self.assertFalse(g.consecutive_loss_pause(closed, NOW + timedelta(hours=24), 3, 24)[0])
        self.assertFalse(g.consecutive_loss_pause(closed, NOW, 4, 24)[0])
        self.assertFalse(g.consecutive_loss_pause(closed[:2], NOW, 3, 24)[0])
        mixed = closed + [(NOW - timedelta(minutes=5), 0.01)]
        self.assertFalse(g.consecutive_loss_pause(mixed, NOW, 3, 24)[0])

    def test_naive_and_string_dates_are_utc(self):
        closed = [('2026-10-13 09:00:00', -0.01), (datetime(2026, 10, 13, 10), -0.01), ('2026-10-13T11:00:00Z', -0.02)]
        self.assertTrue(g.consecutive_loss_pause(closed, NOW, 3, 24)[0])

    def test_portfolio_halt_threshold(self):
        self.assertFalse(g.portfolio_halt(100, -4.99, 0, 5))
        self.assertTrue(g.portfolio_halt(100, -4.0, -1.0, 5))
        self.assertTrue(g.portfolio_halt(0, 0, 0, 5))

    def test_require_simulation(self):
        g.require_simulation({'dry_run': True, 'trading_mode': 'spot', 'exchange': {'key': '', 'secret': ''}})
        for config in [{'dry_run': False, 'trading_mode': 'spot'}, {'dry_run': 'true', 'trading_mode': 'spot'},
                       {'dry_run': True, 'trading_mode': 'futures'},
                       {'dry_run': True, 'trading_mode': 'spot', 'exchange': {'key': 'x'}}]:
            with self.assertRaises(ValueError):
                g.require_simulation(config)

    def test_control_is_isolated_from_current_policy(self):
        self.assertNotEqual(g.CONTROL_POLICY_ID, POLICY_ID)
        self.assertNotEqual(g.CONTROL_DB, CRYPTO_DB)
        current = json.loads((ROOT / 'user_data/config.dryrun.json').read_text())
        control = json.loads((ROOT / 'user_data/config.control.dryrun.json').read_text())
        self.assertEqual(current['strategy'], 'MoussaMarketRoom')
        self.assertEqual(control['strategy'], 'MoussaControlStops')
        for key in ['fee', 'dry_run_wallet', 'stake_amount', 'timeframe', 'stake_currency', 'trading_mode']:
            self.assertEqual(control[key], current[key], key)
        self.assertEqual(control['exchange']['pair_whitelist'], current['exchange']['pair_whitelist'])
        self.assertIs(control['dry_run'], True)
        self.assertEqual((control['exchange']['key'], control['exchange']['secret']), ('', ''))

    def test_control_compose_is_simulation_only_and_separate(self):
        text = (ROOT / 'docker-compose.control.yml').read_text()
        self.assertIn('FREQTRADE__DRY_RUN: "true"', text)
        self.assertIn('--dry-run', text)
        self.assertIn('127.0.0.1:8081:8080', text)
        self.assertIn(g.CONTROL_DB, text)
        self.assertIn('ai-trading-freqtrade-control-runtime', text)
        self.assertIn('FREQTRADE__EXCHANGE__KEY: ""', text)
        self.assertNotIn('trades-market-room-100eur-20261009', text)
        main = (ROOT / 'docker-compose.yml').read_text()
        self.assertNotIn('freqtrade-control', main)


if __name__ == '__main__':
    unittest.main()
