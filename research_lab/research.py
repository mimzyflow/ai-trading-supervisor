"""Four fixed templates, frozen selection, genuinely later one-use holdout."""
import json
import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from .data import canonical_hash, stamp, subset, validate
from .engine import simulate, TEMPLATES


def compact(result):
    return {k: v for k, v in result.items() if k not in {'curve', 'trades'}}


def costs(bundle, stressed=False):
    crypto = all(a['asset_class'] == 'crypto' for a in bundle['assets'])
    # Equity commissions are a conservative test scenario, not a broker quote.
    return {'fee': 0.012 if crypto and stressed else (0.008 if crypto else 0.001),
            'min_commission': 0 if crypto else 1,
            'slippage': 0.0025 if stressed else 0.001}


def quality(bundle):
    universe = bundle.get('historical_universe_verified') is True or (
        bundle.get('universe_policy') == 'fixed_at_freeze' and bundle.get('future_membership_tracking') is True)
    return universe and all(bundle.get(key) is True for key in ['calendar_verified', 'corporate_actions_verified'])


def implementation_hash():
    root = Path(__file__).resolve().parent
    return hashlib.sha256(b''.join((root / name).read_bytes() for name in ['data.py', 'engine.py', 'research.py'])).hexdigest()


def frozen_history_hash(bundle, count):
    """Commit to the development bars and instrument metadata, not later bars."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        raise ValueError('invalid_frozen_history_count')
    assets = []
    for asset in bundle['assets']:
        if len(asset['bars']) < count:
            raise ValueError('frozen_history_missing')
        assets.append({**asset, 'bars': asset['bars'][:count]})
    return canonical_hash({'schema_version': bundle['schema_version'], 'currency': bundle['currency'],
                           'assets': sorted(assets, key=lambda asset: asset['id'])})


def passing(result, benchmark, minimum_trades=5):
    return (result['closed_trades'] >= minimum_trades and result['return_pct'] > max(0, benchmark['return_pct']) + 0.1
            and result['max_drawdown_pct'] <= 5 and result['profit_factor'] is not None
            and result['profit_factor'] >= 1.2 and not result['halted'])


def research_scope(bundle):
    return canonical_hash({'assets': sorted(a['id'] for a in bundle['assets']),
                           'currency': bundle['currency'], 'frequency': 'daily'})


def freeze_development(bundle, now):
    count = len(bundle['assets'][0]['bars'])
    if count < 600:
        raise ValueError('insufficient_development_history')
    split = int(count * 0.65)
    training = subset(bundle, 0, split)
    benchmark = simulate(bundle, {'family': 'buy_hold'}, start_index=split, risk_control=False, **costs(bundle))
    trials = []
    for spec in TEMPLATES:
        train = simulate(training, spec, start_index=200, **costs(bundle))
        selection = simulate(bundle, spec, start_index=split, **costs(bundle))
        stress = simulate(bundle, spec, start_index=split, **costs(bundle, True))
        eligible = passing(selection, benchmark) and train['return_pct'] > 0 and stress['return_pct'] > 0
        trials.append({'spec': spec, 'training': compact(train), 'selection': compact(selection),
                       'stress': compact(stress), 'eligible': eligible})
    eligible = [trial for trial in trials if trial['eligible']]
    selected = max(eligible, key=lambda trial: trial['selection']['return_pct'])['spec'] if eligible else None
    return {'scope': research_scope(bundle), 'frozen_at': now.isoformat(),
            'templates_sha256': canonical_hash(TEMPLATES), 'implementation_sha256': implementation_hash(),
            'data_sha256': canonical_hash(bundle), 'selected': selected, 'trials': trials,
            'frozen_history_count': count, 'frozen_history_sha256': frozen_history_hash(bundle, count),
            'selection_benchmark': compact(benchmark), 'quality_verified': quality(bundle),
            'future_holdout_sessions': 126, 'real_money_eligible': False}


def prepare_resume(bundle, db, parent_epoch, now=None, expected_parent_sha256=None):
    """Read-only proposal: only an unselected, unevaluated frozen plan may resume."""
    now = now or datetime.now(timezone.utc)
    data = validate(deepcopy(bundle), now)
    scope = research_scope(data)
    row = db.execute('SELECT * FROM epochs WHERE id=?', (parent_epoch,)).fetchone()
    if not row or row['status'] != 'frozen':
        raise ValueError('frozen_parent_required')
    plan = json.loads(row['plan'])
    fingerprint = canonical_hash({'id': row['id'], 'status': row['status'],
                                  'plan': plan, 'result': json.loads(row['result'])})
    if expected_parent_sha256 is not None and fingerprint != expected_parent_sha256:
        raise ValueError('parent_changed_since_preview')
    if plan.get('selected') is not None or json.loads(row['result']) != {}:
        raise ValueError('unselected_unevaluated_parent_required')
    if plan.get('scope') != scope:
        raise ValueError('resume_scope_mismatch')
    frozen = stamp(plan['frozen_at'])
    if frozen > now:
        raise ValueError('parent_freeze_is_future')
    old_implementation = plan.get('implementation_sha256')
    if not isinstance(old_implementation, str) or not re.fullmatch('[a-f0-9]{64}', old_implementation):
        raise ValueError('invalid_parent_implementation')
    current_implementation = implementation_hash()
    if old_implementation == current_implementation:
        raise ValueError('implementation_unchanged')
    root = db.execute("SELECT status FROM bots WHERE id='root'").fetchone()
    if not root or root['status'] != 'research_only':
        raise ValueError('research_only_root_required')
    proof = plan.get('frozen_history_sha256')
    count = plan.get('frozen_history_count')
    if proof is not None or count is not None:
        if not isinstance(proof, str) or not re.fullmatch('[a-f0-9]{64}', proof):
            raise ValueError('invalid_parent_history_proof')
        if frozen_history_hash(data, count) != proof:
            raise ValueError('parent_frozen_history_changed')
        if any(stamp(bar['close_at']) > frozen for asset in data['assets'] for bar in asset['bars'][:count]):
            raise ValueError('inconsistent_parent_history_cutoff')
        proof_kind = 'frozen_history_sha256'
    else:
        # Legacy 557510a stored a complete bundle hash. Reconstruct exactly that
        # bundle at its original freeze, including all instrument metadata.
        original = {**data, 'assets': [{**asset, 'bars': [bar for bar in asset['bars']
                    if stamp(bar['close_at']) <= frozen]} for asset in data['assets']]}
        if canonical_hash(original) != plan.get('data_sha256'):
            raise ValueError('legacy_frozen_bundle_unverifiable')
        proof_kind = 'legacy_complete_bundle_sha256'
    if len(data['assets'][0]['bars']) < 600:
        raise ValueError('insufficient_development_history')
    consumed = db.execute('SELECT scope,start,end,epoch FROM consumed WHERE scope=? OR epoch=?',
                          (scope, parent_epoch)).fetchall()
    for window in consumed:
        if window['epoch'] == parent_epoch:
            raise ValueError('parent_has_consumed_holdout')
        start, end = stamp(window['start']), stamp(window['end'])
        if start > end or end > now:
            raise ValueError('inconsistent_consumed_window')
    period = scope + ':' + now.strftime('%Y-%m')
    for other in db.execute("SELECT id,status,plan FROM epochs WHERE id LIKE ? AND status IN ('frozen','evaluated')", (scope + ':%',)):
        if other['id'] == parent_epoch:
            continue
        if (other['status'] == 'frozen' and json.loads(other['plan']).get('selected')) or other['id'] == period or other['id'].startswith(period + ':revision:'):
            raise ValueError('competing_research_plan')
    return {'state': 'ready_to_refreeze_development', 'parent_epoch': parent_epoch,
            'expected_parent_sha256': fingerprint, 'scope': scope,
            'previous_implementation_sha256': old_implementation,
            'implementation_sha256': current_implementation, 'history_proof': proof_kind,
            'development_sessions': len(data['assets'][0]['bars']), 'data_sha256': canonical_hash(data),
            'future_holdout_sessions': 126, 'new_freeze_at_preview': now.isoformat(),
            'preserved_consumed_windows': db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],
            'broker_orders_activated': False, 'real_money_eligible': False}


def apply_resume(bundle, registry, parent_epoch, expected_parent_sha256, now=None):
    """Append a revision atomically; never delete old plans, events or windows."""
    if not isinstance(expected_parent_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_parent_sha256):
        raise ValueError('expected_parent_sha256_required')
    fixed_test_time = now is not None
    now = now or datetime.now(timezone.utc)
    registry.db.execute('BEGIN IMMEDIATE')
    try:
        preview = prepare_resume(bundle, registry.db, parent_epoch, now, expected_parent_sha256)
        data = validate(deepcopy(bundle), now)
        plan = freeze_development(data, now)
        frozen_at = now if fixed_test_time else max(now, datetime.now(timezone.utc))
        # The actual freeze follows development computation, including a run
        # crossing a session/month boundary. Preview time never backdates it.
        preview = prepare_resume(bundle, registry.db, parent_epoch, frozen_at, expected_parent_sha256)
        plan['frozen_at'] = frozen_at.isoformat()
        if plan['implementation_sha256'] != preview['implementation_sha256']:
            raise ValueError('implementation_changed_during_resume')
        plan.update(resumes_epoch=parent_epoch, parent_sha256=expected_parent_sha256,
                    previous_implementation_sha256=preview['previous_implementation_sha256'],
                    resume_decision='refreeze_development', parent_history_proof=preview['history_proof'])
        epoch = preview['scope'] + ':' + frozen_at.strftime('%Y-%m') + ':revision:' + canonical_hash(plan)[:16]
        registry.db.execute('INSERT INTO epochs VALUES(?,?,?,?)', (epoch, json.dumps(plan), 'frozen', '{}'))
        registry.db.execute("UPDATE epochs SET status='superseded' WHERE id=?", (parent_epoch,))
        registry.event('research_plan_explicitly_refrozen', {'parent_epoch': parent_epoch, 'epoch': epoch,
                       'parent_sha256': expected_parent_sha256, 'frozen_at': frozen_at.isoformat(),
                       'history_proof': preview['history_proof'], 'data_sha256': plan['data_sha256'],
                       'preserved_consumed_windows': preview['preserved_consumed_windows'],
                       'prior_observations_used_as': 'development_only', 'real_money_eligible': False})
        registry.db.execute('COMMIT')
        return {'state': 'development_refrozen', 'parent_epoch': parent_epoch, 'epoch': epoch,
                'frozen_at': frozen_at.isoformat(), 'selected_candidate': plan['selected'] is not None,
                'future_holdout_sessions': 126, 'preserved_consumed_windows': preview['preserved_consumed_windows'],
                'broker_orders_activated': False, 'real_money_eligible': False}
    except Exception:
        registry.db.execute('ROLLBACK')
        raise


def cycle(bundle, registry, now=None):
    validate(bundle, now)
    now = now or datetime.now(timezone.utc)
    scope = research_scope(bundle)
    epoch_id = scope + ':' + now.strftime('%Y-%m')
    # Keep a selected frozen experiment alive across month boundaries.
    pending = [r for r in registry.db.execute('SELECT * FROM epochs WHERE id LIKE ? AND status=? ORDER BY id', (scope + ':%', 'frozen'))
               if json.loads(r['plan']).get('selected')]
    revisions = registry.db.execute("SELECT * FROM epochs WHERE id LIKE ? AND status IN ('frozen','evaluated') ORDER BY id", (epoch_id + ':revision:%',)).fetchall()
    if len(revisions) > 1:
        raise ValueError('ambiguous_active_research_revision')
    row = pending[0] if pending else (revisions[0] if revisions else registry.db.execute('SELECT * FROM epochs WHERE id=?', (epoch_id,)).fetchone())
    if row:
        epoch_id = row['id']
        if row['status'] == 'superseded':
            return {'state': 'superseded_plan_missing_revision', 'epoch': epoch_id, 'real_money_eligible': False}
    if not row:
        count = len(bundle['assets'][0]['bars'])
        if count < 600:
            return {'state': 'insufficient_development_history', 'sessions': count, 'required': 600, 'real_money_eligible': False}
        plan = freeze_development(bundle, now)
        registry.db.execute('INSERT INTO epochs VALUES(?,?,?,?)', (epoch_id, json.dumps(plan), 'frozen', '{}'))
        registry.event('research_plan_frozen', {'epoch': epoch_id, 'selected': plan['selected'], 'data_sha256': plan['data_sha256']})
    else:
        plan = json.loads(row['plan'])
    if plan['templates_sha256'] != canonical_hash(TEMPLATES) or plan.get('implementation_sha256') != implementation_hash():
        return {'state': 'implementation_changed_new_plan_required', 'epoch': epoch_id, 'real_money_eligible': False}
    if not plan['selected']:
        return {'state': 'no_candidate_passed_development', 'epoch': epoch_id, 'trials': plan['trials'], 'real_money_eligible': False}
    if not plan.get('frozen_history_sha256') or 'frozen_history_count' not in plan:
        return {'state': 'frozen_history_verification_required', 'epoch': epoch_id, 'real_money_eligible': False}
    try:
        unchanged = frozen_history_hash(bundle, plan['frozen_history_count']) == plan['frozen_history_sha256']
    except ValueError:
        unchanged = False
    if not unchanged:
        return {'state': 'frozen_history_changed_new_plan_required', 'epoch': epoch_id, 'real_money_eligible': False}
    frozen = stamp(plan['frozen_at'])
    bars = bundle['assets'][0]['bars']
    indices = [i for i, b in enumerate(bars) if stamp(b['open_at']) > frozen]
    if len(indices) < 126:
        return {'state': 'awaiting_future_holdout', 'epoch': epoch_id, 'received': len(indices), 'required': 126, 'real_money_eligible': False}
    if row and row['status'] == 'evaluated':
        return {'state': 'holdout_already_evaluated', 'epoch': epoch_id, 'result': json.loads(row['result']), 'real_money_eligible': False}
    start, end = indices[0], indices[125] + 1
    registry.consume_holdout(scope, bars[start]['open_at'], bars[end-1]['close_at'], epoch_id)
    window = subset(bundle, 0, end)
    holdout = simulate(window, plan['selected'], start_index=start, **costs(bundle))
    benchmark = simulate(window, {'family': 'buy_hold'}, start_index=start, risk_control=False, **costs(bundle))
    stress = simulate(window, plan['selected'], start_index=start, **costs(bundle, True))
    selected_trial = next(t for t in plan['trials'] if t['spec'] == plan['selected'])
    enough_trades = sum(x['closed_trades'] for x in [selected_trial['training'], selected_trial['selection'], holdout]) >= 30
    approved = plan['quality_verified'] and quality(bundle) and enough_trades and passing(holdout, benchmark) and stress['return_pct'] > 0
    contribution = {}
    for trade in holdout['trades']:
        contribution[trade['asset']] = contribution.get(trade['asset'], 0) + max(0, trade['profit'])
    total_positive = sum(contribution.values())
    concentrated = total_positive > 0 and max(contribution.values()) / total_positive > 0.65
    if len(bundle['assets']) > 1 and concentrated:
        approved = False
    result = {'state': 'paper_candidate_passed' if approved else 'candidate_rejected',
              'holdout': compact(holdout), 'benchmark': compact(benchmark), 'stress': compact(stress),
              'concentration_rejected': concentrated, 'selected_spec': plan['selected'],
              'automatic_live_deployment': False, 'verified_forward': False, 'real_money_eligible': False}
    registry.db.execute('UPDATE epochs SET status=?,result=? WHERE id=?', ('evaluated', json.dumps(result), epoch_id))
    registry.event('holdout_evaluated', {'epoch': epoch_id, **result})
    return {'state': result['state'], 'epoch': epoch_id, 'result': result, 'real_money_eligible': False}
