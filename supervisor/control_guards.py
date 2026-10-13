"""Garde-fous du compte témoin DRY-RUN (simulation uniquement).

Logique pure, sans dépendance Freqtrade, testable isolément. Elle n'est
utilisée que par la stratégie MoussaControlStops ; la politique
market-room-100eur-20261009 et MoussaMarketRoom ne l'importent pas.
"""
import os
from datetime import datetime, timedelta, timezone

CONTROL_POLICY_ID = 'control-stops-20261013'
CONTROL_DB = 'trades-control-stops-20261013.dryrun.sqlite'
DEFAULT_MAX_CONSECUTIVE_LOSSES = 3
DEFAULT_LOSS_PAUSE_HOURS = 24
DEFAULT_PORTFOLIO_LOSS_LIMIT_PCT = 5.0
DEFAULT_POSITION_STOP = -0.03


def _int_env(name, default, low, high):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


def _float_env(name, default, low, high):
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


def settings():
    """Paramètres bornés ; une valeur invalide retombe sur le défaut prudent."""
    return {
        'policy_id': CONTROL_POLICY_ID,
        'max_consecutive_losses': _int_env('CONTROL_MAX_CONSECUTIVE_LOSSES', DEFAULT_MAX_CONSECUTIVE_LOSSES, 1, 20),
        'loss_pause_hours': _float_env('CONTROL_LOSS_PAUSE_HOURS', DEFAULT_LOSS_PAUSE_HOURS, 1, 24 * 14),
        'portfolio_loss_limit_pct': _float_env('CONTROL_PORTFOLIO_LOSS_LIMIT_PCT', DEFAULT_PORTFOLIO_LOSS_LIMIT_PCT, 0.5, 50),
        'position_stop': _float_env('CONTROL_POSITION_STOP', DEFAULT_POSITION_STOP, -0.5, -0.005),
    }


def _aware(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def consecutive_loss_pause(closed, now, max_losses, pause_hours):
    """closed : liste de (close_date, close_profit) des trades clôturés.

    Bloque les nouvelles entrées si les N dernières clôtures sont toutes
    perdantes (profit <= 0) et que la dernière date de moins de pause_hours.
    Retourne (bloqué, raison).
    """
    ordered = sorted(((_aware(d), p) for d, p in closed if d is not None and p is not None),
                     key=lambda item: item[0])
    if len(ordered) < max_losses:
        return False, ''
    recent = ordered[-max_losses:]
    if all(profit <= 0 for _, profit in recent):
        if _aware(now) - recent[-1][0] < timedelta(hours=pause_hours):
            return True, 'consecutive_losses_pause'
    return False, ''


def portfolio_halt(initial, realized_abs, unrealized_abs, limit_pct):
    """Arrêt persistant : perte totale >= limit_pct du capital initial.

    Calculé depuis la base des trades, donc conservé après redémarrage.
    """
    if initial <= 0:
        return True
    return (realized_abs + unrealized_abs) <= -initial * limit_pct / 100.0


def require_simulation(config):
    if config.get('dry_run') is not True or config.get('trading_mode') != 'spot':
        raise ValueError('control_strategy_is_simulation_only')
    exchange = config.get('exchange', {}) or {}
    if exchange.get('key') or exchange.get('secret'):
        raise ValueError('control_strategy_refuses_exchange_credentials')
