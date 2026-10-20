import ast
import json
import unittest
from pathlib import Path

from scripts.run_bias_checks import ALLOWED, SAFE_ENV, commands

ROOT = Path(__file__).resolve().parents[1]
STRATEGY = ROOT / 'user_data/strategies/MoussaDailyTrend.py'
CONFIG = ROOT / 'user_data/config.daily-trend.research.json'


def class_attrs():
    tree = ast.parse(STRATEGY.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MoussaDailyTrend')
    out = {}
    for node in cls.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


class DailyTrendStrategyTests(unittest.TestCase):
    def test_daily_low_turnover_without_forced_stop(self):
        attrs = class_attrs()
        self.assertEqual(attrs['timeframe'], '1d')
        self.assertFalse(attrs['can_short'])
        self.assertEqual(attrs['stoploss'], -1.0)
        self.assertFalse(attrs['trailing_stop'])
        self.assertGreaterEqual(attrs['startup_candle_count'], attrs['sma_period'])
        self.assertGreater(attrs['band'], 0)

    def test_simulation_guard_and_stake_cap_present(self):
        source = STRATEGY.read_text()
        self.assertIn('daily_trend_strategy_is_simulation_only', source)
        self.assertIn('min(max_stake, 20.0', source)

    def test_existing_strategies_untouched_by_name(self):
        names = sorted(p.name for p in (ROOT / 'user_data/strategies').glob('Moussa*.py'))
        self.assertIn('MoussaMarketRoom.py', names)
        self.assertIn('MoussaDailyTrend.py', names)

    def test_research_config_is_dry_run_without_keys(self):
        config = json.loads(CONFIG.read_text())
        self.assertIs(config['dry_run'], True)
        self.assertEqual(config['trading_mode'], 'spot')
        self.assertEqual(config['exchange']['key'], '')
        self.assertEqual(config['exchange']['secret'], '')
        self.assertLessEqual(config['stake_amount'], 20)
        self.assertLessEqual(config['dry_run_wallet'], 100)
        self.assertEqual(config['timeframe'], '1d')
        self.assertEqual(config['strategy'], 'MoussaDailyTrend')


class BiasCheckCommandTests(unittest.TestCase):
    def test_local_commands(self):
        look, rec = commands(ROOT, '/data', '/out', 'MoussaDailyTrend', '20250301-20261019')
        self.assertEqual(look[:2], ['freqtrade', 'lookahead-analysis'])
        self.assertEqual(rec[:2], ['freqtrade', 'recursive-analysis'])
        self.assertIn('--userdir', look)
        self.assertIn('1d', look)
        self.assertNotIn('trade', [part for part in look if part in ('trade', 'webserver')])

    def test_docker_commands_are_offline_and_keyless(self):
        look, rec = commands(ROOT, '/data', '/out', 'MoussaV3SlowBreakout', '20260101-20260630', runner='docker')
        for cmd in (look, rec):
            self.assertEqual(cmd[:5], ['docker', 'run', '--rm', '--network', 'none'])
            self.assertIn('FREQTRADE__DRY_RUN=true', cmd)
            self.assertIn('FREQTRADE__EXCHANGE__KEY=', cmd)
            self.assertIn('FREQTRADE__EXCHANGE__SECRET=', cmd)
        self.assertEqual(SAFE_ENV['FREQTRADE__DRY_RUN'], 'true')

    def test_refusals(self):
        with self.assertRaises(ValueError):
            commands(ROOT, '/d', '/o', 'SomeRandomStrategy', '20250301-20261019')
        with self.assertRaises(ValueError):
            commands(ROOT, '/d', '/o', 'MoussaDailyTrend', '2025;rm -rf /')
        with self.assertRaises(ValueError):
            commands(ROOT, '/d', '/o', 'MoussaDailyTrend', '20250301-20261019', pairs=['BTC/USDT'])
        with self.assertRaises(ValueError):
            commands(ROOT, '/d', '/o', 'MoussaDailyTrend', '20250301-20261019', runner='ssh')

    def test_allowed_strategies_exist(self):
        for name in ALLOWED:
            self.assertTrue((ROOT / 'user_data/strategies' / (name + '.py')).exists(), name)


if __name__ == '__main__':
    unittest.main()
