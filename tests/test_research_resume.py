import copy
import fcntl
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research_lab.data import stamp
from research_lab.governor import Registry
from research_lab.research import apply_resume, cycle, prepare_resume
from research_lab.resume import main, run
from research_lab.worker import daily_cycle_required
from test_research_lab import bundle


GOOD = {'return_pct': 3, 'profit': 3, 'profit_factor': 1.5, 'max_drawdown_pct': 1,
        'closed_trades': 20, 'halted': False, 'trades': [], 'curve': []}


def eligible(data, spec, **kwargs):
    return {**GOOD, 'return_pct': 0 if spec['family'] == 'buy_hold' else 3}


class ResearchResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'research_state'
        self.state.mkdir()
        (self.state / 'worker.lock').touch()
        self.registry = Registry(self.state / 'registry.sqlite')
        self.addCleanup(self.registry.close)
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=605)
        self.original = bundle(count=600, start=start)
        self.original_freeze = stamp(self.original['assets'][0]['bars'][-1]['close_at']) + timedelta(hours=1)
        self.current = bundle(count=604, start=start)
        self.resume_at = stamp(self.current['assets'][0]['bars'][-1]['close_at']) + timedelta(hours=1)
        with patch('research_lab.research.implementation_hash', return_value='a' * 64), patch('research_lab.research.simulate', return_value=GOOD):
            result = cycle(self.original, self.registry, self.original_freeze)
        self.parent = result['epoch']
        self.assertEqual(result['state'], 'no_candidate_passed_development')
        (self.state / 'crypto_daily.json').write_text(json.dumps(self.current))
        (self.root / 'user_data').mkdir()
        source = Path(__file__).resolve().parents[1] / 'user_data/config.dryrun.json'
        (self.root / 'user_data/config.dryrun.json').write_bytes(source.read_bytes())

    def parent_row(self):
        return dict(self.registry.db.execute('SELECT * FROM epochs WHERE id=?', (self.parent,)).fetchone())

    def preview(self, data=None):
        return prepare_resume(data or self.current, self.registry.db, self.parent, self.resume_at)

    def legacy_parent(self):
        row = self.parent_row()
        plan = json.loads(row['plan'])
        del plan['frozen_history_count']; del plan['frozen_history_sha256']
        self.registry.db.execute('UPDATE epochs SET plan=? WHERE id=?', (json.dumps(plan), self.parent))

    def test_preview_is_read_only_and_validates_legacy_complete_bundle(self):
        self.legacy_parent()
        before = (self.state / 'registry.sqlite').read_bytes()
        with patch('research_lab.research.simulate') as simulate:
            preview = run(self.root, self.parent)
        self.assertEqual(preview['history_proof'], 'legacy_complete_bundle_sha256')
        self.assertEqual(preview['state'], 'ready_to_refreeze_development')
        self.assertFalse(preview['broker_orders_activated'])
        self.assertEqual((self.state / 'registry.sqlite').read_bytes(), before)
        simulate.assert_not_called()

    def test_apply_appends_revision_preserves_parent_bytes_and_all_consumed_windows(self):
        self.legacy_parent()
        original = self.parent_row()
        scope = json.loads(original['plan'])['scope']
        start = (self.original_freeze - timedelta(days=20)).isoformat()
        end = (self.original_freeze - timedelta(days=10)).isoformat()
        self.registry.consume_holdout(scope, start, end, 'previous-experiment')
        self.registry.consume_holdout('another-scope', start, end, 'other-experiment')
        windows = [tuple(row) for row in self.registry.db.execute('SELECT * FROM consumed ORDER BY epoch')]
        token = self.preview()['expected_parent_sha256']
        with patch('research_lab.research.simulate', side_effect=eligible):
            result = apply_resume(self.current, self.registry, self.parent, token, self.resume_at)
        parent = self.parent_row()
        self.assertEqual(parent['plan'], original['plan'])
        self.assertEqual(parent['result'], original['result'])
        self.assertEqual(parent['status'], 'superseded')
        self.assertEqual([tuple(row) for row in self.registry.db.execute('SELECT * FROM consumed ORDER BY epoch')], windows)
        self.assertEqual(result['preserved_consumed_windows'], 2)
        self.assertFalse(result['real_money_eligible'])
        revision = json.loads(self.registry.db.execute('SELECT plan FROM epochs WHERE id=?', (result['epoch'],)).fetchone()[0])
        self.assertEqual(revision['resumes_epoch'], self.parent)
        self.assertEqual(revision['frozen_at'], self.resume_at.isoformat())
        self.assertEqual(revision['frozen_history_count'], 604)
        self.assertEqual(self.registry.db.execute("SELECT COUNT(*) FROM events WHERE type='research_plan_explicitly_refrozen'").fetchone()[0], 1)

    def test_old_future_bars_never_count_toward_new_holdout_and_revision_survives_months(self):
        token = self.preview()['expected_parent_sha256']
        with patch('research_lab.research.simulate', side_effect=eligible):
            result = apply_resume(self.current, self.registry, self.parent, token, self.resume_at)
        with patch('research_lab.research.simulate') as simulate:
            observed = cycle(self.current, self.registry, self.resume_at + timedelta(hours=1))
            later = cycle(self.current, self.registry, self.resume_at + timedelta(days=40))
        self.assertEqual(observed['state'], 'awaiting_future_holdout')
        self.assertEqual(observed['received'], 0)
        self.assertEqual(later['received'], 0)
        self.assertEqual(later['epoch'], result['epoch'])
        simulate.assert_not_called()
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0], 0)

    def test_unselected_revision_is_used_in_current_month_without_waiting_for_november(self):
        # Put both freezes in the same month for the cache/current-plan routing.
        instant = self.original_freeze + timedelta(hours=1)
        token = prepare_resume(self.original, self.registry.db, self.parent, instant)['expected_parent_sha256']
        with patch('research_lab.research.simulate', return_value=GOOD):
            result = apply_resume(self.original, self.registry, self.parent, token, instant)
            routed = cycle(self.original, self.registry, instant + timedelta(minutes=1))
        self.assertEqual(routed['state'], 'no_candidate_passed_development')
        self.assertEqual(routed['epoch'], result['epoch'])
        marker = {'day': instant.date().isoformat(), 'result': {'state': 'no_candidate_passed_development', 'epoch': self.parent}}
        self.assertTrue(daily_cycle_required(marker, self.registry, instant))
        marker['result']['epoch'] = result['epoch']
        self.assertFalse(daily_cycle_required(marker, self.registry, instant))

    def test_holdout_reserves_only_126_sessions_opened_after_the_new_freeze(self):
        token = self.preview()['expected_parent_sha256']
        start = stamp(self.original['assets'][0]['bars'][0]['open_at'])
        with patch('research_lab.research.simulate', side_effect=eligible):
            result = apply_resume(self.current, self.registry, self.parent, token, self.resume_at)
            incomplete = bundle(count=729, start=start)
            waiting = cycle(incomplete, self.registry, stamp(incomplete['assets'][0]['bars'][-1]['close_at']) + timedelta(hours=1))
            complete = bundle(count=730, start=start)
            evaluated = cycle(complete, self.registry, stamp(complete['assets'][0]['bars'][-1]['close_at']) + timedelta(hours=1))
        self.assertEqual(waiting['received'], 125)
        self.assertEqual(waiting['epoch'], result['epoch'])
        self.assertEqual(evaluated['state'], 'paper_candidate_passed')
        window = self.registry.db.execute('SELECT * FROM consumed').fetchone()
        self.assertGreater(stamp(window['start']), self.resume_at)
        self.assertEqual(window['start'], complete['assets'][0]['bars'][604]['open_at'])
        self.assertEqual(window['end'], complete['assets'][0]['bars'][729]['close_at'])

    def test_modified_or_missing_legacy_history_and_instrument_metadata_refuse(self):
        self.legacy_parent()
        for change in ['price', 'volume', 'lot', 'missing', 'metadata']:
            with self.subTest(change=change):
                data = copy.deepcopy(self.current)
                asset = data['assets'][0]
                if change == 'price': asset['bars'][20].update(open=100, high=101, low=99, close=100)
                if change == 'volume': asset['bars'][20]['volume'] = 9000
                if change == 'lot': asset['lot_size'] = 0.001
                if change == 'missing': asset['bars'] = asset['bars'][1:]
                if change == 'metadata': data['calendar_verified'] = False
                with self.assertRaisesRegex(ValueError, 'legacy_frozen_bundle_unverifiable'):
                    self.preview(data)
        self.assertEqual(self.parent_row()['status'], 'frozen')

    def test_modern_frozen_instrument_or_price_revision_is_refused(self):
        for change in ['price', 'lot']:
            with self.subTest(change=change):
                data = copy.deepcopy(self.current)
                if change == 'price': data['assets'][0]['bars'][20].update(open=100, high=101, low=99, close=100)
                else: data['assets'][0]['lot_size'] = 0.001
                with self.assertRaisesRegex(ValueError, 'parent_frozen_history_changed'):
                    self.preview(data)

    def test_selected_evaluated_or_consumed_parent_is_never_recycled(self):
        original = self.parent_row()
        for change in ['selected', 'evaluated', 'result', 'consumed']:
            with self.subTest(change=change):
                plan = json.loads(original['plan'])
                status, result = 'frozen', '{}'
                if change == 'selected': plan['selected'] = {'family': 'buy_hold'}
                if change == 'evaluated': status = 'evaluated'
                if change == 'result': result = '{"state":"candidate_rejected"}'
                if change == 'consumed':
                    self.registry.consume_holdout(plan['scope'], self.original_freeze.isoformat(), self.resume_at.isoformat(), self.parent)
                self.registry.db.execute('UPDATE epochs SET status=?,plan=?,result=? WHERE id=?', (status, json.dumps(plan), result, self.parent))
                with self.assertRaises(ValueError): self.preview()
                self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM epochs').fetchone()[0], 1)
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0], 1)

    def test_stale_confirmation_and_failed_computation_leave_parent_and_history_intact(self):
        token = self.preview()['expected_parent_sha256']
        with self.assertRaisesRegex(ValueError, 'parent_changed_since_preview'):
            apply_resume(self.current, self.registry, self.parent, '0' * 64, self.resume_at)
        original = self.parent_row()
        event_count = self.registry.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        with patch('research_lab.research.simulate', side_effect=RuntimeError('private simulated failure')):
            with self.assertRaises(RuntimeError):
                apply_resume(self.current, self.registry, self.parent, token, self.resume_at)
        self.assertEqual(self.parent_row(), original)
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM epochs').fetchone()[0], 1)
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], event_count)

    def test_audit_failure_rolls_back_new_plan_and_superseded_parent_together(self):
        token = self.preview()['expected_parent_sha256']
        original = self.parent_row()
        with patch('research_lab.research.simulate', return_value=GOOD), patch.object(self.registry, 'event', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                apply_resume(self.current, self.registry, self.parent, token, self.resume_at)
        self.assertEqual(self.parent_row(), original)
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM epochs').fetchone()[0], 1)
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0], 0)

    def test_cli_requires_confirmation_preserves_live_guard_and_respects_worker_lock(self):
        with self.assertRaisesRegex(ValueError, 'expected_parent_sha256_required'):
            run(self.root, self.parent, apply=True)
        config_path = self.root / 'user_data/config.dryrun.json'
        config = json.loads(config_path.read_text()); config['dry_run'] = False
        config_path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'simulation_spot_required'):
            run(self.root, self.parent)
        with (self.state / 'worker.lock').open('r') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'research_worker_busy'):
                run(self.root, self.parent)

    def test_cli_never_initializes_missing_or_incomplete_state(self):
        missing = self.root / 'missing'
        with self.assertRaisesRegex(ValueError, 'existing_research_state_required'):
            run(missing, self.parent)
        self.assertFalse(missing.exists())
        # No application schema is allowed to be reconstructed by this command.
        empty_root = self.root / 'incomplete'; state = empty_root / 'research_state'
        state.mkdir(parents=True); (state / 'worker.lock').touch()
        with sqlite3.connect(state / 'registry.sqlite') as db: db.execute('CREATE TABLE preserved_marker(value TEXT)')
        (state / 'crypto_daily.json').write_text(json.dumps(self.current))
        (empty_root / 'user_data').mkdir()
        (empty_root / 'user_data/config.dryrun.json').write_bytes((self.root / 'user_data/config.dryrun.json').read_bytes())
        before = (state / 'registry.sqlite').read_bytes()
        with self.assertRaises(sqlite3.OperationalError):
            run(empty_root, self.parent, apply=True, expected_parent_sha256='0' * 64)
        self.assertEqual((state / 'registry.sqlite').read_bytes(), before)

    def test_cli_apply_uses_time_after_development_and_does_not_contact_any_engine(self):
        preview = run(self.root, self.parent)
        before = datetime.now(timezone.utc)
        with patch('research_lab.research.simulate', side_effect=eligible):
            result = run(self.root, self.parent, apply=True, expected_parent_sha256=preview['expected_parent_sha256'])
        after = datetime.now(timezone.utc)
        self.assertLessEqual(before, stamp(result['frozen_at']))
        self.assertLessEqual(stamp(result['frozen_at']), after)
        self.assertFalse(result['broker_orders_activated'])
        with self.assertRaisesRegex(ValueError, 'frozen_parent_required'):
            run(self.root, self.parent, apply=True, expected_parent_sha256=preview['expected_parent_sha256'])

    def test_cli_error_output_never_contains_upstream_free_text(self):
        for error in [RuntimeError('private-secret'), ValueError('PrivateSensitiveToken123')]:
            stream = io.StringIO()
            with patch('research_lab.resume.run', side_effect=error), patch('sys.stdout', new=stream):
                code = main(['--parent-epoch', self.parent])
            self.assertEqual(code, 2)
            output = json.loads(stream.getvalue())
            self.assertEqual(output['state'], 'resume_refused')
            self.assertEqual(output['error_code'], type(error).__name__)
            self.assertNotIn('private-secret', stream.getvalue())
            self.assertNotIn('PrivateSensitiveToken123', stream.getvalue())

    def test_paused_root_and_future_consumed_windows_refuse_without_state_reset(self):
        self.registry.db.execute("UPDATE bots SET status='paused_risk' WHERE id='root'")
        with self.assertRaisesRegex(ValueError, 'research_only_root_required'): self.preview()
        self.registry.db.execute("UPDATE bots SET status='research_only' WHERE id='root'")
        scope = json.loads(self.parent_row()['plan'])['scope']
        self.registry.consume_holdout(scope, self.resume_at.isoformat(), (self.resume_at + timedelta(days=1)).isoformat(), 'future-reservation')
        with self.assertRaisesRegex(ValueError, 'inconsistent_consumed_window'): self.preview()
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
