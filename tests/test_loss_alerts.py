import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from supervisor import loss_alerts

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
POLICY = {'id': 'market-room-100eur-20261009'}


def crypto(equity):
    return {'api_ok': True, 'database_ok': True, 'equity_eur': equity}


class ThresholdConfigTests(unittest.TestCase):
    def test_default_is_five_percent(self):
        self.assertEqual(loss_alerts.threshold_pct(POLICY, environ={}), 5.0)

    def test_env_overrides_policy(self):
        policy = {**POLICY, 'loss_alert_threshold_pct': 3}
        self.assertEqual(loss_alerts.threshold_pct(policy, environ={'LOSS_ALERT_THRESHOLD_PCT': '2.5'}), 2.5)

    def test_policy_key_used_without_env(self):
        policy = {**POLICY, 'loss_alert_threshold_pct': 3}
        self.assertEqual(loss_alerts.threshold_pct(policy, environ={}), 3.0)

    def test_invalid_values_fall_back_to_default(self):
        for raw in ['abc', '0', '-5', '80', 'nan', 'inf']:
            with self.subTest(raw=raw):
                self.assertEqual(loss_alerts.threshold_pct(POLICY, environ={'LOSS_ALERT_THRESHOLD_PCT': raw}), 5.0)
        self.assertEqual(loss_alerts.threshold_pct({**POLICY, 'loss_alert_threshold_pct': True}, environ={}), 5.0)


class LossAlertUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports = Path(self.tmp.name)
        env = patch.dict('os.environ', {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        import os
        os.environ.pop('LOSS_ALERT_THRESHOLD_PCT', None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_alert_below_five_percent(self):
        self.assertEqual(loss_alerts.update(crypto(95.01), self.reports, NOW, POLICY), [])

    def test_alert_at_five_percent_is_notify_only_and_logged(self):
        with self.assertLogs('supervisor.loss_alerts', level='WARNING') as logs:
            events = loss_alerts.update(crypto(94.9), self.reports, NOW, POLICY)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['loss_level_pct'], 5)
        self.assertEqual(events[0]['threshold_pct'], 5.0)
        self.assertEqual(events[0]['action'], 'notify_only')
        self.assertIn('loss_alert', logs.output[0])

    def test_alert_not_repeated_for_same_level(self):
        loss_alerts.update(crypto(94.0), self.reports, NOW, POLICY)
        events = loss_alerts.update(crypto(93.0), self.reports, NOW, POLICY)
        self.assertEqual(len(events), 1)
        events = loss_alerts.update(crypto(89.0), self.reports, NOW, POLICY)
        self.assertEqual([e['loss_level_pct'] for e in events], [5, 10])

    def test_ledger_persisted(self):
        loss_alerts.update(crypto(94.0), self.reports, NOW, POLICY)
        ledger = json.loads((self.reports / 'loss-alerts.json').read_text())
        self.assertEqual(ledger['seen'][POLICY['id'] + ':crypto'], 5)

    def test_env_threshold_changes_trigger(self):
        with patch.dict('os.environ', {'LOSS_ALERT_THRESHOLD_PCT': '2'}):
            events = loss_alerts.update(crypto(97.5), self.reports, NOW, POLICY)
        self.assertEqual(events[0]['loss_level_pct'], 2)
        self.assertEqual(events[0]['threshold_pct'], 2.0)

    def test_unhealthy_telemetry_never_alerts(self):
        report = {'api_ok': False, 'database_ok': True, 'equity_eur': 50.0}
        self.assertEqual(loss_alerts.update(report, self.reports, NOW, POLICY), [])

    def test_module_never_stops_bots(self):
        source = Path(loss_alerts.__file__).read_text()
        for forbidden in ['subprocess', 'docker', 'forceexit', 'force_exit', '/stop', 'stopentry']:
            self.assertNotIn(forbidden, source.lower())


if __name__ == '__main__':
    unittest.main()
