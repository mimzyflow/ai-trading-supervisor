import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import check_simulation, install_release

ROOT = Path(__file__).resolve().parents[1]


def resolved(environment, command='trade --dry-run --strategy MoussaControlStops'):
    return SimpleNamespace(stdout=json.dumps({'services': {'freqtrade-control': {
        'environment': environment, 'command': command}}}))


SAFE = {'FREQTRADE__DRY_RUN': 'true', 'FREQTRADE__EXCHANGE__KEY': '', 'FREQTRADE__EXCHANGE__SECRET': ''}


class CheckSimulationControlTests(unittest.TestCase):
    def test_repository_configs_pass(self):
        reference = json.loads((ROOT / 'user_data/config.dryrun.json').read_text())
        control = json.loads((ROOT / 'user_data/config.control.dryrun.json').read_text())
        self.assertTrue(check_simulation.validate_control(control, reference))
        self.assertTrue(check_simulation.validate_control_compose((ROOT / 'docker-compose.control.yml').read_text()))
        check_simulation.main()

    def test_control_violations_rejected(self):
        reference = json.loads((ROOT / 'user_data/config.dryrun.json').read_text())
        base = json.loads((ROOT / 'user_data/config.control.dryrun.json').read_text())
        for mutate, error in [(lambda c: c.update(dry_run=False), 'simulation_spot_required'),
                              (lambda c: c['exchange'].update(key='x'), 'exchange_credentials_not_needed_for_simulation'),
                              (lambda c: c.update(strategy='MoussaMarketRoom'), 'control_strategy_mismatch'),
                              (lambda c: c.update(fee=0.001), 'control_differs_from_experiment_fee')]:
            config = json.loads(json.dumps(base))
            mutate(config)
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, '^' + error + '$'):
                check_simulation.validate_control(config, reference)

    def test_control_compose_text_rejected(self):
        text = (ROOT / 'docker-compose.control.yml').read_text()
        for bad in [text.replace('--dry-run', ''), text.replace('FREQTRADE__DRY_RUN: "true"', 'FREQTRADE__DRY_RUN: "false"'),
                    text + '\n# trades-market-room-100eur-20261009\n']:
            with self.assertRaises(ValueError):
                check_simulation.validate_control_compose(bad)


class InstallReleaseControlTests(unittest.TestCase):
    compose = ['docker', 'compose', '-p', 'ai-trading-control', '-f', 'control.yml']

    def test_control_preflight_accepts_simulation(self):
        with patch.object(install_release, 'run', return_value=resolved(SAFE)) as runner:
            install_release.preflight_control_compose(self.compose)
        self.assertTrue(all('up' not in c.args[0] for c in runner.call_args_list))

    def test_control_preflight_refuses_live_keys_or_missing_flag(self):
        cases = [(resolved({**SAFE, 'FREQTRADE__DRY_RUN': 'false'}), 'resolved_compose_requires_dry_run'),
                 (resolved({**SAFE, 'FREQTRADE__EXCHANGE__KEY': 'k'}), 'resolved_compose_exchange_credentials_present'),
                 (resolved(SAFE, 'trade --strategy MoussaControlStops'), 'resolved_control_compose_requires_dry_run_flag'),
                 (SimpleNamespace(stdout=json.dumps({'services': {'freqtrade': {'environment': SAFE}}})), 'resolved_compose_unavailable')]
        for value, error in cases:
            with self.subTest(error=error):
                with patch.object(install_release, 'run', return_value=value):
                    with self.assertRaisesRegex(ValueError, '^' + error + '$'):
                        install_release.preflight_control_compose(self.compose)

    def test_main_preflight_unchanged_for_freqtrade_service(self):
        value = SimpleNamespace(stdout=json.dumps({'services': {'freqtrade': {'environment': SAFE}}}))
        with patch.object(install_release, 'run', return_value=value):
            install_release.preflight_simulation_compose(['docker', 'compose'])

    def test_activate_control_starts_only_control_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(install_release.activate_control(root), 'absent')
            (root / 'docker-compose.control.yml').write_text('services: {}\n')
            calls = []

            def execute(argv, **kwargs):
                calls.append(argv)
                if 'config' in argv:
                    return resolved(SAFE)
                if argv[:2] == ['docker', 'inspect']:
                    return SimpleNamespace(stdout=json.dumps([{'Config': {'Env': ['FREQTRADE__DRY_RUN=true', 'FREQTRADE__EXCHANGE__KEY=']}}]))
                return SimpleNamespace(stdout='')
            with patch.object(install_release, 'run', side_effect=execute):
                self.assertEqual(install_release.activate_control(root), 'started')
            ups = [c for c in calls if 'up' in c]
            self.assertEqual(len(ups), 1)
            self.assertIn('ai-trading-control', ups[0])
            self.assertEqual(ups[0][-1], 'freqtrade-control')

    def test_activate_control_refusal_never_runs_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docker-compose.control.yml').write_text('services: {}\n')
            with patch.object(install_release, 'run', return_value=resolved({**SAFE, 'FREQTRADE__DRY_RUN': 'false'})) as runner:
                self.assertEqual(install_release.activate_control(root), 'failed:resolved_compose_requires_dry_run')
            self.assertFalse(any('up' in c.args[0] for c in runner.call_args_list))


if __name__ == '__main__':
    unittest.main()
