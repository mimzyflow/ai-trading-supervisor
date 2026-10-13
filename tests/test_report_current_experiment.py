import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supervisor import report
from tests.test_supervision import FakeAPI

FULL = ("CREATE TABLE trades (id INTEGER, pair TEXT, is_open INTEGER, open_date TEXT, close_date TEXT, "
        "open_rate REAL, close_rate REAL, amount REAL, fee_open REAL, fee_close REAL, "
        "close_profit REAL, close_profit_abs REAL, exit_reason TEXT)")


def make_db(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute(FULL)
        conn.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


ROWS = [
    (1, 'ADA/EUR', 0, '2026-10-09 20:00:00', '2026-10-10 08:00:00', 1.0, 1.1, 10, 0.008, 0.008, 0.084, 0.84, 'roi'),
    (2, 'LINK/EUR', 0, '2026-10-11 09:00:00', '2026-10-13 08:30:15', 1.0, 0.98, 10, 0.008, 0.008, -0.036, -0.36, 'trend_exit'),
    (3, 'ZEC/EUR', 1, '2026-10-13 09:00:00', None, 2.0, None, 5, 0.008, None, None, None, None),
]


class CurrentExperimentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / 'trades-market-room-100eur-20261009.dryrun.sqlite'
        make_db(self.db, ROWS)
        (self.root / 'freqtrade.log').write_text('log')
        for item in [patch.object(report, 'DB', self.db), patch.object(report, 'LOG', self.root / 'freqtrade.log'),
                     patch.object(report, 'REPORTS', self.root), patch.object(report, 'RUNTIME', self.root),
                     patch.dict(os.environ, {'SIMULATION_START_BALANCE_EUR': '100', 'GITHUB_STATUS_TOKEN': '',
                                             'ACCOUNT_POLICY_ID': 'market-room-100eur-20261009',
                                             'ACTIVE_STRATEGY': 'MoussaMarketRoom', 'EXTRA_ACCOUNTS': ''})]:
            item.start()
            self.addCleanup(item.stop)

    def test_trade_stats_profit_factor_dates_and_fees(self):
        with sqlite3.connect(self.db) as conn:
            stats = report.trade_stats(conn)
        self.assertEqual((stats['closed_trades'], stats['wins'], stats['losses']), (2, 1, 1))
        self.assertEqual(stats['realized_profit_eur'], 0.48)
        self.assertEqual(stats['profit_factor'], round(0.84 / 0.36, 4))
        self.assertEqual(stats['first_open_date'], '2026-10-09 20:00:00')
        self.assertEqual(stats['last_close_date'], '2026-10-13 08:30:15')
        expected = 0.008 * 10 + 0.008 * 11 + 0.008 * 10 + 0.008 * 9.8 + 0.008 * 10
        self.assertAlmostEqual(stats['fees_paid_eur'], round(expected, 4))

    def test_missing_columns_give_none_not_zero(self):
        old = self.root / 'old.sqlite'
        with sqlite3.connect(old) as conn:
            conn.execute("CREATE TABLE trades (id INTEGER, pair TEXT, is_open INTEGER, close_profit REAL, close_profit_abs REAL, close_date TEXT, exit_reason TEXT)")
            conn.execute("INSERT INTO trades VALUES (1,'BTC/EUR',0,-0.01,-0.1,'2026-10-03','trend_exit')")
            stats = report.trade_stats(conn)
        self.assertIsNone(stats['first_open_date'])
        self.assertIsNone(stats['fees_paid_eur'])
        self.assertEqual(stats['profit_factor'], 0.0)
        self.assertEqual(stats['losses'], 1)

    def test_collect_exposes_current_experiment_and_keeps_v2(self):
        result = report.collect(FakeAPI())
        current = result['current_experiment']
        self.assertEqual(current['account_id'], 'trades-market-room-100eur-20261009.dryrun')
        self.assertEqual(current['database'], self.db.name)
        self.assertEqual(current['policy_id'], 'market-room-100eur-20261009')
        self.assertEqual(current['strategy'], 'MoussaMarketRoom')
        self.assertEqual(current['closed_trades'], 2)
        self.assertIn('v2', result)
        self.assertEqual(result['accounts'], [])
        self.assertIn('## Expérience courante', report.render(result))

    def test_extra_accounts_read_only_and_validated(self):
        control = self.root / 'trades-control-stops-20261013.dryrun.sqlite'
        make_db(control, ROWS[:1])
        value = json.dumps([
            {'account_id': 'control-stops-20261013', 'db': control.name},
            {'account_id': 'evil', 'db': '../secret.sqlite'},
            {'account_id': 'bad id!', 'db': 'x.sqlite'},
            {'account_id': 'dup', 'db': self.db.name},
            {'account_id': 'missing', 'db': 'absent.sqlite'},
            'garbage',
        ])
        with patch.dict(os.environ, {'EXTRA_ACCOUNTS': value}):
            result = report.collect(FakeAPI())
        accounts = {a['account_id']: a for a in result['accounts']}
        self.assertEqual(set(accounts), {'control-stops-20261013', 'missing'})
        self.assertTrue(accounts['control-stops-20261013']['database_ok'])
        self.assertEqual(accounts['control-stops-20261013']['closed_trades'], 1)
        self.assertFalse(accounts['missing']['database_found'])
        self.assertIn('Compte supplémentaire control-stops-20261013', report.render(result))
        with patch.dict(os.environ, {'EXTRA_ACCOUNTS': '{not json'}):
            self.assertEqual(report.extra_accounts(), [])

    def test_max_drawdown_and_recent_profits(self):
        rows = [
            (1, 'ADA/EUR', 0, '2026-10-09 20:00:00', '2026-10-10 08:00:00', 1, 1, 1, 0, 0, 0.02, 2.0, 'roi'),
            (2, 'XBT/EUR', 0, '2026-10-10 09:00:00', '2026-10-11 08:00:00', 1, 1, 1, 0, 0, -0.03, -3.0, 'stop_loss'),
            (3, 'ETH/EUR', 0, '2026-10-11 09:00:00', '2026-10-12 08:00:00', 1, 1, 1, 0, 0, -0.01, -1.2, 'trend_exit'),
            (4, 'SOL/EUR', 0, '2026-10-12 09:00:00', '2026-10-13 08:00:00', 1, 1, 1, 0, 0, 0.05, 5.0, 'roi'),
            (5, 'ZEC/EUR', 1, '2026-10-13 09:00:00', None, 1, None, 1, 0, None, None, None, None),
        ]
        path = self.root / 'dd.sqlite'
        make_db(path, rows)
        with sqlite3.connect(path) as conn:
            stats = report.trade_stats(conn, 100)
        # Pic 102 puis creux 97.8 : (102 - 97.8) / 102.
        self.assertAlmostEqual(stats['max_drawdown_pct'], round(4.2 / 102 * 100, 4))
        profits = stats['recent_profits']
        self.assertEqual([r['pair'] for r in profits], ['SOL/EUR', 'ETH/EUR', 'XBT/EUR', 'ADA/EUR'])
        self.assertEqual(profits[0], {'pair': 'SOL/EUR', 'close_date': '2026-10-13 08:00:00', 'profit_eur': 5.0,
                                      'profit_pct': 5.0, 'exit_reason': 'roi'})
        self.assertEqual(profits[1]['profit_eur'], -1.2)

    def test_recent_profits_limit_and_no_trades(self):
        rows = [(i, 'ADA/EUR', 0, '2026-10-01 00:00:00', '2026-10-%02d 00:00:00' % i, 1, 1, 1, 0, 0, 0.01, 0.1, 'roi')
                for i in range(1, 16)]
        path = self.root / 'many.sqlite'
        make_db(path, rows)
        with sqlite3.connect(path) as conn:
            stats = report.trade_stats(conn, 100)
        self.assertEqual(len(stats['recent_profits']), report.RECENT_PROFITS_LIMIT)
        self.assertEqual(stats['recent_profits'][0]['close_date'], '2026-10-15 00:00:00')
        self.assertEqual(stats['max_drawdown_pct'], 0.0)
        empty = self.root / 'empty.sqlite'
        make_db(empty, [])
        with sqlite3.connect(empty) as conn:
            stats = report.trade_stats(conn, 100)
        self.assertIsNone(stats['max_drawdown_pct'])
        self.assertEqual(stats['recent_profits'], [])

    def test_collect_current_experiment_has_drawdown_and_recent_profits(self):
        result = report.collect(FakeAPI())
        current = result['current_experiment']
        # 100 -> 100.84 -> 100.48 : (100.84 - 100.48) / 100.84.
        self.assertAlmostEqual(current['max_drawdown_pct'], round(0.36 / 100.84 * 100, 4))
        self.assertEqual([r['profit_eur'] for r in current['recent_profits']], [-0.36, 0.84])
        text = report.render(result)
        self.assertIn('Baisse maximale réalisée %', text)
        self.assertIn('Derniers profits EUR : -0.36, 0.84', text)

    def test_extra_accounts_dir_for_control_volume(self):
        control_dir = self.root / 'control-runtime'
        control_dir.mkdir()
        make_db(control_dir / 'trades-control-stops-20261013.dryrun.sqlite', ROWS[:2])
        value = json.dumps([{'account_id': 'control-stops-20261013', 'db': 'trades-control-stops-20261013.dryrun.sqlite'}])
        with patch.dict(os.environ, {'EXTRA_ACCOUNTS': value, 'EXTRA_ACCOUNTS_DIR': str(control_dir)}):
            accounts = report.extra_accounts()
        self.assertTrue(accounts[0]['database_ok'])
        self.assertEqual(accounts[0]['closed_trades'], 2)
        self.assertIn('max_drawdown_pct', accounts[0])
        self.assertEqual(len(accounts[0]['recent_profits']), 2)

    def test_compose_mounts_control_volume_read_only(self):
        text = (Path(__file__).resolve().parents[1] / 'docker-compose.yml').read_text()
        self.assertIn('freqtrade_control_runtime:/app/control-runtime:ro', text)
        self.assertIn('name: ai-trading-freqtrade-control-runtime', text)
        self.assertIn('EXTRA_ACCOUNTS_DIR: /app/control-runtime', text)
        self.assertNotIn('\n  freqtrade-control:', text)

    def test_policy_id_falls_back_to_none_without_policy(self):
        with patch.dict(os.environ, {'ACCOUNT_POLICY_ID': '', 'SIMULATION_POLICY_FILE': str(self.root / 'none.json')}):
            self.assertIsNone(report.account_policy_id())


if __name__ == '__main__':
    unittest.main()
