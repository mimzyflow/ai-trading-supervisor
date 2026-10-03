import os
import subprocess
import sys
import time

try:
    from .publish_github_issue import save_state
except ImportError:
    from publish_github_issue import save_state

REPORT_INTERVAL = max(30, int(os.environ.get("REPORT_INTERVAL_SECONDS", "300")))
PUBLISH_INTERVAL = max(60, int(os.environ.get("PUBLISH_INTERVAL_SECONDS", "3600")))


def run(command, env=None):
    try:
        return subprocess.run([sys.executable, command], env=env, check=False, timeout=45).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 124


def run_report(archive=False):
    env = os.environ.copy()
    env["REPORT_ARCHIVE"] = "1" if archive else "0"
    return run("supervisor/report.py", env)


def publish():
    return run("supervisor/publish_github_issue.py")


class Schedule:
    def __init__(self):
        self.last_archive = None
        self.next_publish = 0.0
        self.retry_seconds = 60

    def tick(self, now, report=run_report, publisher=publish):
        archive = self.last_archive is None or now - self.last_archive >= PUBLISH_INTERVAL
        if report(archive) != 0:
            save_state("report_failed", "report_process_failed")
            return False
        if archive:
            self.last_archive = now
        if now >= self.next_publish:
            code = publisher()
            if code == 0:
                self.next_publish = now + PUBLISH_INTERVAL
                self.retry_seconds = 60
            elif code == 3:
                self.next_publish = now + PUBLISH_INTERVAL
            else:
                if code == 124:
                    save_state("failed", "publisher_timeout")
                self.next_publish = now + self.retry_seconds
                self.retry_seconds = min(600, self.retry_seconds * 2)
            # Publish status is visible immediately, even when publishing failed.
            report(False)
        return True


def main():
    schedule = Schedule()
    while True:
        schedule.tick(time.monotonic())
        time.sleep(REPORT_INTERVAL)


if __name__ == "__main__":
    main()
