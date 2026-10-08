import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from research_lab.data import validate
from research_lab.worker import once, replace_v3_marker, v3_data_signature


NOW = datetime(2026, 10, 8, 15, 30, tzinfo=timezone.utc)
CODE_HASH = 'a' * 64


def bundle():
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    bars = []
    for day in range(3):
        opened = start + timedelta(days=day)
        bars.append({'open_at': opened.isoformat(),
                     'close_at': (opened + timedelta(hours=20)).isoformat(),
                     'open': 10, 'high': 11, 'low': 9, 'close': 10, 'volume': 10000})
    return validate({'schema_version': 1, 'currency': 'EUR',
                     'universe_discovery': {'observed_at': NOW.isoformat()},
                     'assets': [{'id': name, 'currency': 'EUR', 'asset_class': 'crypto',
                                 'lot_size': 0.00000001, 'bars': copy.deepcopy(bars)}
                                for name in ['XBT', 'ETH']]}, NOW)


class V3ArchiveTests(unittest.TestCase):
    def test_recalculation_preserves_previous_result_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'last_v3_challengers.json'
            old = {'day': '2026-10-08', 'result': {'state': 'all_rejected', 'return_pct': -4.6}}
            new = {'day': '2026-10-08', 'implementation_sha256': 'a' * 64,
                   'result': {'state': 'all_rejected', 'return_pct': -5.2}}
            replace_v3_marker(path, old, new)
            archived = list((path.parent / 'archive').iterdir())
            self.assertEqual(len(archived), 1)
            self.assertEqual(json.loads(archived[0].read_text()), old)
            self.assertEqual(json.loads(path.read_text()), new)
            replace_v3_marker(path, old, new)
            self.assertEqual(len(list((path.parent / 'archive').iterdir())), 1)


class V3CacheTests(unittest.TestCase):
    def seed(self, root, data, legacy=False):
        state = root / 'research_state'
        state.mkdir()
        reports = root / 'user_data/reports'
        reports.mkdir(parents=True)
        (reports / 'latest.json').write_text(json.dumps({
            'schema_version': 2, 'observed_at': NOW.isoformat(), 'mode': 'DRY-RUN',
            'api_ok': True, 'database_ok': True, 'configuration_safe': True,
            'equity_eur': 100, 'starting_balance_eur': 100, 'equity_peak_eur': 100}))
        (state / 'last_daily.json').write_text(json.dumps({
            'day': NOW.date().isoformat(), 'result': {'state': 'no_candidate_passed_development'}}))
        (state / 'crypto_daily.json').write_text(json.dumps(data))
        marker = {'day': NOW.date().isoformat(), 'implementation_sha256': CODE_HASH,
                  'result': {'state': 'all_rejected', 'return_pct': -4.6}}
        if not legacy:
            marker.update(v3_data_signature(data))
            marker['result'].update(v3_data_signature(data))
        (state / 'last_v3_challengers.json').write_text(json.dumps(marker))
        return marker

    def run_worker(self, root, evaluator):
        collector = Mock(side_effect=AssertionError('unchanged daily research must not collect again'))
        with patch('sys.stdout', new=io.StringIO()), \
                patch('research_lab.worker.v3_implementation_hash', return_value=CODE_HASH), \
                patch('research_lab.worker.evaluate_v3_challengers', evaluator):
            result = once(root, stop=False, now=NOW, collector=collector)
        collector.assert_not_called()
        self.assertEqual(result['risk']['state'], 'research_only')
        self.assertTrue(result['risk']['observation_verified'])
        return result

    def assert_archived(self, root, previous):
        archives = list((root / 'research_state/archive').glob('v3-*.json'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(json.loads(archives[0].read_text()), previous)

    def test_same_day_and_code_recalculate_changed_market_data_universe_or_asset_order(self):
        for change in ['volume', 'universe', 'asset_order']:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                data = bundle()
                previous = self.seed(root, data)
                if change == 'volume':
                    data['assets'][0]['bars'][0]['volume'] += 1
                elif change == 'universe':
                    data['assets'][1]['id'] = 'SOL'
                else:
                    data['assets'].reverse()
                (root / 'research_state/crypto_daily.json').write_text(json.dumps(data))
                evaluator = Mock(return_value={'state': 'all_rejected', 'return_pct': -5.2})
                status = self.run_worker(root, evaluator)
                evaluator.assert_called_once_with(data, NOW)
                marker = json.loads((root / 'research_state/last_v3_challengers.json').read_text())
                signature = v3_data_signature(data)
                self.assertNotEqual(marker['data_sha256'], previous['data_sha256'])
                self.assertEqual(marker['scope'] != previous['scope'], change == 'universe')
                self.assertEqual({key: marker[key] for key in signature}, signature)
                self.assertEqual(status['v3_challengers']['return_pct'], -5.2)
                self.assertEqual({key: status['v3_challengers'][key] for key in signature}, signature)
                self.assert_archived(root, previous)

    def test_identical_data_reuses_cache_despite_key_order_and_discovery_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = bundle()
            previous = self.seed(root, data)
            marker_file = root / 'research_state/last_v3_challengers.json'
            original_bytes = marker_file.read_bytes()
            data = dict(reversed(list(data.items())))
            data['universe_discovery'] = {'observed_at': (NOW + timedelta(minutes=5)).isoformat(),
                                        'daily_turnover': 12345}
            data['assets'] = [dict(reversed(list(asset.items()))) for asset in data['assets']]
            (root / 'research_state/crypto_daily.json').write_text(json.dumps(data))
            evaluator = Mock(side_effect=AssertionError('identical data must reuse cache'))
            status = self.run_worker(root, evaluator)
            evaluator.assert_not_called()
            self.assertEqual(marker_file.read_bytes(), original_bytes)
            self.assertEqual(status['v3_challengers'], previous['result'])
            self.assertFalse((root / 'research_state/archive').exists())

    def test_changed_data_archived_before_failed_evaluation_cannot_publish_old_performance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = bundle()
            previous = self.seed(root, data)
            marker_file = root / 'research_state/last_v3_challengers.json'
            original_bytes = marker_file.read_bytes()
            data['assets'][0]['bars'][0]['volume'] += 1
            (root / 'research_state/crypto_daily.json').write_text(json.dumps(data))

            def fail_after_archive(*_):
                self.assert_archived(root, previous)
                raise OSError('private source detail')

            evaluator = Mock(side_effect=fail_after_archive)
            status = self.run_worker(root, evaluator)
            evaluator.assert_called_once()
            self.assertEqual(marker_file.read_bytes(), original_bytes)
            self.assertEqual(status['v3_challengers'], {'state': 'data_changed_recalculation_required'})
            self.assertIn('v3_challengers_OSError', status['errors'])
            self.assertNotIn('private source detail', json.dumps(status))
            published = json.loads((root / 'user_data/reports/autonomy.json').read_text())
            self.assertEqual(published['v3_challengers'], status['v3_challengers'])

    def test_legacy_marker_without_data_proof_is_archived_and_recalculated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = bundle()
            previous = self.seed(root, data, legacy=True)
            evaluator = Mock(return_value={'state': 'all_rejected', 'return_pct': -5.2})
            self.run_worker(root, evaluator)
            evaluator.assert_called_once()
            marker = json.loads((root / 'research_state/last_v3_challengers.json').read_text())
            self.assertEqual(marker['data_sha256'], v3_data_signature(data)['data_sha256'])
            self.assert_archived(root, previous)

    def test_missing_data_cannot_publish_previously_cached_performance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.seed(root, bundle())
            (root / 'research_state/crypto_daily.json').unlink()
            evaluator = Mock(side_effect=AssertionError('missing data cannot be evaluated'))
            status = self.run_worker(root, evaluator)
            evaluator.assert_not_called()
            self.assertEqual(status['v3_challengers'], {'state': 'data_unavailable'})
            self.assertIn('v3_challengers_FileNotFoundError', status['errors'])


if __name__ == '__main__':
    unittest.main()
