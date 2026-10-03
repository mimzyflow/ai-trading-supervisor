"""Check the running engine in its container, without modifying it."""
import base64
import json
import os
import urllib.request


def main():
    try:
        user = os.environ.get("FREQTRADE__API_SERVER__USERNAME", "")
        password = os.environ.get("FREQTRADE__API_SERVER__PASSWORD", "")
        auth = base64.b64encode((user + ":" + password).encode()).decode()
        req = urllib.request.Request("http://127.0.0.1:8080/api/v1/show_config", headers={"Authorization": "Basic " + auth})
        with urllib.request.urlopen(req, timeout=4) as response:
            config = json.load(response)
        return 0 if config.get("dry_run") is True and config.get("state") == "running" and config.get("trading_mode") == "spot" else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
