"""Pinned TradingAgents research, never imported by the execution engines.

The existing Jarvis reasoning gateway keeps credentials and quota policy.
No new provider, historical grid, broker connection or account key is added.
"""
import argparse
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

TICKERS = {'CRYPTO-EUR': 'crypto', 'ACTIONS-USD': 'stock'}
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


def clean_text(value):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+|AIza[\w-]+', '[masqué]', value)
    return ''.join(c for c in value if c.isprintable() or c == '\n')[:700]


def bridge_ready():
    return os.environ.get('MARKET_ROOM_BACKEND') == 'jarvis_bridge' and len(os.environ.get('MARKET_ROOM_BRIDGE_TOKEN', '')) >= 24


def advisory_graph(llm):
    """Reuse upstream debate/risk agents, with our verified reports as input.

    No analyst tool binding: the existing Jarvis reasoning bridge intentionally
    rejects tools. This avoids new data accounts, paid providers and stale
    external USD quotes for an EUR portfolio.
    """
    from langgraph.graph import StateGraph, START, END
    from tradingagents.agents import (AgentState, create_bull_researcher, create_bear_researcher,
        create_research_manager, create_trader, create_aggressive_debator,
        create_conservative_debator, create_neutral_debator, create_portfolio_manager)
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.setup import DEBATE_PATH_MAP, RISK_ANALYSIS_PATH_MAP
    logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    graph = StateGraph(AgentState)
    factories = {'Bull Researcher': create_bull_researcher, 'Bear Researcher': create_bear_researcher,
                 'Research Manager': create_research_manager, 'Trader': create_trader,
                 'Aggressive Analyst': create_aggressive_debator, 'Conservative Analyst': create_conservative_debator,
                 'Neutral Analyst': create_neutral_debator, 'Portfolio Manager': create_portfolio_manager}
    for name, factory in factories.items():
        graph.add_node(name, factory(llm))
    graph.add_edge(START, 'Bull Researcher')
    for name in ('Bull Researcher', 'Bear Researcher'):
        graph.add_conditional_edges(name, logic.should_continue_debate, DEBATE_PATH_MAP)
    graph.add_edge('Research Manager', 'Trader')
    graph.add_edge('Trader', 'Aggressive Analyst')
    for name in ('Aggressive Analyst', 'Conservative Analyst', 'Neutral Analyst'):
        graph.add_conditional_edges(name, logic.should_continue_risk_analysis, RISK_ANALYSIS_PATH_MAP)
    graph.add_edge('Portfolio Manager', END)
    return graph.compile()


def analyze(ticker, as_of, work):
    verify_package()
    if not bridge_ready():
        raise ValueError('existing_jarvis_bridge_required')
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult, ChatGeneration
    from tradingagents.graph.propagation import Propagator
    from tradingagents.dataflows.config import run_config
    from tradingagents.agents.rating import run_rating
    from urllib.request import Request, build_opener, ProxyHandler
    budget = CallBudget()
    class ReasoningBridge(BaseChatModel):
        @property
        def _llm_type(self):
            return 'jarvis-existing-reasoning-bridge'
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            budget.reserve([messages])
            body = {'model': 'jarvis/router-shadow', 'messages': [
                {'role': 'assistant' if message.type == 'ai' else ('system' if message.type == 'system' else 'user'),
                 'content': str(message.content)} for message in messages]}
            req = Request('http://127.0.0.1:20129/v1/chat/completions',
                          data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
                          'Authorization': 'Bearer ' + os.environ['MARKET_ROOM_BRIDGE_TOKEN']})
            with build_opener(ProxyHandler({})).open(req, timeout=35) as response:
                data = json.loads(response.read(64000))
            content = data['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError('empty_bridge_response')
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content[:6000]))])
    evidence = json.loads((work / 'evidence.json').read_text())
    config = {'output_language': 'French'}
    state = Propagator().create_initial_state(ticker, as_of[:10], asset_type=TICKERS[ticker],
        instrument_context='Analyse du desk ' + ticker + '. Simulation uniquement. Aucun ordre ni changement de stratégie. '
                           'Utilise seulement les preuves fournies, distingue dates et devises et propose des vérifications humaines.')
    state.update(market_report=json.dumps(evidence, ensure_ascii=False),
                 news_report='Aucun flux d’actualité indépendant fourni. Ne pas inventer de nouvelles.',
                 fundamentals_report='Pas de données fondamentales indépendantes ; aucune inférence de valorisation.',
                 sentiment_report='Sentiment non collecté.')
    with run_config(config):
        state = advisory_graph(ReasoningBridge()).invoke(state, config={'recursion_limit': 20})
    rating = run_rating(state)
    roles = {key: clean_text(state.get(key)) for key in ('market_report', 'news_report')}
    debate = state.get('investment_debate_state', {})
    roles.update(bull=clean_text(debate.get('bull_history')), bear=clean_text(debate.get('bear_history')),
                 risk=clean_text(state.get('risk_debate_state', {}).get('history')),
                 decision=clean_text(state.get('final_trade_decision')))
    rating = rating if rating in {'Buy', 'Overweight', 'Hold', 'Underweight', 'Sell'} else 'REVIEW'
    return {'ticker': ticker, 'as_of': as_of, 'state': 'complete', 'rating': rating,
            'quote_currency': 'EUR' if ticker == 'CRYPTO-EUR' else 'USD', 'portfolio_context': 'sanitized_bot_reports',
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
                                               'MARKET_ROOM_BACKEND', 'MARKET_ROOM_BRIDGE_TOKEN') if key in os.environ}
        env['HOME'] = str(work)
        (work / 'evidence.json').write_bytes((runtime / 'evidence.json').read_bytes())
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
        if not bridge_ready():
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
        crypto = {key: report.get(key) for key in ['mode', 'observed_at', 'equity_eur', 'total_return_pct', 'closed_trades', 'v2', 'alerts']}
        crypto.update(currency='EUR', risk=research.get('risk_control'), v3_historical=research.get('v3_results'),
                      v3_observed_at=research.get('v3_observed_at'))
        atomic_write(runtime / 'evidence.json', json.dumps(crypto, ensure_ascii=False, allow_nan=False))
        analyses = [runner('CRYPTO-EUR', as_of, runtime)]
        session = research.get('equity_paper', {}).get('last_session')
        if fresh(session, now, 96 * 3600):
            equity = {key: research.get(key) for key in ['equity_paper', 'equity_v3', 'equities', 'sessions', 'required', 'observed_at', 'errors']}
            equity['currency'] = 'USD'
            atomic_write(runtime / 'evidence.json', json.dumps(equity, ensure_ascii=False, allow_nan=False))
            item = runner('ACTIONS-USD', as_of, runtime)
            item['bot_last_closed_session'] = session
            analyses.append(item)
        payload = {'schema_version': 1, 'generated_at': now.isoformat(), 'upstream_commit': UPSTREAM_COMMIT,
                   'can_trade': False, 'budget_eur': 0, 'provider': 'existing_jarvis_reasoning_bridge',
                   'actual_upstream_model_verified': False,
                   'analyses': analyses}
        atomic_write(path, json.dumps(payload, ensure_ascii=False, allow_nan=False))
        lines = ['# Avis TradingAgents, à examiner', '', 'Aucun ordre. Rapports des bots, EUR et USD séparés. Aucun flux de nouvelles indépendant.']
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
