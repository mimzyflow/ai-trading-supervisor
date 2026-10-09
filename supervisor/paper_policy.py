"""User-authorized paper policy and bounded advisory inputs. No broker API."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

POLICY_ID = 'market-room-100eur-20261009'
CRYPTO_DB = 'trades-market-room-100eur-20261009.dryrun.sqlite'
PIN = '1394a3f72aa4393e1a98f51b382434c4b4c2d972'


def read_policy(root=None):
    path = (Path(root) / 'simulation-policy.json' if root is not None else
            Path(os.environ.get('SIMULATION_POLICY_FILE', str(Path(__file__).resolve().parents[1] / 'simulation-policy.json'))))
    if not path.exists():
        return None
    if path.stat().st_size > 4096:
        raise ValueError('invalid_simulation_policy')
    value = json.loads(path.read_text())
    if (value.get('schema_version') != 1 or value.get('id') != POLICY_ID or value.get('mode') != 'SIMULATION_ONLY'
            or value.get('active') is not True or value.get('initial_eur_per_bot') != 100
            or value.get('portfolio_loss_limit_pct') is not None or value.get('position_loss_stops') is not False
            or value.get('ai_influence') is not True or value.get('real_money_eligible') is not False):
        raise ValueError('invalid_simulation_policy')
    authorized = datetime.fromisoformat(value['authorized_at'])
    if authorized.tzinfo is None or authorized > datetime.now(timezone.utc):
        raise ValueError('invalid_policy_authorization_time')
    return value


def advice(reports, desk, now=None, policy=None):
    now = now or datetime.now(timezone.utc)
    default = {'state': 'fallback', 'rating': 'REVIEW', 'stake_multiplier': 1.0,
               'allow_entry': True, 'exit': False, 'id': None, 'as_of': None}
    try:
        policy = policy or read_policy()
        if not policy:
            return default
        path = Path(reports) / 'tradingagents.json'
        if path.stat().st_size > 20000:
            return default
        raw = json.loads(path.read_text())
        generated = datetime.fromisoformat(raw['generated_at'])
        if (raw.get('schema_version') != 1 or generated.tzinfo is None or not 0 <= (now-generated).total_seconds() <= 36*3600
                or raw.get('policy_id') != policy['id'] or raw.get('upstream_commit') != PIN
                or raw.get('can_trade') is not False or raw.get('budget_eur') != 0):
            return default
        for item in raw.get('analyses', [])[:2]:
            if item.get('ticker') != desk or item.get('state') != 'complete':
                continue
            stamp = datetime.fromisoformat(item['as_of'])
            if (stamp.tzinfo is None or stamp < datetime.fromisoformat(policy['authorized_at'])
                    or not 0 <= (now-stamp).total_seconds() <= 36*3600):
                continue
            rating = item.get('rating')
            multipliers = {'Buy': 2.0, 'Overweight': 1.5, 'Hold': 1.0, 'Underweight': .5, 'Sell': 0.0}
            if rating not in multipliers:
                continue
            return {'state': 'applied', 'rating': rating, 'stake_multiplier': multipliers[rating],
                    'allow_entry': rating != 'Sell', 'exit': rating == 'Sell', 'as_of': item['as_of'],
                    'id': hashlib.sha256((raw['generated_at']+desk+rating).encode()).hexdigest()[:20]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return default
