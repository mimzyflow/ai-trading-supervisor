import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import install_release


class DeploymentSimulationGuardTests(unittest.TestCase):
    compose = ['docker', 'compose', '-f', 'candidate.yml']

    def resolved(self, environment):
        return SimpleNamespace(stdout=json.dumps({'services': {'freqtrade': {'environment': environment}}}))

    def test_simulation_validation_precedes_activation_and_captures_private_config(self):
        environment = {'FREQTRADE__DRY_RUN': 'true', 'FREQTRADE__EXCHANGE__KEY': '',
                       'FREQTRADE__EXCHANGE__SECRET': '', 'FREQTRADE__API_SERVER__PASSWORD': 'private-sentinel'}
        output = io.StringIO()
        with patch.object(install_release, 'run', return_value=self.resolved(environment)) as runner:
            with redirect_stdout(output), redirect_stderr(output):
                install_release.activate_simulation(self.compose, ['-d'])
        self.assertEqual(runner.call_args_list[0].args[0], self.compose + ['config', '--format', 'json'])
        self.assertEqual(runner.call_args_list[0].kwargs, {'capture_output': True, 'text': True})
        self.assertEqual(runner.call_args_list[1].args[0], self.compose + ['up', '-d'])
        self.assertEqual(output.getvalue(), '')

    def test_live_unknown_or_missing_dry_run_never_activates(self):
        for dry_run in [False, 'false', 'True', 1, None, 'private-sentinel']:
            with self.subTest(dry_run=dry_run):
                with patch.object(install_release, 'run', return_value=self.resolved({'FREQTRADE__DRY_RUN': dry_run})) as runner:
                    with self.assertRaisesRegex(ValueError, '^resolved_compose_requires_dry_run$'):
                        install_release.activate_simulation(self.compose, ['-d'])
                self.assertEqual(runner.call_count, 1)

    def test_exchange_credentials_including_non_string_values_never_activate(self):
        for name in ['FREQTRADE__EXCHANGE__KEY', 'FREQTRADE__EXCHANGE__SECRET']:
            for value in ['private-sentinel', False, 0, {'token': 'private-sentinel'}]:
                with self.subTest(name=name, value=value):
                    environment = {'FREQTRADE__DRY_RUN': 'true', name: value}
                    with patch.object(install_release, 'run', return_value=self.resolved(environment)) as runner:
                        with self.assertRaisesRegex(ValueError, '^resolved_compose_exchange_credentials_present$'):
                            install_release.activate_simulation(self.compose, ['-d'])
                    self.assertEqual(runner.call_count, 1)

    def test_malformed_configuration_and_failed_resolution_do_not_leak_output(self):
        failures = [SimpleNamespace(stdout='private-sentinel'), self.resolved([]),
                    subprocess.CalledProcessError(1, self.compose, output='private-sentinel', stderr='private-sentinel')]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
                with patch.object(install_release, 'run', **kwargs) as runner:
                    with self.assertRaises(ValueError) as error:
                        install_release.activate_simulation(self.compose, ['-d'])
                self.assertNotIn('private-sentinel', str(error.exception))
                self.assertEqual(runner.call_count, 1)

    def test_candidate_refusal_preserves_active_release_and_never_enters_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            root = temp / 'active'
            root.mkdir()
            (root / 'old.py').write_text('active release\n')
            (root / 'build-info.json').write_text('{"commit":"previous"}\n')
            archive = temp / 'candidate.tar'
            with tarfile.open(archive, 'w') as tar:
                for name, payload in [('docker-compose.yml', b'services: {}\n'), ('old.py', b'candidate release\n')]:
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    tar.addfile(info, io.BytesIO(payload))
            paths = {'/home/ubuntu/ai-trading-supervisor': root,
                     '/home/ubuntu/trading-releases': temp / 'releases', '/etc/systemd/system': temp / 'units'}
            def path_factory(value):
                return paths.get(str(value), Path(value))
            def execute(argv, **kwargs):
                if 'config' in argv:
                    return self.resolved({'FREQTRADE__DRY_RUN': 'false'})
                return SimpleNamespace(returncode=0, stdout='')
            # The system Python predates extraction filters. This archive is
            # constructed above; production still uses its explicit data filter.
            extractall = tarfile.TarFile.extractall
            def extract_test_archive(tar, path, **kwargs):
                return extractall(tar, path)
            params = {'archive': str(archive), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'commit': 'b' * 40}
            with patch.object(install_release, 'Path', side_effect=path_factory):
                with patch.object(install_release, 'run', side_effect=execute) as runner:
                    with patch.object(install_release.subprocess, 'run') as direct:
                        with patch.object(install_release, 'install_research_units') as units:
                            with patch.object(tarfile.TarFile, 'extractall', extract_test_archive):
                                with self.assertRaisesRegex(ValueError, '^resolved_compose_requires_dry_run$'):
                                    install_release.install(params)
            self.assertEqual((root / 'old.py').read_text(), 'active release\n')
            self.assertEqual((root / 'build-info.json').read_text(), '{"commit":"previous"}\n')
            self.assertFalse(any('up' in call.args[0] for call in runner.call_args_list))
            direct.assert_not_called()
            units.assert_not_called()
            self.assertTrue(archive.exists())


if __name__ == '__main__':
    unittest.main()
