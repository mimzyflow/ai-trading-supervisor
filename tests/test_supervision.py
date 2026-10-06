import copy
import io
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from supervisor import report, healthcheck, loop, publish_github_issue
from supervisor.api import ReadOnlyAPI, TelemetryError
from scripts.check_simulation import validate


class FakeAPI:
    def __init__(self, values=None, fail=False):
        self.values = values or {
            "show_config": {"dry_run": True, "state": "running", "strategy": "MoussaBaseline", "version": "test", "timeframe": "15m", "trading_mode": "spot", "exchange": "kraken", "stake_currency": "EUR", "stake_amount": "10", "max_open_trades": -1, "stoploss": -0.04, "force_entry_enable": False},
            "balance": {"total": 97.0, "starting_capital": 90.0},
            "profit": {"profit_all_coin": -3.0, "profit_closed_coin": 1.0, "trade_count": 2, "closed_trade_count": 1},
            "status": [{"pair": "ETH/EUR", "stake_amount": 20}],
        }
        self.fail = fail

    def snapshot(self):
        if self.fail:
            raise TelemetryError("api_unreachable")
        return copy.deepcopy(self.values)


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "tradesv3.dryrun.sqlite"
        self.log = self.root / "freqtrade.log"
        self.log.write_text("fresh log")
        patches = [patch.object(report, "DB", self.db), patch.object(report, "LOG", self.log), patch.object(report, "REPORTS", self.root), patch.object(publish_github_issue, "REPORTS", self.root), patch.dict(os.environ, {"SIMULATION_START_BALANCE_EUR": "100", "GITHUB_STATUS_TOKEN": ""})]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE trades (id INTEGER, pair TEXT, is_open INTEGER, close_profit REAL, close_profit_abs REAL, close_date TEXT, exit_reason TEXT)")
            conn.execute("INSERT INTO trades VALUES (1,'BTC/EUR',0,0.05,1.0,'2026-10-03','roi')")
            conn.execute("INSERT INTO trades VALUES (2,'ETH/EUR',1,NULL,NULL,NULL,NULL)")

    def test_malformed_research_status_cannot_break_engine_report(self):
        for value in [[], {'generated_at': 1}, {'generated_at': '2026-10-03T00:00:00'},
                      {'generated_at': datetime.now(timezone.utc).isoformat(), 'risk': []}]:
            with self.subTest(value=value):
                (self.root / 'autonomy.json').write_text(json.dumps(value))
                result = report.collect(FakeAPI())
                self.assertTrue(result['api_ok'])
                self.assertEqual(result['research']['state'], 'unavailable')

    def test_research_summary_expires_and_never_exposes_extra_fields(self):
        value = {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
                 'risk': {'state': 'research_only', 'secret': 'test-secret'},
                 'crypto_research': {'state': 'no_candidate_passed_development'},
                 'broker_orders_activated': True, 'real_money_eligible': True, 'max_bots': 999}
        (self.root / 'autonomy.json').write_text(json.dumps(value))
        result = report.read_research()
        self.assertEqual(result['state'], 'current')
        self.assertFalse(result['broker_orders_activated'])
        self.assertFalse(result['real_money_eligible'])
        self.assertEqual(result['max_bots'], 3)
        self.assertNotIn('test-secret', json.dumps(result))
        value['generated_at'] = (datetime.now(timezone.utc) - timedelta(seconds=901)).isoformat()
        (self.root / 'autonomy.json').write_text(json.dumps(value))
        self.assertEqual(report.read_research()['state'], 'stale')

    def test_v2_metrics_exclude_predeployment_baseline(self):
        result = report.collect(FakeAPI())
        self.assertTrue(result["v2"]["baseline_history_excluded"])
        self.assertEqual(result["v2"]["closed_trades"], 0)
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO trades VALUES (3,'SOL/EUR',0,-0.02,-0.2,'2026-10-06 12:00:00','trend_exit')")
        result = report.collect(FakeAPI())
        self.assertEqual(result["v2"]["closed_trades"], 1)
        self.assertEqual(result["v2"]["losses"], 1)
        self.assertAlmostEqual(result["v2"]["realized_profit_eur"], -0.2)

    def test_reports_latent_loss_and_full_wallet_denominator(self):
        result = report.collect(FakeAPI())
        self.assertEqual(result["mode"], "DRY-RUN")
        self.assertEqual(result["unrealized_profit_eur"], -4.0)
        self.assertEqual(result["total_return_pct"], -3.0)
        self.assertEqual(result["committed_capital_eur"], 20.0)
        self.assertEqual(result["estimated_stop_risk_eur"], 0.8)
        self.assertTrue(healthcheck.check(result))
        self.assertEqual(result["publication"]["state"], "not_configured")
        self.assertFalse(result["healthy"])

    def test_missing_database_is_not_created_or_reported_zero(self):
        self.db.unlink()
        result = report.collect(FakeAPI())
        self.assertIsNone(result["total_trades"])
        self.assertFalse(self.db.exists())
        self.assertFalse(healthcheck.check(result))

    def test_corrupt_database_is_explicit(self):
        self.db.write_bytes(b"invalid sqlite")
        result = report.collect(FakeAPI())
        self.assertIsNone(result["realized_profit_eur"])
        self.assertFalse(result["database_ok"])
        self.assertTrue(any("base impossible" in a for a in result["alerts"]))

    def test_fresh_log_cannot_prove_running_engine(self):
        result = report.collect(FakeAPI(fail=True))
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["mode"], "UNKNOWN")
        self.assertIsNone(result["observed_at"])
        self.assertEqual(result["activity_note"], "")
        self.assertFalse(healthcheck.check(result))

    def test_live_mode_is_never_mislabelled_dry_run(self):
        api = FakeAPI()
        api.values["show_config"]["dry_run"] = False
        result = report.collect(api)
        self.assertEqual(result["mode"], "LIVE")
        self.assertEqual(result["state"], "degraded")
        self.assertFalse(healthcheck.check(result))
        self.assertTrue(any("CRITIQUE" in a for a in result["alerts"]))

    def test_non_spot_and_excessive_stake_are_rejected(self):
        api = FakeAPI()
        for overrides in [{"trading_mode": "futures"}, {"stake_amount": "21"}, {"max_open_trades": 2}]:
            with self.subTest(overrides=overrides):
                changed = FakeAPI(api.snapshot())
                changed.values["show_config"].update(overrides)
                result = report.collect(changed)
                self.assertFalse(result["configuration_safe"])
                self.assertFalse(healthcheck.check(result))

    def test_nan_and_missing_mode_are_invalid(self):
        for changes in ["nan", "mode"]:
            api = FakeAPI()
            if changes == "nan":
                api.values["balance"]["total"] = float("nan")
            else:
                del api.values["show_config"]["dry_run"]
            result = report.collect(api)
            self.assertFalse(result["api_ok"])
            self.assertEqual(result["state"], "unknown")

    def test_stale_and_future_reports_fail_healthcheck(self):
        result = report.collect(FakeAPI())
        now = datetime.now(timezone.utc)
        for offset in [-901, 60]:
            changed = dict(result, observed_at=(now + timedelta(seconds=offset)).isoformat())
            self.assertFalse(healthcheck.check(changed, now))

    def test_atomic_writes_leave_no_partial_file(self):
        path = self.root / "nested/report.json"
        report.atomic_write(path, '{"mode":"DRY-RUN"}')
        self.assertEqual(json.loads(path.read_text())["mode"], "DRY-RUN")
        self.assertEqual(len(list(path.parent.iterdir())), 1)

    def test_drawdown_persists_between_observations(self):
        first = report.collect(FakeAPI())
        first["equity_peak_eur"] = 105.0
        report.atomic_write(self.root / "latest.json", json.dumps(first))
        second = report.collect(FakeAPI())
        self.assertAlmostEqual(second["observed_max_drawdown_pct"], 100 * 8 / 105, places=3)

    def test_missing_github_token_is_not_success(self):
        self.assertEqual(publish_github_issue.main(), 3)
        self.assertEqual(json.loads((self.root / "publication.json").read_text())["state"], "not_configured")

    def test_stale_github_payload_never_reaches_network(self):
        result = report.collect(FakeAPI())
        result["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        (self.root / "latest.json").write_text(json.dumps(result))
        (self.root / "latest.md").write_text("stale")
        with patch.dict(os.environ, {"GITHUB_STATUS_TOKEN": "test-only"}), patch("urllib.request.build_opener") as network:
            self.assertEqual(publish_github_issue.main(), 4)
            network.assert_not_called()

    def test_failure_does_not_defer_publish_for_an_hour(self):
        schedule = loop.Schedule()
        reports, attempts = [], []
        def make_report(archive):
            reports.append(archive)
            return 0
        def fail():
            attempts.append(True)
            return 2
        schedule.tick(10, make_report, fail)
        self.assertEqual(schedule.next_publish, 70)
        schedule.tick(69, make_report, fail)
        self.assertEqual(len(attempts), 1)
        schedule.tick(70, make_report, fail)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(schedule.next_publish, 190)

    def test_failed_report_is_never_published(self):
        with patch.object(loop, "save_state") as save, patch.object(loop, "publish") as publisher:
            self.assertFalse(loop.Schedule().tick(0, lambda _: 2, publisher))
            publisher.assert_not_called()
            save.assert_called_with("report_failed", "report_process_failed")


class APITests(unittest.TestCase):
    def test_order_endpoints_and_external_hosts_are_forbidden(self):
        for url in ["https://example.com", "http://freqtrade@evil.example", "http://freqtrade:8080?redirect=evil"]:
            with self.assertRaises(TelemetryError):
                ReadOnlyAPI(url, "user", "password")
        api = ReadOnlyAPI("http://freqtrade:8080", "user", "password")
        with self.assertRaises(TelemetryError):
            api.get("forceenter")

    def test_requests_are_get_and_exception_secrets_are_redacted(self):
        def opener(request, timeout):
            self.assertEqual(request.method, "GET")
            raise OSError("secret-value")
        api = ReadOnlyAPI("http://freqtrade:8080", "user", "password", opener)
        with self.assertRaises(TelemetryError) as context:
            api.get("balance")
        self.assertNotIn("secret-value", str(context.exception))


class SimulationTests(unittest.TestCase):
    def test_guard_rejects_live_leverage_keys_and_excessive_stake(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "user_data/config.dryrun.json").read_text())
        self.assertTrue(validate(config))
        for overrides in [{"dry_run": False}, {"trading_mode": "futures"}, {"stake_amount": 21}, {"force_entry_enable": True}, {"exchange": {"name": "kraken", "key": "test-secret"}}, {"add_config_files": ["private.json"]}]:
            changed = copy.deepcopy(config)
            changed.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                validate(changed)


if __name__ == "__main__":
    unittest.main()
