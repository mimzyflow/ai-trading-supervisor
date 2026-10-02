import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("USER_DATA_DIR", "/app/user_data"))
DB = ROOT / "tradesv3.dryrun.sqlite"
LOG = ROOT / "logs" / "freqtrade.log"
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)


def utcnow():
    return datetime.now(timezone.utc)


def db_columns(conn, table):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def scalar(conn, sql, default=0):
    try:
        row = conn.execute(sql).fetchone()
        return row[0] if row and row[0] is not None else default
    except sqlite3.Error:
        return default


def log_age_minutes():
    if not LOG.exists():
        return None
    age = utcnow().timestamp() - LOG.stat().st_mtime
    return round(age / 60, 1)


def collect():
    data = {
        "generated_at": utcnow().isoformat(),
        "mode": "DRY-RUN",
        "database_found": DB.exists(),
        "log_age_minutes": log_age_minutes(),
        "total_trades": 0,
        "open_trades": 0,
        "closed_trades": 0,
        "realized_profit_eur": 0.0,
        "wins": 0,
        "losses": 0,
        "last_trades": [],
        "alerts": [],
    }
    if not DB.exists():
        data["alerts"].append("Base Freqtrade absente: bot pas encore initialisé.")
        return data

    conn = sqlite3.connect(DB)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "trades" not in tables:
            data["alerts"].append("Table trades absente.")
            return data
        cols = db_columns(conn, "trades")
        data["total_trades"] = scalar(conn, "SELECT COUNT(*) FROM trades")
        if "is_open" in cols:
            data["open_trades"] = scalar(
                conn, "SELECT COUNT(*) FROM trades WHERE is_open = 1"
            )
            data["closed_trades"] = scalar(
                conn, "SELECT COUNT(*) FROM trades WHERE is_open = 0"
            )
        if "close_profit_abs" in cols:
            data["realized_profit_eur"] = round(float(scalar(
                conn,
                "SELECT COALESCE(SUM(close_profit_abs),0) FROM trades "
                "WHERE is_open = 0",
            )), 4)
        if "close_profit" in cols:
            data["wins"] = scalar(
                conn, "SELECT COUNT(*) FROM trades "
                "WHERE is_open = 0 AND close_profit > 0"
            )
            data["losses"] = scalar(
                conn, "SELECT COUNT(*) FROM trades "
                "WHERE is_open = 0 AND close_profit <= 0"
            )
        wanted = [c for c in [
            "pair", "close_profit", "close_profit_abs", "close_date", "exit_reason"
        ] if c in cols]
        if wanted and "is_open" in cols:
            sql = (
                f"SELECT {','.join(wanted)} FROM trades "
                "WHERE is_open = 0 ORDER BY id DESC LIMIT 5"
            )
            for row in conn.execute(sql):
                item = dict(zip(wanted, row))
                if item.get("close_profit") is not None:
                    item["close_profit_pct"] = round(
                        float(item["close_profit"]) * 100, 2
                    )
                data["last_trades"].append(item)
    finally:
        conn.close()

    age = data["log_age_minutes"]
    if age is None:
        data["alerts"].append("Journal Freqtrade absent.")
    elif age > 20:
        data["alerts"].append(
            f"Journal Freqtrade ancien ({age} min): vérifier le conteneur."
        )
    return data


def render(data):
    nclosed = data["closed_trades"]
    winrate = (data["wins"] / nclosed * 100) if nclosed else 0
    lines = [
        "# Rapport horaire Freqtrade",
        "",
        f"- Généré: {data['generated_at']}",
        f"- Mode: **{data['mode']}**",
        f"- Trades ouverts: {data['open_trades']}",
        f"- Trades clôturés: {nclosed}",
        f"- P/L réalisé simulé: {data['realized_profit_eur']:.2f} EUR",
        f"- Taux de trades gagnants: {winrate:.1f}%",
        f"- Âge du dernier log: {data['log_age_minutes']} min",
        "",
        "## Alertes",
    ]
    if data["alerts"]:
        lines += [f"- {a}" for a in data["alerts"]]
    else:
        lines.append("- Aucune alerte technique détectée.")
    lines += ["", "## Derniers trades simulés"]
    if not data["last_trades"]:
        lines.append("- Aucun trade clôturé pour le moment.")
    else:
        for t in data["last_trades"]:
            pair = t.get("pair", "?")
            pct = t.get("close_profit_pct", 0)
            reason = t.get("exit_reason", "?")
            lines.append(f"- {pair}: {pct:+.2f}% | sortie: {reason}")
    lines += [
        "",
        "> Ce rapport décrit le fonctionnement du bot et ses résultats simulés. "
        "Il ne déclenche aucune décision financière.",
    ]
    return "\n".join(lines) + "\n"


def main():
    data = collect()
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    markdown = render(data)
    (REPORTS / "latest.md").write_text(markdown, encoding="utf-8")
    (REPORTS / "latest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORTS / f"{stamp}.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
