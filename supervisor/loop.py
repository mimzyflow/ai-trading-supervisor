import os
import subprocess
import sys
import time

REPORT_INTERVAL = int(os.environ.get("REPORT_INTERVAL_SECONDS", "300"))
PUBLISH_INTERVAL = int(os.environ.get("PUBLISH_INTERVAL_SECONDS", "3600"))


def run_report(archive=False):
    env = os.environ.copy()
    env["REPORT_ARCHIVE"] = "1" if archive else "0"
    return subprocess.run(
        [sys.executable, "supervisor/report.py"],
        env=env,
        check=False,
    ).returncode


def publish():
    return subprocess.run(
        [sys.executable, "supervisor/publish_github_issue.py"],
        check=False,
    ).returncode


def main():
    last_publish = 0.0
    while True:
        now = time.monotonic()
        due_publish = not last_publish or (now - last_publish) >= PUBLISH_INTERVAL
        run_report(archive=due_publish)
        if due_publish:
            publish()
            last_publish = now
        time.sleep(max(30, REPORT_INTERVAL))


if __name__ == "__main__":
    main()
