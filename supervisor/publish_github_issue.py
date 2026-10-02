import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("USER_DATA_DIR", "/app/user_data"))
REPORTS = Path(os.environ.get("REPORTS_DIR", str(ROOT / "reports")))
REPORT = REPORTS / "latest.md"
TOKEN = os.environ.get("GITHUB_STATUS_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPO", "mimzyflow/ai-trading-supervisor").strip()
ISSUE = os.environ.get("GITHUB_STATUS_ISSUE", "1").strip()


def main():
    if not TOKEN:
        print("GitHub status publishing disabled: token missing.")
        return 0
    if not REPORT.exists():
        print("GitHub status publishing skipped: report missing.")
        return 0

    body = REPORT.read_text(encoding="utf-8")
    body += (
        "\n\n---\n"
        "Publication automatique depuis Oracle. "
        "Aucun secret Kraken ne doit apparaître ici."
    )
    payload = json.dumps({"body": body}).encode("utf-8")
    url = f"https://api.github.com/repos/{REPO}/issues/{ISSUE}"
    req = urllib.request.Request(
        url,
        data=payload,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "ai-trading-supervisor",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            print(f"GitHub status updated: HTTP {response.status}")
            return 0
    except urllib.error.HTTPError as exc:
        print(f"GitHub status update failed: HTTP {exc.code}")
        return 2
    except urllib.error.URLError as exc:
        print(f"GitHub status update failed: {exc.reason}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
