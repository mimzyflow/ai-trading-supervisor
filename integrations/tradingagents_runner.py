"""Pinned TradingAgents research, never imported by the execution engines.

Only an explicitly verified existing Gemini free tier is allowed. No provider
fallback, historical grid, broker connection, account context or paid API.
"""
import argparse
import copy
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from importlib.metadata import distribution
from pathlib import Path
from supervisor.market_room import UPSTREAM_COMMIT, fresh
from supervisor.report import atomic_write

TICKERS = {'BTC-USD': 'crypto', 'SOFI': 'stock'}
MAX_CALLS = 16
MAX_INPUT_CHARS = 240000
ROLE_KEYS = ('market_report', 'news_report', 'bull', 'bear', 'risk', 'decision')


class CallBudget:
    def __init__(self):
        self.calls = 0
        self.characters = 0
        self.lock = threading.Lock()

    def reserve(self, messages):
        size = sum(len(str(message.content)) for batch in messages for message in batch)
        with self.lock:
            if self.calls >= MAX_CALLS or self.characters + size > MAX_INPUT_CHARS:
                raise ValueError('llm_budget_exceeded')
            self.calls += 1
            self.characters += size


def verify_package():
    installed = distribution('tradingagents')
    origin = json.loads(installed.read_text('direct_url.json') or '{}')
    if installed.version != '0.6.0' or origin.get('vcs_info', {}).get('commit_id') != UPSTREAM_COMMIT:
        raise ValueError('unpinned_tradingagents_package')


def configuration(work):
    if os.environ.get('GEMINI_FREE_TIER_VERIFIED') != '1' or not os.environ.get('GOOGLE_API_KEY'):
        raise ValueError('existing_free_provider_required')
    from tradingagents.default_config import DEFAULT_CONFIG
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(llm_provider='google', quick_think_provider=None, deep_think_provider=None,
                  backend_url=None, quick_think_backend_url=None, deep_think_backend_url=None,
                  quick_think_llm='gemini-3.5-flash-lite', deep_think_llm='gemini-3.5-flash-lite',
                  output_language='French', google_thinking_level='minimal', temperature=0,
                  max_debate_rounds=1, max_risk_discuss_rounds=1, max_tool_rounds=1,
                  max_recur_limit=40, llm_max_retries=0, max_tokens=1024,
                  checkpoint_enabled=False, news_article_limit=3, global_news_article_limit=2,
                  data_vendors={key: 'yfinance' for key in DEFAULT_CONFIG['data_vendors']},
                  tool_vendors={}, results_dir=str(work / 'results'), data_cache_dir=str(work / 'cache'),
                  memory_log_path=str(work / 'memory.md'))
    return config


def clean_text(value):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+|AIza[\w-]+', '[masqué]', value)
    return ''.join(c for c in value if c.isprintable() or c == '\n')[:700]


def analyze(ticker, as_of, work):
    verify_package()
    from langchain_core.callbacks import BaseCallbackHandler
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    budget = CallBudget()

    class BudgetCallback(BaseCallbackHandler):
        raise_error = True
        def on_chat_model_start(self, serialized, messages, **kwargs):
            budget.reserve(messages)

    graph = TradingAgentsGraph(selected_analysts=('market', 'news'), debug=False,
                               config=configuration(work), callbacks=[BudgetCallback()])
    # No persistent learning/settlement: each advisory run has a fresh workspace.
    state, rating = graph.propagate(ticker, as_of[:10], asset_type=TICKERS[ticker], portfolio=None)
    roles = {key: clean_text(state.get(key)) for key in ('market_report', 'news_report')}
    debate = state.get('investment_debate_state', {})
    roles.update(bull=clean_text(debate.get('bull_history')), bear=clean_text(debate.get('bear_history')),
                 risk=clean_text(state.get('risk_debate_state', {}).get('judge_decision')),
                 decision=clean_text(state.get('final_trade_decision')))
    rating = rating if rating in {'Buy', 'Overweight', 'Hold', 'Underweight', 'Sell'} else 'REVIEW'
    return {'ticker': ticker, 'as_of': as_of, 'state': 'complete', 'rating': rating,
            'quote_currency': 'USD', 'portfolio_context': 'not_provided',
            'calls': budget.calls, 'input_characters': budget.characters, 'roles': roles}


def child(ticker, as_of, work):
    # SDK diagnostics never cross the child stdout protocol or enter Jarvis.
    from contextlib import redirect_stdout, redirect_stderr
    try:
        with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
            result = analyze(ticker, as_of, work)
    except Exception as exc:
        result = {'ticker': ticker, 'as_of': as_of, 'state': 'failed', 'rating': 'REVIEW',
                  'error_type': type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


def run_child(ticker, as_of, runtime):
    with tempfile.TemporaryDirectory(dir=runtime, prefix='advisory-') as folder:
        work = Path(folder)
        env = {key: os.environ[key] for key in ('PATH', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'LANG',
                                               'GOOGLE_API_KEY', 'GEMINI_FREE_TIER_VERIFIED') if key in os.environ}
        env['HOME'] = str(work)
        process = subprocess.Popen([sys.executable, '-m', 'integrations.tradingagents_runner',
                                    '--child', ticker, '--as-of', as_of, '--work', str(work)],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   env=env, text=True, start_new_session=True)
        try:
            output, _ = process.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            return {'ticker': ticker, 'as_of': as_of, 'state': 'failed', 'rating': 'REVIEW', 'error_type': 'DeadlineExceeded'}
        try:
            if process.returncode != 0 or len(output.encode()) > 12000:
                raise ValueError('child_failed')
            result = json.loads(output)
            if result.get('ticker') != ticker or result.get('as_of') != as_of:
                raise ValueError('child_scope_mismatch')
            return result
        except (ValueError, AttributeError):
            return {'ticker': ticker, 'as_of': as_of, 'state': 'failed', 'rating': 'REVIEW', 'error_type': 'InvalidResponse'}


def run(root, now=None, runner=run_child):
    now = now or datetime.now(timezone.utc)
    reports = root / 'user_data/reports'
    runtime = root / '.runtime/tradingagents'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (runtime / 'runner.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'already_running'}
        marker = runtime / 'last_attempt.json'
        try:
            previous = json.loads(marker.read_text())
        except (OSError, ValueError):
            previous = {}
        if previous.get('day') == now.date().isoformat():
            return {'state': 'daily_budget_consumed'}
        if os.environ.get('GEMINI_FREE_TIER_VERIFIED') != '1' or not os.environ.get('GOOGLE_API_KEY'):
            return {'state': 'not_configured'}
        report = json.loads((reports / 'latest.json').read_text())
        research = report.get('research', {})
        if not fresh(report.get('generated_at'), now, 900) or research.get('state') != 'current':
            return {'state': 'source_unavailable'}
        # Reserve before any provider call; a crash/failed response consumes the
        # daily attempt too. Re-running cannot create an unbounded retry bill.
        atomic_write(marker, json.dumps({'day': now.date().isoformat()}))
        path = reports / 'tradingagents.json'
        if path.exists():
            old = path.read_bytes()
            import hashlib
            archive = reports / 'tradingagents-archive' / (hashlib.sha256(old).hexdigest() + '.json')
            if not archive.exists():
                atomic_write(archive, old.decode())
        as_of = now.isoformat()
        analyses = [runner('BTC-USD', as_of, runtime)]
        session = research.get('equity_paper', {}).get('last_session')
        if fresh(session, now, 96 * 3600):
            item = runner('SOFI', as_of, runtime)
            item['bot_last_closed_session'] = session
            analyses.append(item)
        payload = {'schema_version': 1, 'generated_at': now.isoformat(), 'upstream_commit': UPSTREAM_COMMIT,
                   'can_trade': False, 'budget_eur': 0, 'provider': 'existing_verified_free_gemini',
                   'analyses': analyses}
        atomic_write(path, json.dumps(payload, ensure_ascii=False, allow_nan=False))
        lines = ['# Avis TradingAgents, à examiner', '', 'Aucun ordre. Données externes USD, portefeuille non transmis.']
        for item in analyses:
            lines += ['', '## ' + item['ticker'] + ' · ' + item['state'] + ' · ' + item['rating']]
            for role, value in item.get('roles', {}).items():
                lines += ['', '### ' + role, '', value]
            if item.get('error_type'):
                lines.append('Analyse indisponible : ' + item['error_type'])
        atomic_write(reports / 'tradingagents.md', '\n'.join(lines) + '\n')
        print(json.dumps({'state': 'finished', 'analyses': [{'ticker': x['ticker'], 'state': x['state']} for x in analyses]}))
        return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--child', choices=TICKERS)
    parser.add_argument('--as-of')
    parser.add_argument('--work', type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.as_of, args.work)
    else:
        run(args.root.resolve())


if __name__ == '__main__':
    main()
