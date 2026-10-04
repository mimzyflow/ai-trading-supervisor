import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_lab.data import canonical_hash
from research_lab.engine import simulate
from research_lab.equity_experiment import (WARMUP, benchmark_fills, causal_execution_bundle,
                                           prepare_experiment, run_prepared, variant_verdict)

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def historical_bundle(price=10):
    day, end = datetime(2021, 6, 1, tzinfo=timezone.utc), datetime(2026, 10, 2, tzinfo=timezone.utc)
    bars = []
    while day <= end:
        if day.weekday() < 5:
            bars.append({'open_at': (day + timedelta(hours=14)).isoformat(),
                         'close_at': (day + timedelta(hours=21)).isoformat(),
                         'open': price, 'high': price, 'low': price,
                         'close': price, 'volume': 10000})
        day += timedelta(days=1)
    return {'schema_version': 1, 'currency': 'USD', 'calendar_verified': False,
            'corporate_actions_verified': False, 'historical_universe_verified': False,
            'universe_policy': 'fixed_historical',
            'assets': [{'id': 'TOY', 'asset_class': 'stock', 'currency': 'USD',
                        'price_basis': 'raw', 'lot_size': 1, 'bars': bars}]}


class EquityExperimentTests(unittest.TestCase):
    def test_plan_exists_before_simulation_and_every_variant_is_published(self):
        data = historical_bundle()
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'new'
            plan = prepare_experiment(data, output, now=NOW)
            self.assertEqual(data, original)
            self.assertEqual([w['id'] for w in plan['windows']], ['2023', '2024', '2025', '2026YTD'])
            self.assertFalse(plan['quality_via_research'])
            self.assertNotEqual(plan['original_bundle_sha256'], plan['execution_bundle_sha256'])
            calls = []
            def fake(bundle, spec, **kwargs):
                self.assertTrue((output / 'plan.json').exists())
                self.assertTrue((output / 'started.json').exists())
                self.assertEqual(kwargs['start_index'], WARMUP)
                window = plan['windows'][len(calls) // 18]
                passed = bundle['assets'][0]['bars']
                self.assertEqual(passed[WARMUP]['open_at'][:10], window['first_session'])
                self.assertEqual(passed[-1]['open_at'][:10], window['last_session'])
                self.assertEqual(len(passed), WARMUP + window['sessions'])
                calls.append((bundle, spec, kwargs))
                return {'profit': 0, 'return_pct': 0, 'max_drawdown_pct': 0,
                        'closed_trades': 0, 'halted': False, 'curve': [], 'trades': []}
            with patch('research_lab.equity_experiment.simulate', side_effect=fake):
                result = run_prepared(output)
            self.assertEqual(len(calls), 72)
            self.assertEqual(len(result['runs']), 72)
            self.assertEqual(set(result['variant_verdicts']), {f'template_{i}' for i in range(4)})
            self.assertIsNone(result['selection'])
            self.assertFalse(result['real_money_eligible'])
            for _, spec, kwargs in calls:
                self.assertEqual(kwargs['risk_control'], spec['family'] == 'trend_breakout')
                self.assertEqual(kwargs['initial'], 100)
                self.assertEqual(kwargs['allocation'], 20)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            for file in output.iterdir():
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            report = (output / 'report.md').read_text()
            self.assertIn('sans holdout prospectif', report)
            self.assertIn('biais de survivance', report)
            self.assertIn('Aucun paper trading courtier', report)
            with self.assertRaises(FileExistsError):
                run_prepared(output)
            with self.assertRaises(FileExistsError):
                prepare_experiment(data, output, now=NOW)

    def test_changed_bundle_plan_rules_and_code_are_refused_before_engine(self):
        for changed in ('bundle', 'plan', 'code', 'rules'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / 'new'
                prepare_experiment(historical_bundle(), output, now=NOW)
                if changed == 'bundle':
                    path = output / 'bundle.json'; path.write_bytes(path.read_bytes() + b' ')
                elif changed == 'plan':
                    plan = json.loads((output / 'plan.json').read_text()); plan['currency'] = 'EUR'
                    (output / 'plan.json').write_text(json.dumps(plan))
                context = patch('research_lab.equity_experiment.source_hashes', return_value={}) if changed == 'code' else (
                    patch('research_lab.equity_experiment.rules', return_value={}) if changed == 'rules' else patch('research_lab.equity_experiment.math.floor', wraps=__import__('math').floor))
                with context, patch('research_lab.equity_experiment.simulate') as engine:
                    with self.assertRaises(ValueError):
                        run_prepared(output)
                    engine.assert_not_called()
                self.assertFalse((output / 'started.json').exists())

    def test_bad_bundles_and_incomplete_history_are_refused_without_output(self):
        for changed in ('crypto', 'fractional', 'short', 'partial_year', 'partial_ytd', 'late_ytd', 'quality', 'quality_claim', 'nan', 'adjusted'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder:
                data = historical_bundle(); asset = data['assets'][0]
                if changed == 'crypto': asset['asset_class'] = 'crypto'
                if changed == 'fractional': asset.update(lot_size=0.5, fractional_supported=True)
                if changed == 'short': asset['bars'] = asset['bars'][500:]
                if changed == 'partial_year': asset['bars'] = [b for b in asset['bars'] if not b['open_at'].startswith('2024-01')]
                if changed == 'partial_ytd': asset['bars'] = [b for b in asset['bars'] if b['open_at'][:10] < '2026-04-01']
                if changed == 'late_ytd': asset['bars'] = [b for b in asset['bars'] if not ('2026-01-01' <= b['open_at'][:10] < '2026-08-01')]
                if changed == 'quality': data['calendar_verified'] = 'true'
                if changed == 'quality_claim': data['historical_universe_verified'] = True
                if changed == 'nan': asset['bars'][0]['close'] = float('nan')
                if changed == 'adjusted': asset['price_basis'] = 'adjusted'
                output = Path(folder) / 'new'
                with self.assertRaises(ValueError): prepare_experiment(data, output, now=NOW)
                self.assertFalse(output.exists())

    def test_previous_volume_changes_fills_without_future_volume_or_price_leak(self):
        data = historical_bundle(); bars = data['assets'][0]['bars']
        bars[200]['volume'] = 1_000_000
        bars[199]['volume'] = 1
        execution = causal_execution_bundle(data)
        self.assertEqual(execution['assets'][0]['bars'][200]['volume'], 1)
        self.assertEqual(execution['assets'][0]['bars'][201]['volume'], 1_000_000)
        self.assertEqual(execution['assets'][0]['bars'][0]['volume'], 1)
        for original, transformed in zip(bars, execution['assets'][0]['bars']):
            self.assertEqual({k: v for k, v in original.items() if k != 'volume'},
                             {k: v for k, v in transformed.items() if k != 'volume'})
        result = simulate(execution, {'family': 'buy_hold'}, start_index=200,
                          fee=0.001, min_commission=1, slippage=0.001, risk_control=False)
        self.assertEqual(result['closed_trades'], 0)
        future = copy.deepcopy(data); future['assets'][0]['bars'][201]['volume'] = 500
        self.assertEqual(causal_execution_bundle(future)['assets'][0]['bars'][:202],
                         execution['assets'][0]['bars'][:202])

    def test_real_engine_costs_and_integer_lot_benchmarks(self):
        data = historical_bundle(); execution = causal_execution_bundle(data)
        expected = {'base': -2.02, 'stress': -2.05, 'zero_commission_hypothetical': -0.02}
        with tempfile.TemporaryDirectory() as folder:
            plan = prepare_experiment(data, Path(folder) / 'new', now=NOW)
        for scenario, options in plan['rules']['cost_scenarios'].items():
            result = simulate(execution, {'family': 'buy_hold'}, start_index=200,
                              risk_control=False, **options)
            self.assertEqual(result['closed_trades'], 1)
            self.assertEqual(result['trades'][0]['quantity'], 1)
            self.assertAlmostEqual(result['profit'], expected[scenario], places=7)
            self.assertGreaterEqual(result['trades'][0]['entry_session'], execution['assets'][0]['bars'][200]['open_at'])
            description = benchmark_fills(execution, options)
            self.assertEqual(description['initial_fills'][0]['quantity'], 1)
            self.assertAlmostEqual(description['initial_idle_cash'], 100 - 10 * (1 + options['slippage']) - options['min_commission'])
        expensive = causal_execution_bundle(historical_bundle(price=100))
        self.assertEqual(benchmark_fills(expensive, plan['rules']['cost_scenarios']['base'])['initial_notional_exposure_pct'], 0)

    def test_negative_zero_and_sparse_verdicts_never_promote(self):
        def row(profit, trades):
            return {'scenario': 'base', 'metrics': {'profit': profit, 'halted': False, 'closed_trades': trades}}
        self.assertEqual(variant_verdict([row(-1, 10)])['verdict'], 'rejet_experimental')
        self.assertEqual(variant_verdict([row(0, 0)])['reason'], 'au_moins_une_fenetre_sans_transaction')
        self.assertEqual(variant_verdict([row(1, 2)])['reason'], 'transactions_trop_rares')
        self.assertEqual(variant_verdict([row(1, 10)])['verdict'], 'inconclusif')


if __name__ == '__main__':
    unittest.main()
