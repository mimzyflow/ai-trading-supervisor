import json
import math
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from .api import ReadOnlyAPI, TelemetryError
    from .market_room import build as build_room, render as render_room
    from .paper_policy import read_policy, advice
except ImportError:
    from api import ReadOnlyAPI, TelemetryError
    from market_room import build as build_room, render as render_room
    from paper_policy import read_policy, advice

ROOT = Path(os.environ.get("USER_DATA_DIR", "/app/user_data"))
RUNTIME = Path(os.environ.get("RUNTIME_DIR", str(ROOT)))
DB = RUNTIME / os.environ.get('FREQTRADE_DB_NAME', 'tradesv3.dryrun.sqlite')
LOG = RUNTIME / "freqtrade.log"
REPORTS = Path(os.environ.get("REPORTS_DIR", str(ROOT / "reports")))
JARVIS_REPORT_FILE = os.environ.get("JARVIS_REPORT_FILE", "").strip()
V2_DEPLOYED_AT = "2026-10-05T15:03:00+00:00"


def utcnow():
    return datetime.now(timezone.utc)


def number(value):
    if isinstance(value, bool):
        raise ValueError("boolean_not_number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non_finite_number")
    return result


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix="." + path.name + ".", delete=False) as file:
            temp = Path(file.name)
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()


def read_publication():
    try:
        value = json.loads((REPORTS / "publication.json").read_text())
        return {k: value.get(k) for k in ["state", "last_attempt_at", "last_success_at", "error_code"]}
    except (OSError, ValueError, TypeError):
        return {"state": "not_configured" if not os.environ.get("GITHUB_STATUS_TOKEN", "").strip() else "pending"}


def metric(value, count=False):
    try:
        value = number(value)
        if count and (value < 0 or not value.is_integer()):
            return None
        return int(value) if count else round(value, 4)
    except (ValueError, TypeError, OverflowError):
        return None


def status_code(value, fallback='unknown'):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_:-]{1,80}', value) else fallback


def paper_metrics(value):
    if not isinstance(value, dict) or value.get('mode') != 'BROKERLESS_PAPER' or value.get('real_money_eligible') is not False:
        return {'state': 'unavailable'}
    result = {'state': status_code(value.get('state')), 'mode': 'BROKERLESS_PAPER',
              'currency': 'USD', 'real_money_eligible': False}
    for key in ['equity', 'return_pct', 'cash', 'profit_factor', 'max_drawdown_pct', 'win_rate_pct', 'expectancy']:
        result[key] = metric(value.get(key))
    for key in ['open_positions', 'closed_trades', 'wins', 'losses']:
        result[key] = metric(value.get(key), count=True)
    try:
        parsed = datetime.fromisoformat(value['last_session'].replace('Z', '+00:00'))
        result['last_session'] = parsed.isoformat() if parsed.tzinfo else None
    except (KeyError, ValueError, TypeError, AttributeError):
        result['last_session'] = None
    session = result.get('last_session')
    market_age = (utcnow() - datetime.fromisoformat(session)).total_seconds() if session else None
    if value.get('state') not in {'paper_active', 'paper_halted'} or market_age is None or not 0 <= market_age <= 96 * 3600:
        for key in ['equity', 'return_pct', 'cash', 'profit_factor', 'max_drawdown_pct', 'win_rate_pct', 'expectancy', 'open_positions', 'closed_trades', 'wins', 'losses']:
            result[key] = None
    result['halt_reason'] = status_code(value.get('halt_reason'), '')
    result['blocked_reason'] = status_code(value.get('blocked_reason'), '')
    result['execution_revision'] = status_code(value.get('execution_revision'), '')
    if value.get('initial_eur') == 100:
        result.update(initial_eur=100, equity_eur=metric(value.get('equity_eur')),
                      return_eur_pct=metric(value.get('return_eur_pct')), funding_usd=metric(value.get('funding_usd')),
                      fx_usd_per_eur=metric(value.get('fx_usd_per_eur')), fx_date=value.get('fx_date'),
                      funding_fx_date=value.get('funding_fx_date'), policy_id=status_code(value.get('policy_id')),
                      loss_limit_pct=None, position_loss_stops=False)
        if result.get('equity') is None:
            result.update(equity_eur=None, return_eur_pct=None)
    return result


ACCOUNT_DB_PATTERN = re.compile(r'[A-Za-z0-9._-]{1,120}\.sqlite')
ACCOUNT_ID_PATTERN = re.compile(r'[A-Za-z0-9_:-]{1,80}')
MAX_EXTRA_ACCOUNTS = 5


def account_policy_id():
    """policy_id explicite (ACCOUNT_POLICY_ID) sinon politique active lue en lecture seule."""
    explicit = os.environ.get('ACCOUNT_POLICY_ID', '').strip()
    if explicit:
        return status_code(explicit, None)
    try:
        policy = read_policy()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return status_code(policy.get('id'), None) if policy else None


def trade_stats(conn):
    """Statistiques de l'expérience courante depuis une base Freqtrade (lecture seule).

    Les colonnes absentes (anciennes bases, tests) donnent None, jamais zéro inventé.
    """
    columns = {row[1] for row in conn.execute('PRAGMA table_info(trades)')}
    closed = conn.execute(
        """SELECT COUNT(*),
                  SUM(CASE WHEN close_profit>0 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN close_profit<=0 THEN 1 ELSE 0 END),
                  COALESCE(SUM(close_profit_abs),0),
                  COALESCE(SUM(CASE WHEN close_profit_abs>0 THEN close_profit_abs ELSE 0 END),0),
                  COALESCE(-SUM(CASE WHEN close_profit_abs<0 THEN close_profit_abs ELSE 0 END),0),
                  MAX(close_date)
           FROM trades WHERE is_open=0""").fetchone()
    result = {
        'closed_trades': closed[0] or 0, 'wins': closed[1] or 0, 'losses': closed[2] or 0,
        'realized_profit_eur': round(number(closed[3]), 4),
        'profit_factor': round(number(closed[4]) / number(closed[5]), 4) if number(closed[5]) > 0 else None,
        'last_close_date': str(closed[6])[:40] if closed[6] else None,
        'first_open_date': None, 'fees_paid_eur': None,
    }
    if 'open_date' in columns:
        first = conn.execute('SELECT MIN(open_date) FROM trades').fetchone()[0]
        result['first_open_date'] = str(first)[:40] if first else None
    if {'fee_open', 'fee_close', 'open_rate', 'close_rate', 'amount'} <= columns:
        fees = conn.execute(
            """SELECT COALESCE(SUM(COALESCE(fee_open,0)*COALESCE(open_rate,0)*COALESCE(amount,0)
                                + CASE WHEN is_open=0 THEN COALESCE(fee_close,0)*COALESCE(close_rate,0)*COALESCE(amount,0) ELSE 0 END),0)
               FROM trades""").fetchone()[0]
        result['fees_paid_eur'] = round(number(fees), 4)
    return result


def read_account(path, account_id):
    """Compte supplémentaire (ex. témoin DRY-RUN) lu uniquement depuis sa base, sans API."""
    item = {'account_id': account_id, 'database': path.name, 'database_found': path.is_file(), 'database_ok': False}
    if not item['database_found']:
        return item
    try:
        conn = sqlite3.connect('file:' + quote(str(path.resolve()), safe='/') + '?mode=ro', uri=True, timeout=2)
        try:
            item.update(trade_stats(conn))
            item['database_ok'] = True
        finally:
            conn.close()
    except (sqlite3.Error, OSError, TypeError, ValueError):
        item['database_ok'] = False
    return item


def extra_accounts():
    """EXTRA_ACCOUNTS='[{"account_id":"control-stops-20261013","db":"trades-control-stops-20261013.dryrun.sqlite"}]'.

    Noms de fichiers simples uniquement, résolus sous RUNTIME ; entrée invalide ignorée.
    """
    try:
        raw = json.loads(os.environ.get('EXTRA_ACCOUNTS', '') or '[]')
    except ValueError:
        return []
    accounts = []
    if not isinstance(raw, list):
        return accounts
    for entry in raw[:MAX_EXTRA_ACCOUNTS]:
        if not isinstance(entry, dict):
            continue
        name, account_id = entry.get('db'), entry.get('account_id')
        if not (isinstance(name, str) and ACCOUNT_DB_PATTERN.fullmatch(name)
                and isinstance(account_id, str) and ACCOUNT_ID_PATTERN.fullmatch(account_id)):
            continue
        if name == DB.name:
            continue
        accounts.append(read_account(RUNTIME / name, account_id))
    return accounts


def read_research():
    path = REPORTS / 'autonomy.json'
    try:
        if path.stat().st_size > 65536:
            return {'state': 'invalid'}
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get('generated_at'), str):
            raise ValueError('invalid_research_status')
        if any(not isinstance(raw.get(key, {}), dict) for key in ['risk', 'crypto_research', 'equities', 'v3_challengers', 'freqai_shadow']):
            raise ValueError('invalid_research_sections')
        observed = datetime.fromisoformat(raw['generated_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError('research_time_without_timezone')
        age = (utcnow() - observed).total_seconds()
        if raw.get('schema_version') != 1 or not 0 <= age <= 900:
            return {'state': 'stale'}
        equities = raw.get('equities', {})
        shadows = equities.get('v3_shadow', {})
        shadows = {name: paper_metrics(value) for name, value in list(shadows.items())[:3]
                   if name in {'regime_momentum', 'triple_barrier', 'slow_breakout'}} if isinstance(shadows, dict) else {}
        v3 = raw.get('v3_challengers', {})
        challengers = v3.get('challengers', {})
        results = {}
        if isinstance(challengers, dict):
            for name, value in list(challengers.items())[:3]:
                if name not in {'regime_momentum', 'triple_barrier', 'slow_breakout'} or not isinstance(value, dict):
                    continue
                result, gate = value.get('result', {}), value.get('gate', {})
                if not isinstance(result, dict) or not isinstance(gate, dict):
                    continue
                reasons = gate.get('reasons', [])
                results[name] = {key: metric(result.get(key), count=key == 'closed_trades')
                                 for key in ['return_pct', 'profit_factor', 'max_drawdown_pct', 'closed_trades']}
                results[name].update(state=status_code(gate.get('state')),
                                     reasons=[status_code(x) for x in reasons[:12]] if isinstance(reasons, list) else [])
        errors = raw.get('errors', [])
        risk = raw.get('risk', {})
        risk_control = {key: status_code(risk.get(key)) for key in ['state', 'reason', 'stop_result']}
        risk_control['recorded_at'] = risk.get('recorded_at') if isinstance(risk.get('recorded_at'), str) and len(risk['recorded_at']) <= 64 else None
        risk_control['last_verified_equity_eur'] = metric(risk.get('last_verified_equity_eur'))
        return {'state': 'current', 'observed_at': raw['generated_at'],
                'risk_control': risk_control,
                'risk': str(raw.get('risk', {}).get('state', 'unknown'))[:48],
                'crypto': str(raw.get('crypto_research', {}).get('state', 'unknown'))[:64],
                'v3_crypto': str(raw.get('v3_challengers', {}).get('state', 'unknown'))[:64],
                'freqai_shadow': str(raw.get('freqai_shadow', {}).get('state', 'unknown'))[:64],
                'equities': str(raw.get('equities', {}).get('state', 'unknown'))[:64],
                'equity_paper': paper_metrics(equities.get('paper')),
                'equity_control': paper_metrics(equities.get('control')),
                'equity_v3': shadows, 'v3_results': results,
                'v3_observed_at': str(v3.get('observed_at') or '')[:64],
                'sessions': metric(equities.get('sessions'), count=True),
                'required': metric(equities.get('required'), count=True),
                'errors': [status_code(x) for x in errors[:10]] if isinstance(errors, list) else [],
                'broker_orders_activated': False, 'max_bots': 3, 'real_money_eligible': False}
    except (OSError, ValueError, KeyError, TypeError):
        return {'state': 'unavailable', 'broker_orders_activated': False}


def collect(api=None):
    now = utcnow()
    initial = number(os.environ.get("SIMULATION_START_BALANCE_EUR", "100"))
    data = {
        "schema_version": 2, "generated_at": now.isoformat(), "observed_at": None,
        "max_age_seconds": 900, "mode": "UNKNOWN", "state": "unknown", "healthy": False,
        "strategy": "unknown", "strategy_validation_state": os.environ.get("STRATEGY_VALIDATION_STATE", "research_only")[:40],
        "database_found": DB.is_file(), "database_ok": False, "api_ok": False, "configuration_safe": False,
        "log_age_minutes": round((now.timestamp() - LOG.stat().st_mtime) / 60, 1) if LOG.is_file() else None,
        "total_trades": None, "open_trades": None, "closed_trades": None,
        "realized_profit_eur": None, "unrealized_profit_eur": None, "total_profit_eur": None,
        "equity_eur": None, "starting_balance_eur": initial, "total_return_pct": None,
        "committed_capital_eur": None, "estimated_stop_risk_eur": None,
        "observed_max_drawdown_pct": None, "wins": None, "losses": None,
        "last_trades": [], "alerts": [], "activity_note": "", "publication": read_publication(),
        "research": read_research(),
        "v2": {
            "deployed_at": V2_DEPLOYED_AT,
            "baseline_history_excluded": True,
            "closed_trades": None, "wins": None, "losses": None,
            "realized_profit_eur": None, "profit_factor": None,
        },
        "current_experiment": {
            "account_id": DB.name.removesuffix(".sqlite"), "database": DB.name,
            "policy_id": account_policy_id(), "strategy": os.environ.get("ACTIVE_STRATEGY", "unknown")[:80],
            "first_open_date": None, "last_close_date": None, "closed_trades": None,
            "wins": None, "losses": None, "realized_profit_eur": None,
            "profit_factor": None, "fees_paid_eur": None,
        },
    }
    if not data["database_found"]:
        data["alerts"].append("Base Freqtrade absente : statistiques indisponibles.")
    else:
        try:
            conn = sqlite3.connect("file:" + quote(str(DB.resolve()), safe="/") + "?mode=ro", uri=True, timeout=2)
            try:
                counts = conn.execute("SELECT COUNT(*), SUM(CASE WHEN is_open=1 THEN 1 ELSE 0 END), SUM(CASE WHEN is_open=0 THEN 1 ELSE 0 END) FROM trades").fetchone()
                data.update(total_trades=counts[0], open_trades=counts[1] or 0, closed_trades=counts[2] or 0)
                result = conn.execute("SELECT COALESCE(SUM(close_profit_abs),0), SUM(CASE WHEN close_profit>0 THEN 1 ELSE 0 END), SUM(CASE WHEN close_profit<=0 THEN 1 ELSE 0 END) FROM trades WHERE is_open=0").fetchone()
                data.update(realized_profit_eur=round(number(result[0]), 4), wins=result[1] or 0, losses=result[2] or 0)
                v2 = conn.execute(
                    """SELECT COUNT(*),
                              SUM(CASE WHEN close_profit>0 THEN 1 ELSE 0 END),
                              SUM(CASE WHEN close_profit<=0 THEN 1 ELSE 0 END),
                              COALESCE(SUM(close_profit_abs),0),
                              COALESCE(SUM(CASE WHEN close_profit_abs>0 THEN close_profit_abs ELSE 0 END),0),
                              COALESCE(-SUM(CASE WHEN close_profit_abs<0 THEN close_profit_abs ELSE 0 END),0)
                       FROM trades
                       WHERE is_open=0 AND datetime(close_date) >= datetime(?)""",
                    (V2_DEPLOYED_AT,),
                ).fetchone()
                data["v2"].update(
                    closed_trades=v2[0] or 0,
                    wins=v2[1] or 0,
                    losses=v2[2] or 0,
                    realized_profit_eur=round(number(v2[3]), 4),
                    profit_factor=round(number(v2[4]) / number(v2[5]), 4) if number(v2[5]) > 0 else None,
                )
                rows = conn.execute("SELECT pair,close_profit,close_profit_abs,close_date,exit_reason FROM trades WHERE is_open=0 ORDER BY id DESC LIMIT 5").fetchall()
                data["last_trades"] = [dict(zip(["pair", "close_profit", "close_profit_abs", "close_date", "exit_reason"], row)) for row in rows]
                for trade in data["last_trades"]:
                    trade["close_profit_pct"] = round(number(trade["close_profit"]) * 100, 2)
                data["current_experiment"].update(trade_stats(conn))
                data["database_ok"] = True
            finally:
                conn.close()
        except (sqlite3.Error, OSError, TypeError, ValueError):
            data.update(total_trades=None, open_trades=None, closed_trades=None, realized_profit_eur=None, wins=None, losses=None, last_trades=[])
            data["alerts"].append("Lecture de la base impossible : ne pas interpréter les statistiques comme zéro.")
    try:
        snapshot = (api or ReadOnlyAPI()).snapshot()
        config, balance, profit, positions = [snapshot[k] for k in ["show_config", "balance", "profit", "status"]]
        if not isinstance(config.get("dry_run"), bool):
            raise ValueError("mode_missing")
        data["mode"] = "DRY-RUN" if config["dry_run"] else "LIVE"
        data["engine_state"] = str(config.get("state", "unknown"))[:40]
        data["strategy"] = str(config.get("strategy", "unknown"))[:80]
        data["engine_version"] = str(config.get("version", "unknown"))[:40]
        data["timeframe"] = str(config.get("timeframe", "unknown"))[:12]
        if data["mode"] != "DRY-RUN":
            data["alerts"].append("CRITIQUE : moteur en mode réel inattendu. Aucune action financière exécutée par le superviseur.")
        scope_ok = config.get("trading_mode") == "spot" and config.get("exchange") == "kraken" and config.get("stake_currency") == "EUR"
        no_loss_stops = config.get('strategy') == 'MoussaMarketRoom' and read_policy() is not None
        stop_ok = number(config.get('stoploss')) == -1 if no_loss_stops else -1 < number(config.get('stoploss')) < 0
        limits_ok = number(config.get("max_open_trades")) == -1 and 0 < number(config.get("stake_amount")) <= 20 and not config.get("force_entry_enable") and stop_ok
        data["configuration_safe"] = scope_ok and limits_ok and data["mode"] == "DRY-RUN"
        if not scope_ok:
            data["alerts"].append("Configuration différente du périmètre Kraken spot EUR autorisé.")
        if not limits_ok:
            data["alerts"].append("Limites de simulation non conformes : vérifier la configuration.")
        total, closed = number(profit["profit_all_coin"]), number(profit["profit_closed_coin"])
        data.update(equity_eur=round(number(balance["total"]), 4), total_profit_eur=round(total, 4), unrealized_profit_eur=round(total - closed, 4), total_return_pct=round(total / initial * 100, 4))
        data["committed_capital_eur"] = round(sum(number(t["stake_amount"]) for t in positions), 4)
        data["estimated_stop_risk_eur"] = None if no_loss_stops else round(data["committed_capital_eur"] * abs(number(config["stoploss"])), 4)
        if no_loss_stops:
            data['v2'].update(closed_trades=None,wins=None,losses=None,realized_profit_eur=None,profit_factor=None)
            data['execution_revision'] = 'market_room_no_loss_stops_v1'
        if data["database_ok"] and (int(profit["trade_count"]) != data["total_trades"] or int(profit["closed_trade_count"]) != data["closed_trades"] or abs(closed - data["realized_profit_eur"]) > 0.01):
            data["alerts"].append("Statistiques API/base divergentes : revérifier avant interprétation.")
        if data["engine_state"] != "running":
            data["alerts"].append("Moteur Freqtrade non actif : " + data["engine_state"])
        data["api_ok"] = True
        data["observed_at"] = now.isoformat()
        data["state"] = "active" if data["engine_state"] == "running" and data["configuration_safe"] else "degraded"
        previous = {}
        try:
            previous = json.loads((REPORTS / "latest.json").read_text())
        except (OSError, ValueError):
            pass
        comparable = previous.get("mode") == data["mode"] and previous.get("strategy") == data["strategy"] and previous.get("starting_balance_eur") == initial
        peak = max(initial, data["equity_eur"], number(previous.get("equity_peak_eur", initial)) if comparable else initial)
        drawdown = max(0.0, (peak - data["equity_eur"]) / peak * 100)
        data["equity_peak_eur"] = round(peak, 4)
        data["observed_max_drawdown_pct"] = round(max(drawdown, number(previous.get("observed_max_drawdown_pct", 0) or 0) if comparable else 0), 4)
    except (TelemetryError, KeyError, TypeError, ValueError, ZeroDivisionError):
        data["api_ok"] = False
        data["observed_at"] = None
        data["state"] = "unknown"
        data["alerts"].append("Télémétrie du moteur indisponible ou invalide : état non vérifié.")
    if data["log_age_minutes"] is None or data["log_age_minutes"] > 20:
        data["alerts"].append("Journal Freqtrade absent ou ancien : vérifier le moteur.")
    if data["publication"].get("state") in {"failed", "report_failed"}:
        data["alerts"].append("Publication GitHub : " + str(data["publication"]["state"]) + ". Les rapports locaux restent la source de télémétrie.")
    if data['research'].get('errors'):
        data['alerts'].append('Recherche : ' + ', '.join(data['research']['errors']))
    data["healthy"] = data["api_ok"] and data["database_ok"] and data["configuration_safe"] and not data["alerts"]
    if data["api_ok"] and data["database_ok"] and data["total_trades"] == 0 and data["state"] == "active":
        data["activity_note"] = "Bot actif, en attente d'un signal d'entrée conforme à la stratégie."
    data['accounts'] = extra_accounts()
    data['market_room'] = build_room(data, REPORTS, now)
    execution = data['market_room'].get('simulation_execution')
    if execution:
        try:
            try:
                from .loss_alerts import update
            except ImportError:
                from loss_alerts import update
            events = update(data, REPORTS, now, read_policy())
            data['market_room']['loss_alerts'] = events
            for event in events:
                if event['observed_at'] == now.isoformat():
                    data['alerts'].append('Perte simulée ' + event['desk'] + ' : seuil ' + str(event['loss_level_pct']) + ' %, surveillance sans arrêt.')
        except (ValueError,OSError,KeyError,TypeError):
            data['alerts'].append('Journal des alertes de pertes indisponible : surveillance à vérifier.')
    return data


def display(value, digits=2):
    return "indisponible" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))


def render(data):
    lines = ["# Rapport Freqtrade", "", f"- Généré : {data['generated_at']}", f"- Observation moteur : {data.get('observed_at') or 'non vérifiée'}", f"- Validité : {data.get('max_age_seconds', 900)} secondes ; au-delà, état inconnu.", f"- Mode vérifié : **{data['mode']}**", f"- État : **{data['state']}**", f"- Stratégie : **{data['strategy']}** ({data['strategy_validation_state']})"]
    for label, key in [("Trades ouverts", "open_trades"), ("Trades clôturés", "closed_trades"), ("Valeur simulée EUR", "equity_eur"), ("P/L réalisé EUR", "realized_profit_eur"), ("P/L latent net estimé EUR", "unrealized_profit_eur"), ("P/L total EUR", "total_profit_eur"), ("Rendement sur portefeuille initial %", "total_return_pct"), ("Capital engagé EUR", "committed_capital_eur"), ("Risque théorique au stop, hors frais/glissement EUR", "estimated_stop_risk_eur"), ("Baisse maximale observée depuis suivi %", "observed_max_drawdown_pct")]:
        lines.append("- " + label + " : " + display(data.get(key)))
    current = data.get("current_experiment", {})
    lines += ["", "## Expérience courante", "- Compte : " + str(current.get("account_id") or "inconnu") + " (" + str(current.get("database") or "?") + ")",
              "- Politique : " + str(current.get("policy_id") or "aucune"),
              "- Premier trade ouvert : " + display(current.get("first_open_date")) + " ; dernière clôture : " + display(current.get("last_close_date")),
              "- Profit factor : " + display(current.get("profit_factor")) + " ; frais estimés EUR : " + display(current.get("fees_paid_eur"))]
    for account in data.get("accounts", []):
        lines.append("- Compte supplémentaire " + str(account.get("account_id")) + " : " + display(account.get("closed_trades")) + " clôtures, P/L réalisé EUR " + display(account.get("realized_profit_eur")) + ", PF " + display(account.get("profit_factor")))
    v2 = data.get("v2", {})
    lines += ["", "## Performance prospective V2 uniquement",
              "- Frontière : " + str(v2.get("deployed_at", "inconnue")),
              "- Ancienne MoussaBaseline exclue : " + ("oui" if v2.get("baseline_history_excluded") else "non"),
              "- Trades clôturés V2 : " + display(v2.get("closed_trades")),
              "- P/L réalisé V2 EUR : " + display(v2.get("realized_profit_eur")),
              "- Profit factor V2 : " + display(v2.get("profit_factor"))]
    lines += ["", "## Publication GitHub", "- État : " + str(data.get("publication", {}).get("state", "unknown")), "", "## Alertes"]
    lines += ["- " + str(a) for a in data["alerts"]] or ["- Aucune alerte détectée."]
    if data.get("activity_note"):
        lines += ["", data["activity_note"]]
    lines += ["", "## Derniers trades simulés"]
    for trade in data.get("last_trades", []):
        lines.append("- " + str(trade.get("pair", "?")) + " : " + display(trade.get("close_profit_pct")) + "% | " + str(trade.get("exit_reason", "?")))
    if not data.get("last_trades"):
        lines.append("- Aucun trade clôturé disponible.")
    research = data.get('research', {})
    lines += ['', '## Recherche autonome et actions/ETF', '- Télémétrie : ' + str(research.get('state', 'unknown')),
              '- Recherche crypto : ' + str(research.get('crypto', 'indisponible')),
              '- Actions/ETF : ' + str(research.get('equities', 'indisponible')),
              '- Ordres courtier activés : non. Réel éligible : non.']
    paper = research.get('equity_paper', {})
    lines += ['', '### ' + ('Actions IA : 100 EUR financés en USD fictifs' if paper.get('initial_eur') == 100 else 'Actions prospectives V2 (USD fictifs)'),
              '- État : ' + str(paper.get('state', 'unavailable')),
              '- Dernière séance traitée : ' + str(paper.get('last_session') or 'indisponible')]
    for label, key in [('Valeur USD', 'equity'), ('Rendement %', 'return_pct'), ('Cash USD', 'cash'),
                       ('Positions ouvertes', 'open_positions'), ('Trades clôturés', 'closed_trades'),
                       ('Baisse maximale %', 'max_drawdown_pct')]:
        lines.append('- ' + label + ' : ' + display(paper.get(key)))
    if paper.get('closed_trades') == 0:
        lines.append('- Zéro transaction : aucune efficacité démontrée.')
    control = research.get('equity_control', {})
    if control:
        lines.append('- Ancien témoin conservé : ' + display(control.get('equity')) + ' USD, ' + display(control.get('closed_trades')) + ' clôture(s).')
    lines += ['', '### Crypto V3 : recherche historique',
              '- Calcul source : ' + str(research.get('v3_observed_at') or 'indisponible'),
              '- Décision : ' + str(research.get('v3_crypto', 'unavailable')),
              '| Variante | Rendement % | Profit factor | Baisse max % | Clôtures | Décision |',
              '| --- | ---: | ---: | ---: | ---: | --- |']
    for name, result in research.get('v3_results', {}).items():
        lines.append('| ' + name + ' | ' + ' | '.join(display(result.get(k)) for k in ['return_pct', 'profit_factor', 'max_drawdown_pct', 'closed_trades']) + ' | ' + str(result.get('state', 'unknown')) + ' |')
    for name, result in research.get('v3_results', {}).items():
        if result.get('reasons'):
            lines.append('\nRefus ' + name + ' : ' + ', '.join(result['reasons']) + '.\n')
    lines += ['', '### Actions V3 : portefeuilles prospectifs séparés']
    for name, shadow in research.get('equity_v3', {}).items():
        lines.append('- ' + name + ' : ' + display(shadow.get('equity')) + ' USD, ' + display(shadow.get('closed_trades')) + ' clôture(s), état ' + str(shadow.get('state', 'unknown')) + '.')
    if research.get('sessions') is not None:
        lines.append('- Historique actions : ' + display(research['sessions']) + ' séances / ' + display(research.get('required')) + ' requises.')
    if research.get('errors'):
        lines.append('- Erreurs worker : ' + ', '.join(research['errors']))
    risk = research.get('risk_control', {})
    if risk.get('state') in {'paused_risk', 'retired'}:
        lines += ['', '## Arrêt de risque conservé', '- État : ' + risk['state'],
                  '- Motif : ' + str(risk.get('reason')), '- Décision enregistrée : ' + str(risk.get('recorded_at')),
                  '- Dernière valeur vérifiée lors de cet arrêt, pas une valeur actuelle : ' + display(risk.get('last_verified_equity_eur')) + ' EUR.',
                  '- Une reprise nécessite une décision humaine distincte.']
    if data.get('market_room'):
        lines += ['', render_room(data['market_room'])]
    lines += ["", "> Supervision en lecture seule. Les résultats simulés ne constituent pas une validation de rentabilité."]
    return "\n".join(lines) + "\n"


def main():
    data = collect()
    markdown = render(data)
    payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    atomic_write(REPORTS / "latest.md", markdown)
    atomic_write(REPORTS / "latest.json", payload)
    atomic_write(REPORTS / 'market-room.md', render_room(data['market_room']))
    if JARVIS_REPORT_FILE:
        atomic_write(Path(JARVIS_REPORT_FILE), payload)
        ai_file = REPORTS / 'tradingagents.json'
        # General telemetry excludes model prose. A separate, fixed private
        # file supports an authenticated plain-text advisory report in Jarvis.
        if data['market_room']['ai']['state'] == 'current' and ai_file.stat().st_size <= 20000:
            atomic_write(Path(JARVIS_REPORT_FILE).parent / 'room-analysis.json', ai_file.read_text())
    if os.environ.get("REPORT_ARCHIVE", "1") == "1":
        atomic_write(REPORTS / (utcnow().strftime("%Y%m%d-%H%M") + ".md"), markdown)
    print(markdown)


if __name__ == "__main__":
    main()
