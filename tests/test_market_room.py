import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from supervisor.market_room import build, read_ai, UPSTREAM_COMMIT
from supervisor.healthcheck import check
from scripts.install_release import activate_preserving_risk
from scripts.install_market_room import bridge_environment
from integrations.tradingagents_runner import CallBudget, run


class MarketRoomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime.now(timezone.utc)
        self.reports = self.root / 'user_data/reports'
        self.reports.mkdir(parents=True)

    def report(self):
        return {'generated_at': self.now.isoformat(), 'observed_at': None,
                'research': {'state': 'current', 'observed_at': self.now.isoformat(),
                    'risk_control': {'state': 'paused_risk', 'stop_result': 'already_stopped_data_preserved'},
                    'equities': 'insufficient_development_history', 'v3_crypto': 'all_rejected',
                    'equity_paper': {'state': 'paper_active', 'closed_trades': 0,
                                     'last_session': (self.now - timedelta(hours=12)).isoformat()}}}

    def test_risk_stop_is_a_decision_and_zero_trades_are_not_success(self):
        room = build(self.report(), self.reports, self.now)
        self.assertEqual(room['desks']['crypto']['state'], 'risk_halted')
        self.assertEqual(room['desks']['crypto']['currency'], 'EUR')
        self.assertEqual(room['desks']['equities']['currency'], 'USD')
        self.assertIn('paper_no_trade_evidence', room['decisions'])
        self.assertFalse(room['can_trade'])
        self.assertTrue(check(self.report(), self.now))
        report = self.report()
        report['research']['observed_at'] = (self.now - timedelta(seconds=901)).isoformat()
        self.assertFalse(check(report, self.now))

    def test_ai_stale_unsafe_or_changed_revision_never_presents_a_rating(self):
        raw = {'schema_version': 1, 'generated_at': self.now.isoformat(), 'upstream_commit': UPSTREAM_COMMIT,
               'can_trade': False, 'budget_eur': 0, 'analyses': [{'ticker': 'ACTIONS-USD', 'rating': 'Buy',
                  'state': 'complete', 'as_of': self.now.isoformat(), 'secret': 'sentinel'}]}
        for update, state in [({'generated_at': (self.now - timedelta(hours=37)).isoformat()}, 'stale'),
                              ({'can_trade': True}, 'not_configured'), ({'upstream_commit': 'wrong'}, 'not_configured')]:
            (self.reports / 'tradingagents.json').write_text(json.dumps({**raw, **update}))
            result = read_ai(self.reports, self.now)
            self.assertEqual(result['state'], state)
            self.assertEqual(result['analyses'], [])
        (self.reports / 'tradingagents.json').write_text(json.dumps(raw))
        self.assertNotIn('sentinel', json.dumps(read_ai(self.reports, self.now)))

    def test_failed_attempt_consumes_daily_budget_without_clearing_history(self):
        (self.reports / 'latest.json').write_text(json.dumps(self.report()))
        (self.reports / 'tradingagents.json').write_text('previous evidence')
        calls = []
        def runner(ticker, as_of, runtime):
            calls.append(ticker)
            return {'ticker': ticker, 'as_of': as_of, 'state': 'failed', 'rating': 'REVIEW'}
        with patch.dict(os.environ, {'MARKET_ROOM_BACKEND': 'jarvis_bridge', 'MARKET_ROOM_BRIDGE_TOKEN': 'synthetic-token-1234567890'}):
            result = run(self.root, self.now, runner)
            self.assertEqual(run(self.root, self.now, runner)['state'], 'daily_budget_consumed')
        self.assertEqual(calls, ['CRYPTO-EUR', 'ACTIONS-USD'])
        self.assertEqual(result['budget_eur'], 0)
        self.assertFalse(result['can_trade'])
        self.assertEqual(next((self.reports / 'tradingagents-archive').iterdir()).read_text(), 'previous evidence')

    def test_absent_free_confirmation_never_calls_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch('integrations.tradingagents_runner.run_child') as provider:
                self.assertEqual(run(self.root, self.now)['state'], 'not_configured')
                provider.assert_not_called()

    def test_call_budget_fails_before_seventeenth_request(self):
        budget = CallBudget()
        for _ in range(16):
            budget.reserve([[SimpleNamespace(content='message')]])
        with self.assertRaisesRegex(ValueError, 'llm_budget_exceeded'):
            budget.reserve([[SimpleNamespace(content='message')]])
        self.assertEqual(budget.calls, 16)

    def test_deployment_cannot_restart_a_risk_stopped_simulation(self):
        (self.root / 'research_state').mkdir()
        with sqlite3.connect(self.root / 'research_state/registry.sqlite') as db:
            db.execute('create table bots(id text,status text)')
            db.execute("insert into bots values('root','paused_risk')")
        with patch('scripts.install_release.preflight_simulation_compose'), patch('scripts.install_release.run') as runner:
            self.assertTrue(activate_preserving_risk(['docker','compose'], ['-d'], self.root))
            self.assertEqual(runner.call_args.args[0], ['docker','compose','up','-d','--force-recreate','--no-deps','supervisor'])
        (self.root / 'research_state/registry.sqlite').write_text('invalid registry')
        with patch('scripts.install_release.preflight_simulation_compose'), patch('scripts.install_release.run') as runner:
            with self.assertRaises(sqlite3.Error):
                activate_preserving_risk(['docker','compose'], ['-d'], self.root)
            runner.assert_not_called()

    def test_only_existing_reasoning_gateway_token_is_selected(self):
        path = self.root / 'bridge-token'
        path.write_text('synthetic-bridge-token-1234567890')
        result = bridge_environment(path)
        self.assertNotIn('GOOGLE_API_KEY', result)
        self.assertIn('MARKET_ROOM_BACKEND=jarvis_bridge', result)
        path.write_text('bad')
        with self.assertRaises(ValueError):
            bridge_environment(path)
