"""Deploy only committed simulation code, with preflight and rollback."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def call(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def main():
    if call(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
        raise RuntimeError("Commit and validate the source before deployment.")
    call(["python3", "scripts/check_simulation.py"], cwd=ROOT)
    call(["python3", "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT)
    commit = call(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    host = os.environ.get("ORACLE_HOST") or call(["sh", "scripts/oracle-ssh-target.sh"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    key = os.environ.get("ORACLE_KEY", str(Path.home() / ".ssh/jarvis-oracle.key"))
    ssh = ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8", host]
    files = call(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    forbidden = [name for name in files if Path(name).name == ".env" or name.endswith((".sqlite", ".pem", ".key")) or "config.private" in name]
    if forbidden:
        raise RuntimeError("Sensitive tracked paths are not deployable.")
    with tempfile.TemporaryDirectory(prefix="trading-release-") as folder:
        archive = Path(folder) / "release.tar.gz"
        call(["git", "archive", "--format=tar.gz", "--output=" + str(archive), "HEAD"], cwd=ROOT)
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        incoming = "/home/ubuntu/trading-release-" + commit[:12] + ".tar.gz"
        call(["scp", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", str(archive), host + ":" + incoming])
        # Values are serialized into Python, never interpolated into shell code.
        payload = {"commit": commit, "sha256": sha, "archive": incoming}
        remote = "PARAMS = " + repr(payload) + "\n" + (ROOT / "scripts/install_release.py").read_text()
        call(ssh + ["sudo -n python3 -"], input=remote, text=True, timeout=240)


if __name__ == "__main__":
    main()
