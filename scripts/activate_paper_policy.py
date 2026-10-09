"""Record this human-authorized experiment; never erase prior accounts."""
import json
from datetime import datetime, timezone
from supervisor.paper_policy import read_policy, CRYPTO_DB
from supervisor.report import atomic_write


def activate(root):
    policy = read_policy(root)
    if not policy:
        return None
    config = json.loads((root / 'user_data/config.dryrun.json').read_text())
    if (config.get('dry_run') is not True or config.get('trading_mode') != 'spot'
            or config.get('dry_run_wallet') != 100 or config.get('strategy') != 'MoussaMarketRoom'
            or any(config.get('exchange', {}).get(key) for key in ['key','secret'])):
        raise ValueError('paper_policy_requires_verified_simulation')
    from research_lab.governor import Registry
    registry = Registry(root / 'research_state/registry.sqlite')
    try:
        registry.db.execute('BEGIN IMMEDIATE')
        row = registry.db.execute("SELECT status,spec FROM bots WHERE id='root'").fetchone()
        before = {'status': row['status'], 'spec': row['spec']}
        spec = json.loads(row['spec'])
        if spec.get('paper_policy_id') == policy['id']:
            registry.db.execute('COMMIT')
            return None
        payload = {'policy_id': policy['id'], 'recorded_at': datetime.now(timezone.utc).isoformat(),
                   'initial_eur_per_bot':100, 'old_crypto_database_preserved':'tradesv3.dryrun.sqlite',
                   'crypto_database':CRYPTO_DB, 'loss_limit_pct':None, 'position_loss_stops':False,
                   'previous_root_status':row['status'], 'mode':'SIMULATION_ONLY'}
        spec['paper_policy_id'] = policy['id']
        registry.db.execute("UPDATE bots SET status='research_only',spec=? WHERE id='root'",(json.dumps(spec),))
        registry.event('human_authorized_paper_experiment', payload)
        registry.db.execute('COMMIT')
        atomic_write(root / 'research_state/paper-policy-activation.json', json.dumps(payload))
        return before
    except Exception:
        if registry.db.in_transaction:
            registry.db.execute('ROLLBACK')
        raise
    finally:
        registry.close()


def rollback(root, previous):
    if previous is None:
        return
    from research_lab.governor import Registry
    registry = Registry(root / 'research_state/registry.sqlite')
    try:
        registry.db.execute('BEGIN IMMEDIATE')
        registry.db.execute("UPDATE bots SET status=?,spec=? WHERE id='root'",(previous['status'],previous['spec']))
        registry.event('paper_experiment_activation_rolled_back', {'previous_status':previous['status'], 'data_preserved':True})
        registry.db.execute('COMMIT')
    finally:
        registry.close()
