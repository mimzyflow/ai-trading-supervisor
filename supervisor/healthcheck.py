import json
import os
from datetime import datetime, timezone
from pathlib import Path


def check(report, now=None):
    try:
        now = now or datetime.now(timezone.utc)
        research = report.get('research', {})
        risk = research.get('risk_control', {})
        if risk.get('state') in {'paused_risk', 'retired'} and risk.get('stop_result') in {'already_stopped_data_preserved', 'simulation_container_stopped_data_preserved'}:
            age = (now - datetime.fromisoformat(research['observed_at'])).total_seconds()
            return research.get('state') == 'current' and 0 <= age <= 900
        observed = datetime.fromisoformat(report["observed_at"])
        age = (now - observed).total_seconds()
        return 0 <= age <= 900 and report.get("api_ok") is True and report.get("database_ok") is True and report.get("configuration_safe") is True and report.get("mode") == "DRY-RUN" and report.get("state") == "active"
    except (ValueError, TypeError, KeyError):
        return False


def main():
    try:
        report = json.loads((Path(os.environ.get("REPORTS_DIR", "/app/reports")) / "latest.json").read_text())
        return 0 if check(report) else 1
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
