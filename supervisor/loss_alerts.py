"""Durable loss notifications. Recording an alert never stops a simulation.

Seuil configurable (défaut 5 %) :
  1. variable d'environnement LOSS_ALERT_THRESHOLD_PCT ;
  2. sinon clé ``loss_alert_threshold_pct`` de la politique ;
  3. sinon 5.0.
Une valeur invalide ou hors bornes [0.5, 50] retombe sur 5.0.
Une alerte est émise chaque fois qu'un nouveau multiple du seuil est franchi
(5, 10, 15 ... % avec le défaut). Action toujours ``notify_only`` : ce module
n'arrête, ne met en pause et ne modifie aucun bot.
"""
import json
import logging
import math
import os
try:
    from .report import atomic_write
except ImportError:
    from report import atomic_write

DEFAULT_THRESHOLD_PCT = 5.0
THRESHOLD_ENV = 'LOSS_ALERT_THRESHOLD_PCT'
THRESHOLD_POLICY_KEY = 'loss_alert_threshold_pct'
MIN_THRESHOLD_PCT = 0.5
MAX_THRESHOLD_PCT = 50.0

log = logging.getLogger('supervisor.loss_alerts')


def _valid(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not MIN_THRESHOLD_PCT <= value <= MAX_THRESHOLD_PCT:
        return None
    return value


def threshold_pct(policy=None, environ=None):
    environ = os.environ if environ is None else environ
    raw = environ.get(THRESHOLD_ENV)
    if raw not in (None, ''):
        value = _valid(raw)
        return value if value is not None else DEFAULT_THRESHOLD_PCT
    if isinstance(policy, dict) and policy.get(THRESHOLD_POLICY_KEY) is not None:
        value = _valid(policy.get(THRESHOLD_POLICY_KEY))
        return value if value is not None else DEFAULT_THRESHOLD_PCT
    return DEFAULT_THRESHOLD_PCT


def crossed_level(loss_pct, step):
    """Plus grand multiple de ``step`` atteint par ``loss_pct`` (0 si aucun)."""
    loss_pct = min(100., max(0., loss_pct))
    level = math.floor(loss_pct / step + 1e-9) * step
    return round(level, 4)


def update(report, reports, now, policy):
    path = reports / 'loss-alerts.json'
    if path.exists():
        ledger = json.loads(path.read_text())
        if not isinstance(ledger.get('events'), list) or not isinstance(ledger.get('seen'), dict):
            raise ValueError('invalid_loss_alert_ledger')
    else:
        ledger = {'schema_version':1, 'seen':{}, 'events':[]}
    step = threshold_pct(policy)
    paper = report.get('research', {}).get('equity_paper', {})
    values = {'crypto':report.get('equity_eur') if report.get('api_ok') and report.get('database_ok') else None,
              'equities':paper.get('equity_eur') if paper.get('policy_id') == policy['id'] else None}
    for desk, equity in values.items():
        if isinstance(equity, bool) or not isinstance(equity, (float,int)):
            continue
        loss = max(0., (100-equity))
        key = policy['id'] + ':' + desk
        crossed = crossed_level(loss, step)
        if crossed == int(crossed):
            crossed = int(crossed)
        previous = ledger['seen'].get(key, 0)
        if crossed > previous:
            event = {'policy_id':policy['id'], 'desk':desk, 'observed_at':now.isoformat(),
                     'loss_level_pct':crossed, 'threshold_pct':step,
                     'equity_eur':round(equity,4), 'action':'notify_only'}
            ledger['events'].append(event)
            ledger['seen'][key] = crossed
            log.warning('loss_alert policy=%s desk=%s loss_level_pct=%s threshold_pct=%s equity_eur=%.4f action=notify_only',
                        policy['id'], desk, crossed, step, equity)
    atomic_write(path, json.dumps(ledger, allow_nan=False))
    return [event for event in ledger['events'] if event.get('policy_id') == policy['id']][-12:]
