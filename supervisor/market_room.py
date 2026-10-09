"""Evidence desks, independent of the optional LLM research process.

No broker, exchange mutation, strategy or portfolio writer is imported here.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

UPSTREAM_COMMIT = '1394a3f72aa4393e1a98f51b382434c4b4c2d972'
DESKS = ('crypto', 'equities', 'research', 'risk')


def fresh(value, now, limit):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.tzinfo is not None and 0 <= (now - date).total_seconds() <= limit
    except (ValueError, TypeError, AttributeError):
        return False


def read_ai(reports, now):
    try:
        path = Path(reports) / 'tradingagents.json'
        if path.stat().st_size > 20000:
            raise ValueError('large_ai_report')
        raw = json.loads(path.read_text())
        if (raw.get('schema_version') != 1 or raw.get('upstream_commit') != UPSTREAM_COMMIT
                or raw.get('can_trade') is not False or raw.get('budget_eur') != 0):
            raise ValueError('invalid_ai_report')
        if not fresh(raw.get('generated_at'), now, 36 * 3600):
            return {'state': 'stale', 'analyses': []}
        analyses = []
        for item in raw.get('analyses', [])[:2]:
            if not isinstance(item, dict) or item.get('ticker') not in {'BTC-USD', 'SOFI'}:
                continue
            # LLM text stays in the private source file. Only typed, bounded
            # status/rating crosses the general telemetry interface.
            state = item.get('state') if item.get('state') in {'complete', 'failed', 'budget_exceeded'} else 'invalid'
            rating = item.get('rating') if item.get('rating') in {'Buy', 'Overweight', 'Hold', 'Underweight', 'Sell', 'REVIEW'} else 'REVIEW'
            as_of = item.get('as_of') if fresh(item.get('as_of'), now, 96 * 3600) else None
            analyses.append({'ticker': item['ticker'], 'quote_currency': 'USD', 'state': state,
                             'rating': rating if state == 'complete' and as_of else 'REVIEW',
                             'as_of': as_of,
                             'calls': item.get('calls') if type(item.get('calls')) is int and 0 <= item['calls'] <= 16 else None})
        return {'state': 'current', 'observed_at': raw['generated_at'], 'analyses': analyses}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'state': 'not_configured', 'analyses': []}


def build(report, reports, now=None):
    now = now or datetime.now(timezone.utc)
    research = report.get('research', {})
    risk = research.get('risk_control', {})
    halted = risk.get('state') in {'paused_risk', 'retired'}
    crypto_ok = report.get('api_ok') is True and report.get('database_ok') is True and fresh(report.get('observed_at'), now, 900)
    paper = research.get('equity_paper', {})
    paper_ok = research.get('state') == 'current' and paper.get('state') == 'paper_active'
    decisions = []
    if halted:
        decisions.append('review_crypto_risk_halt')
    elif not crypto_ok:
        decisions.append('verify_crypto_telemetry')
    if paper.get('closed_trades') == 0:
        decisions.append('paper_no_trade_evidence')
    if research.get('equities') == 'insufficient_development_history':
        decisions.append('equity_rolling_2y_below_600_sessions')
    if research.get('v3_crypto') == 'all_rejected':
        decisions.append('no_v3_candidate_validated')
    return {'schema_version': 1, 'observed_at': report['generated_at'], 'mode': 'ADVISORY_ONLY',
            'upstream': 'TauricResearch/TradingAgents', 'upstream_version': '0.6.0',
            'upstream_commit': UPSTREAM_COMMIT, 'can_trade': False, 'budget_eur': 0,
            'approval_required': True, 'desks': {
                'crypto': {'state': 'risk_halted' if halted else ('observed' if crypto_ok else 'unverified'), 'currency': 'EUR'},
                'equities': {'state': 'observed' if paper_ok else 'unverified', 'currency': 'USD'},
                'research': {'state': 'rejected' if research.get('v3_crypto') == 'all_rejected' else 'unverified'},
                'risk': {'state': 'human_review_required' if halted else ('monitoring' if crypto_ok else 'unverified')}},
            'decisions': decisions, 'ai': read_ai(reports, now)}


def render(room):
    labels = {'crypto': 'Crypto (EUR)', 'equities': 'Actions (USD)', 'research': 'Recherche historique', 'risk': 'Risque indépendant'}
    lines = ['# Salle des marchés supervisée', '', '- TradingAgents 0.6.0, analyse consultative uniquement.',
             '- Budget IA : 0 EUR. Aucun avis ne modifie un ordre, une stratégie ou un état financier.',
             '- Observation : ' + room['observed_at']]
    lines += ['- ' + labels[name] + ' : ' + room['desks'][name]['state'] for name in DESKS]
    lines += ['', '## Points à examiner'] + ['- ' + value for value in room['decisions']]
    lines += ['', '## Analyses IA', '- État : ' + room['ai']['state']]
    for item in room['ai'].get('analyses', []):
        lines.append('- ' + item['ticker'] + ' (USD, contexte externe) : ' + item['state'] + ' / ' + item['rating'] + '. Avis à vérifier, pas un ordre.')
    lines.append('\nBTC-USD ne mesure pas le portefeuille Kraken EUR. Zéro transaction ne démontre aucune rentabilité.\n')
    return '\n'.join(lines)
