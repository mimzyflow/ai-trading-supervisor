import json
import math
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from .api import ReadOnlyAPI, TelemetryError
except ImportError:
    from api import ReadOnlyAPI, TelemetryError

ROOT = Path(os.environ.get("USER_DATA_DIR", "/app/user_data"))
RUNTIME = Path(os.environ.get("RUNTIME_DIR", str(ROOT)))
DB = RUNTIME / "tradesv3.dryrun.sqlite"
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


def read_research():
    path = REPORTS / 'autonomy.json'
    try:
        if path.stat().st_size > 65536:
            return {'state': 'invalid'}
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get('generated_at'), str):
            raise ValueError('invalid_research_status')
        if any(not isinstance(raw.get(key, {}), dict) for key in ['risk', 'crypto_research', 'equities']):
            raise ValueError('invalid_research_sections')
        observed = datetime.fromisoformat(raw['generated_at'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError('research_time_without_timezone')
        age = (utcnow() - observed).total_seconds()
        if raw.get('schema_version') != 1 or not 0 <= age <= 900:
            return {'state': 'stale'}
        shadows = {}
        for name, value in list(raw.get('equities', {}).get('v3_shadow', {}).items())[:3]:
            if isinstance(value, dict):
                shadows[str(name)[:40]] = {
                    'equity': value.get('equity'),
                    'return_pct': value.get('return_pct'),
                    'open_positions': value.get('open_positions'),
                    'closed_trades': value.get('closed_trades'),
                    'max_drawdown_pct': value.get('max_drawdown_pct'),
                }
        return {'state': 'current', 'observed_at': raw['generated_at'],
                'risk': str(raw.get('risk', {}).get('state', 'unknown'))[:48],
                'crypto': str(raw.get('crypto_research', {}).get('state', 'unknown'))[:64],
                'v3_crypto': str(raw.get('v3_challengers', {}).get('state', 'unknown'))[:64],
                'freqai_shadow': str(raw.get('freqai_shadow', {}).get('state', 'unknown'))[:64],
                'equities': str(raw.get('equities', {}).get('state', 'unknown'))[:64],
                'equity_v3': shadows,
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
        limits_ok = number(config.get("max_open_trades")) == -1 and 0 < number(config.get("stake_amount")) <= 20 and not config.get("force_entry_enable") and -1 < number(config.get("stoploss")) < 0
        data["configuration_safe"] = scope_ok and limits_ok and data["mode"] == "DRY-RUN"
        if not scope_ok:
            data["alerts"].append("Configuration différente du périmètre Kraken spot EUR autorisé.")
        if not limits_ok:
            data["alerts"].append("Limites de simulation non conformes : vérifier la configuration.")
        total, closed = number(profit["profit_all_coin"]), number(profit["profit_closed_coin"])
        data.update(equity_eur=round(number(balance["total"]), 4), total_profit_eur=round(total, 4), unrealized_profit_eur=round(total - closed, 4), total_return_pct=round(total / initial * 100, 4))
        data["committed_capital_eur"] = round(sum(number(t["stake_amount"]) for t in positions), 4)
        data["estimated_stop_risk_eur"] = round(data["committed_capital_eur"] * abs(number(config["stoploss"])), 4)
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
    if data["publication"].get("state") in {"not_configured", "failed", "report_failed"}:
        data["alerts"].append("Publication GitHub : " + str(data["publication"]["state"]) + ". Les rapports locaux restent la source de télémétrie.")
    data["healthy"] = data["api_ok"] and data["database_ok"] and data["configuration_safe"] and not data["alerts"]
    if data["api_ok"] and data["database_ok"] and data["total_trades"] == 0 and data["state"] == "active":
        data["activity_note"] = "Bot actif, en attente d'un signal d'entrée conforme à la stratégie."
    return data


def display(value, digits=2):
    return "indisponible" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))


def render(data):
    lines = ["# Rapport Freqtrade", "", f"- Généré : {data['generated_at']}", f"- Observation moteur : {data.get('observed_at') or 'non vérifiée'}", f"- Validité : {data.get('max_age_seconds', 900)} secondes ; au-delà, état inconnu.", f"- Mode vérifié : **{data['mode']}**", f"- État : **{data['state']}**", f"- Stratégie : **{data['strategy']}** ({data['strategy_validation_state']})"]
    for label, key in [("Trades ouverts", "open_trades"), ("Trades clôturés", "closed_trades"), ("Valeur simulée EUR", "equity_eur"), ("P/L réalisé EUR", "realized_profit_eur"), ("P/L latent net estimé EUR", "unrealized_profit_eur"), ("P/L total EUR", "total_profit_eur"), ("Rendement sur portefeuille initial %", "total_return_pct"), ("Capital engagé EUR", "committed_capital_eur"), ("Risque théorique au stop, hors frais/glissement EUR", "estimated_stop_risk_eur"), ("Baisse maximale observée depuis suivi %", "observed_max_drawdown_pct")]:
        lines.append("- " + label + " : " + display(data.get(key)))
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
    lines += ["", "> Supervision en lecture seule. Les résultats simulés ne constituent pas une validation de rentabilité."]
    return "\n".join(lines) + "\n"


def main():
    data = collect()
    markdown = render(data)
    payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    atomic_write(REPORTS / "latest.md", markdown)
    atomic_write(REPORTS / "latest.json", payload)
    if JARVIS_REPORT_FILE:
        atomic_write(Path(JARVIS_REPORT_FILE), payload)
    if os.environ.get("REPORT_ARCHIVE", "1") == "1":
        atomic_write(REPORTS / (utcnow().strftime("%Y%m%d-%H%M") + ".md"), markdown)
    print(markdown)


if __name__ == "__main__":
    main()
