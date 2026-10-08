import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.collect_equity_paper import run
from research_lab.worker import current_equity_bundle


class CollectionIsolationTests(unittest.TestCase):
    def test_source_failure_preserves_previous_bundle_and_disables_equity_consumption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / 'research_state'
            state.mkdir()
            bundle = state / 'equities.bundle.json'
            bundle.write_text('{"old_evidence": true}')
            now = datetime.now(timezone.utc)
            def failure(_):
                raise OSError('private upstream message')
            result = run(root, now, failure)
            self.assertEqual(result['state'], 'unavailable')
            self.assertEqual(bundle.read_text(), '{"old_evidence": true}')
            self.assertNotIn('private upstream', json.dumps(result))
            with self.assertRaisesRegex(ValueError, 'equity_collection_unavailable'):
                current_equity_bundle(state, now)

    def test_success_requires_matching_current_source_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = datetime.now(timezone.utc)
            data = {'observed_at': now.isoformat(), 'assets': [{'bars': [{'close_at': now.isoformat()}]}]}
            run(root, now, lambda _: data)
            state = root / 'research_state'
            with patch('research_lab.worker.validate', side_effect=lambda b, _: b):
                self.assertEqual(current_equity_bundle(state, now), data)
            with self.assertRaisesRegex(ValueError, 'equity_collection_unavailable'):
                current_equity_bundle(state, now + timedelta(seconds=901))
            data['observed_at'] = (now - timedelta(seconds=1)).isoformat()
            (state / 'equities.bundle.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'equity_collection_bundle_mismatch'):
                current_equity_bundle(state, now)

    def test_successful_download_cannot_make_obsolete_market_prices_current(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = datetime.now(timezone.utc)
            data = {'observed_at': now.isoformat(), 'assets': [{'bars': [{
                'close_at': (now - timedelta(days=30)).isoformat()}]}]}
            run(root, now, lambda _: data)
            with patch('research_lab.worker.validate', side_effect=lambda b, _: b):
                with self.assertRaisesRegex(ValueError, 'equity_market_data_stale'):
                    current_equity_bundle(root / 'research_state', now)


if __name__ == '__main__':
    unittest.main()
