import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from .report import atomic_write
except ImportError:
    from report import atomic_write

REPORTS = Path(os.environ.get("REPORTS_DIR", "/app/reports"))


def save_state(state, error=None):
    previous = {}
    try:
        previous = json.loads((REPORTS / "publication.json").read_text())
    except (OSError, ValueError):
        pass
    now = datetime.now(timezone.utc).isoformat()
    payload = {"state": state, "error_code": error, "last_attempt_at": now, "last_success_at": now if state == "ok" else previous.get("last_success_at")}
    atomic_write(REPORTS / "publication.json", json.dumps(payload))


def main():
    token = os.environ.get("GITHUB_STATUS_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "mimzyflow/ai-trading-supervisor").strip()
    issue = os.environ.get("GITHUB_STATUS_ISSUE", "1").strip()
    if not token:
        save_state("not_configured", "missing_token")
        return 3
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not issue.isdigit():
        save_state("failed", "invalid_destination")
        return 4
    try:
        report = json.loads((REPORTS / "latest.json").read_text())
        observed = datetime.fromisoformat(report["observed_at"])
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if not (0 <= age <= 900) or not report.get("api_ok"):
            raise ValueError("unverified_report")
        body = (REPORTS / "latest.md").read_text()
    except (OSError, KeyError, TypeError, ValueError):
        save_state("report_failed", "missing_or_stale_report")
        return 4
    request = urllib.request.Request(
        "https://api.github.com/repos/" + repo + "/issues/" + issue,
        data=json.dumps({"body": body + "\n\nPublication automatique Oracle. Rapport expiré après 15 minutes ; ne pas assimiler cette page à un état en direct."}).encode(),
        method="PATCH", headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json", "User-Agent": "ai-trading-supervisor"},
    )
    try:
        # Redirects must not forward the bearer token.
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError("unexpected_status")
        save_state("ok")
        return 0
    except urllib.error.HTTPError as exc:
        save_state("failed", "http_" + str(exc.code))
    except Exception as exc:
        save_state("failed", type(exc).__name__)
    return 2


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
