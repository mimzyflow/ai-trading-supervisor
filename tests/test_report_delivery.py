import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from supervisor import report


class ResearchDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.patch = patch.object(report, 'REPORTS', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.now = datetime.now(timezone.utc)

    def payload(self):
        paper = {'state': 'paper_active', 'mode': 'BROKERLESS_PAPER', 'real_money_eligible': False,
                 'equity': 100, 'return_pct': 0, 'cash': 100, 'open_positions': 0,
                 'closed_trades': 0, 'wins': 0, 'losses': 0, 'profit_factor': None,
                 'max_drawdown_pct': 0, 'last_session': (self.now - timedelta(hours=12)).isoformat(),
                 'credentials': 'DO_NOT_COPY'}
        return {'schema_version': 1, 'generated_at': self.now.isoformat(),
                'risk': {'state': 'research_only'}, 'crypto_research': {'state': 'no_candidate_passed_development'},
                'equities': {'state': 'insufficient_development_history', 'sessions': 500, 'required': 600,
                             'paper': paper, 'v3_shadow': {'regime_momentum': paper}},
                'v3_challengers': {'state': 'all_rejected', 'observed_at': self.now.isoformat(),
                                  'challengers': {'regime_momentum': {
                                      'result': {'return_pct': -4.6, 'profit_factor': .67,
                                                 'max_drawdown_pct': 7.2, 'closed_trades': 29},
                                      'gate': {'state': 'rejected', 'reasons': ['insufficient_trades']}}}},
                'errors': ['test_worker_ValueError']}

    def read(self, value):
        (self.root / 'autonomy.json').write_text(json.dumps(value))
        with patch.object(report, 'utcnow', return_value=self.now):
            return report.read_research()

    def test_delivers_equity_and_rejection_metrics_without_private_fields(self):
        result = self.read(self.payload())
        self.assertEqual(result['equity_paper']['equity'], 100)
        self.assertEqual(result['equity_v3']['regime_momentum']['currency'], 'USD')
        self.assertEqual(result['v3_results']['regime_momentum']['state'], 'rejected')
        self.assertEqual(result['v3_results']['regime_momentum']['reasons'], ['insufficient_trades'])
        self.assertEqual(result['sessions'], 500)
        self.assertNotIn('DO_NOT_COPY', json.dumps(result))

    def test_expired_or_future_worker_clears_all_equity_numbers(self):
        for offset in [-901, 1]:
            payload = self.payload()
            payload['generated_at'] = (self.now + timedelta(seconds=offset)).isoformat()
            result = self.read(payload)
            self.assertEqual(result['state'], 'stale')
            self.assertNotIn('equity_paper', result)

    def test_malformed_subsections_do_not_crash_delivery(self):
        for value in [None, [], 'invalid']:
            payload = self.payload()
            payload['equities']['v3_shadow'] = value
            payload['v3_challengers']['challengers'] = value
            result = self.read(payload)
            self.assertEqual(result['state'], 'current')
            self.assertEqual(result['equity_v3'], {})
            self.assertEqual(result['v3_results'], {})

    def test_unsafe_paper_and_nonfinite_numbers_never_look_valid(self):
        payload = self.payload()
        payload['equities']['paper']['real_money_eligible'] = True
        self.assertEqual(self.read(payload)['equity_paper'], {'state': 'unavailable'})
        payload = self.payload()
        payload['equities']['paper']['equity'] = float('nan')
        payload['equities']['paper']['closed_trades'] = True
        result = self.read(payload)
        self.assertIsNone(result['equity_paper']['equity'])
        self.assertIsNone(result['equity_paper']['closed_trades'])
        json.dumps(result, allow_nan=False)

    def test_markdown_contains_both_currencies_and_no_activity_claim_on_zero_trades(self):
        research = self.read(self.payload())
        data = {'generated_at': self.now.isoformat(), 'mode': 'DRY-RUN', 'state': 'active',
                'strategy': 'MoussaBaseline', 'strategy_validation_state': 'research_only',
                'alerts': [], 'research': research}
        output = report.render(data)
        self.assertIn('Valeur simulée EUR', output)
        self.assertIn('Valeur USD : 100', output)
        self.assertIn('Zéro transaction', output)
        self.assertIn('insufficient_trades', output)


if __name__ == '__main__':
    unittest.main()
