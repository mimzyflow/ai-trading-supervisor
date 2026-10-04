"""Explicit development refreeze. No broker, engine or network call is exposed."""
import argparse
import fcntl
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from scripts.check_simulation import validate as validate_simulation
from .governor import Registry
from .research import apply_resume, prepare_resume
from .worker import read_json

REFUSAL_CODES = frozenset({
    'expected_parent_sha256_required', 'existing_research_state_required', 'research_worker_busy',
    'frozen_parent_required', 'parent_changed_since_preview', 'unselected_unevaluated_parent_required',
    'resume_scope_mismatch', 'parent_freeze_is_future', 'invalid_parent_implementation',
    'implementation_unchanged', 'research_only_root_required', 'invalid_parent_history_proof',
    'parent_frozen_history_changed', 'inconsistent_parent_history_cutoff',
    'legacy_frozen_bundle_unverifiable', 'insufficient_development_history',
    'parent_has_consumed_holdout', 'inconsistent_consumed_window', 'competing_research_plan',
    'implementation_changed_during_resume', 'invalid_frozen_history_count', 'frozen_history_missing',
})


def run(root, parent_epoch, apply=False, expected_parent_sha256=None, data_file=None):
    root = Path(root).resolve()
    state = root / 'research_state'
    database = state / 'registry.sqlite'
    if apply and not expected_parent_sha256:
        raise ValueError('expected_parent_sha256_required')
    if not database.is_file() or not (state / 'worker.lock').is_file():
        raise ValueError('existing_research_state_required')
    # The existing worker lock is opened read-only; preview creates no file.
    with (state / 'worker.lock').open('r') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('research_worker_busy') from None
        validate_simulation(read_json(root / 'user_data/config.dryrun.json'))
        data_path = Path(data_file).resolve() if data_file else state / 'crypto_daily.json'
        bundle = read_json(data_path)
        now = datetime.now(timezone.utc)
        if apply:
            registry = Registry(database, initialize=False)
            try:
                return apply_resume(bundle, registry, parent_epoch, expected_parent_sha256)
            finally:
                registry.close()
        db = sqlite3.connect('file:' + quote(str(database), safe='/') + '?mode=ro', uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            return prepare_resume(bundle, db, parent_epoch, now, expected_parent_sha256)
        finally:
            db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Refreeze an unselected development plan explicitly; preserves all evidence.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--parent-epoch', required=True)
    parser.add_argument('--data', type=Path, help='Explicit dataset path; defaults to research_state/crypto_daily.json')
    parser.add_argument('--apply', action='store_true', help='Explicit decision to create a new development revision')
    parser.add_argument('--expected-parent-sha256', help='Fingerprint from a successful preview; mandatory for --apply')
    args = parser.parse_args(argv)
    try:
        result = run(args.root, args.parent_epoch, args.apply, args.expected_parent_sha256, args.data)
    except Exception as exc:
        # Fixed internal refusal codes only, never upstream exception text.
        code = str(exc) if type(exc) is ValueError and str(exc) in REFUSAL_CODES else type(exc).__name__
        print(json.dumps({'state': 'resume_refused', 'error_code': code,
                          'broker_orders_activated': False, 'real_money_eligible': False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
