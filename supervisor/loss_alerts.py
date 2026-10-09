"""Durable loss notifications. Recording an alert never stops a simulation."""
import json
from .report import atomic_write


def update(report, reports, now, policy):
    path = reports / 'loss-alerts.json'
    if path.exists():
        ledger = json.loads(path.read_text())
        if not isinstance(ledger.get('events'), list) or not isinstance(ledger.get('seen'), dict):
            raise ValueError('invalid_loss_alert_ledger')
    else:
        ledger = {'schema_version':1, 'seen':{}, 'events':[]}
    paper = report.get('research', {}).get('equity_paper', {})
    values = {'crypto':report.get('equity_eur') if report.get('api_ok') and report.get('database_ok') else None,
              'equities':paper.get('equity_eur') if paper.get('policy_id') == policy['id'] else None}
    for desk, equity in values.items():
        if isinstance(equity, bool) or not isinstance(equity, (float,int)):
            continue
        loss = max(0., (100-equity))
        key = policy['id'] + ':' + desk
        crossed = int(min(100., loss) // 5) * 5
        previous = ledger['seen'].get(key, 0)
        if crossed > previous:
            event = {'policy_id':policy['id'], 'desk':desk, 'observed_at':now.isoformat(),
                     'loss_level_pct':crossed, 'equity_eur':round(equity,4), 'action':'notify_only'}
            ledger['events'].append(event)
            ledger['seen'][key] = crossed
    atomic_write(path, json.dumps(ledger, allow_nan=False))
    return [event for event in ledger['events'] if event.get('policy_id') == policy['id']][-12:]
