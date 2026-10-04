"""Persistent limits and genealogy. Retiring a bot never deletes its history."""
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timezone
from .data import finite, stamp, canonical_hash

MAX_BOTS = 3
MAX_DEPTH = 2
MAX_DRAWDOWN = 0.05
VIRTUAL_CAPACITY = 100.0


class Registry:
    def __init__(self, path, initialize=True):
        target = str(path) if initialize else 'file:' + quote(str(Path(path).resolve()), safe='/') + '?mode=rw'
        self.db = sqlite3.connect(target, timeout=5, isolation_level=None, uri=not initialize)
        self.db.row_factory = sqlite3.Row
        if not initialize:
            return
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS bots(id TEXT PRIMARY KEY,parent TEXT,depth INTEGER,
            capacity REAL,status TEXT,validated INTEGER DEFAULT 0,spec TEXT);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at TEXT,type TEXT,payload TEXT);
          CREATE TABLE IF NOT EXISTS epochs(id TEXT PRIMARY KEY,plan TEXT,status TEXT,result TEXT);
          CREATE TABLE IF NOT EXISTS consumed(scope TEXT,start TEXT,end TEXT,epoch TEXT UNIQUE);
        ''')
        self.db.execute("INSERT OR IGNORE INTO bots VALUES('root',NULL,0,100,'research_only',0,'{}')")

    def close(self):
        self.db.close()

    def event(self, kind, payload):
        self.db.execute('INSERT INTO events(at,type,payload) VALUES(?,?,?)',
                        (datetime.now(timezone.utc).isoformat(), kind, json.dumps(payload, sort_keys=True)))

    def bots(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM bots ORDER BY depth,id')]

    def assess(self, report, now=None):
        now = now or datetime.now(timezone.utc)
        observed = stamp(report.get('observed_at'))
        if not 0 <= (now - observed).total_seconds() <= 900:
            raise ValueError('stale_risk_observation')
        if report.get('schema_version') != 2 or report.get('mode') != 'DRY-RUN' or any(
            report.get(key) is not True for key in ['api_ok', 'database_ok', 'configuration_safe']):
            raise ValueError('unverified_simulation')
        initial = finite(report['starting_balance_eur'], 0.00000001)
        equity = finite(report['equity_eur'])
        peak = max(initial, finite(report.get('equity_peak_eur', initial)))
        reason = 'zero_equity' if equity <= 0 else ('drawdown_limit' if (peak - equity) / peak >= MAX_DRAWDOWN else None)
        status = 'retired' if equity <= 0 else ('paused_risk' if reason else 'research_only')
        previous = self.db.execute("SELECT status FROM bots WHERE id='root'").fetchone()[0]
        if previous == 'paper_validated' and not reason:
            status = previous
        if previous in {'paused_risk', 'retired'} and not reason:
            status, reason = previous, 'halt_latched_manual_review_required'
        if previous != status:
            self.db.execute("UPDATE bots SET status=? WHERE id='root'", (status,))
            self.event('risk_state', {'status': status, 'reason': reason, 'equity': equity})
        return {'state': status, 'reason': reason, 'drawdown_pct': (peak - equity) / peak * 100,
                'destroy_files': False, 'real_money_eligible': False}

    def create_child(self, parent, evidence, now=None):
        # A tenfold deposit, an open/unrealised gain, or a backtest is not a reward.
        now = now or datetime.now(timezone.utc)
        if any(isinstance(evidence.get(key), bool) for key in ['external_cashflows', 'open_positions', 'sessions', 'closed_trades']):
            raise ValueError('invalid_forward_numbers')
        if evidence.get('bot_id') != parent or evidence.get('mode') != 'PAPER' or evidence.get('source') != 'paper_forward_ledger' or evidence.get('verified_forward') is not True or evidence.get('external_cashflows') != 0 or evidence.get('open_positions') != 0:
            raise ValueError('forward_paper_evidence_required')
        if not 0 <= (now - stamp(evidence['observed_at'])).total_seconds() <= 900:
            raise ValueError('stale_growth_evidence')
        initial = finite(evidence['initial_equity'], 0.00000001)
        if finite(evidence['equity']) / initial < 10 or finite(evidence['realized_profit']) < initial * 9:
            raise ValueError('tenfold_realized_growth_required')
        if evidence.get('sessions', 0) < 126 or evidence.get('closed_trades', 0) < 30:
            raise ValueError('insufficient_forward_sample')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT * FROM bots WHERE id=?', (parent,)).fetchone()
            if not row or row['validated'] != 1 or row['status'] != 'paper_validated':
                raise ValueError('validated_parent_required')
            spec = json.loads(row['spec'])
            if initial != spec.get('initial_equity', VIRTUAL_CAPACITY):
                raise ValueError('paper_initial_equity_mismatch')
            if row['depth'] >= MAX_DEPTH or self.db.execute('SELECT COUNT(*) FROM bots').fetchone()[0] >= MAX_BOTS:
                raise ValueError('genealogy_limit')
            if self.db.execute('SELECT 1 FROM bots WHERE parent=?', (parent,)).fetchone():
                raise ValueError('one_child_per_parent')
            capacity = min(20.0, row['capacity'] * 0.25)
            child = parent + '-child'
            self.db.execute('UPDATE bots SET capacity=capacity-? WHERE id=?', (capacity, parent))
            self.db.execute('INSERT INTO bots VALUES(?,?,?,?,?,?,?)', (child, parent, row['depth']+1, capacity, 'research_only', 0, json.dumps({'strategy': spec.get('strategy'), 'initial_equity': capacity})))
            self.event('paper_child_created', {'parent': parent, 'child': child, 'virtual_capacity': capacity,
                                               'broker_credentials_inherited': False, 'money_transferred': False})
            self.db.execute('COMMIT')
            return child
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def consume_holdout(self, scope, start, end, epoch):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT 1 FROM consumed WHERE scope=? AND start<=? AND end>=?', (scope, end, start)).fetchone():
                raise ValueError('holdout_already_consumed')
            self.db.execute('INSERT INTO consumed VALUES(?,?,?,?)', (scope, start, end, epoch))
            self.event('holdout_reserved_before_test', {'scope': scope, 'start': start, 'end': end, 'epoch': epoch})
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
