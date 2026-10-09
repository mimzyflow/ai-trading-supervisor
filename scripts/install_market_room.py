"""Explicit Oracle-only installation of isolated, existing-free-tier research."""
import argparse
import os
import pwd
import shlex
import subprocess
from pathlib import Path


def provider_environment(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if '=' not in line or line.startswith('#'):
            continue
        key, raw = line.split('=', 1)
        if key in {'GEMINI_FREE_TIER_VERIFIED', 'GEMINI_API_KEY'}:
            tokens = shlex.split(raw, comments=True)
            if len(tokens) != 1:
                raise ValueError('invalid_existing_free_provider')
            values[key] = tokens[0]
    key = values.get('GEMINI_API_KEY', '')
    if values.get('GEMINI_FREE_TIER_VERIFIED') != '1' or not key or not key.replace('-', '').replace('_', '').isalnum():
        raise ValueError('existing_verified_free_gemini_required')
    return 'GEMINI_FREE_TIER_VERIFIED=1\nGOOGLE_API_KEY=' + key + '\n'


def install(root, activate=False):
    if os.geteuid() != 0 or root != Path('/home/ubuntu/ai-trading-supervisor'):
        raise ValueError('oracle_authorized_install_only')
    # Fail before package/network operations if the existing account isn't
    # explicitly marked free. No other Jarvis secret is copied or displayed.
    environment = provider_environment(Path('/opt/jarvis/.env'))
    runtime = root / '.runtime/tradingagents'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    python = runtime / 'venv/bin/python'
    if not python.exists():
        subprocess.run(['/usr/bin/python3', '-m', 'venv', str(runtime / 'venv')], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '--only-binary=:all:',
                    '-r', str(root / 'integrations/tradingagents-requirements.txt')], check=True)
    subprocess.run([str(python), '-c', 'from integrations.tradingagents_runner import verify_package; verify_package()'], cwd=root, check=True)
    account = pwd.getpwnam('ubuntu')
    for path in [runtime] + list(runtime.rglob('*')):
        os.chown(path, account.pw_uid, account.pw_gid)
    private = runtime / 'free-provider.env'
    fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(environment)
    os.chmod(private, 0o600)
    os.chown(private, account.pw_uid, account.pw_gid)
    # Python environments and provider settings remain private runtime files.
    for name in ['trading-market-room.service', 'trading-market-room.timer']:
        (Path('/etc/systemd/system') / name).write_bytes((root / 'deploy' / name).read_bytes())
    subprocess.run(['systemd-analyze', 'verify', '/etc/systemd/system/trading-market-room.service',
                    '/etc/systemd/system/trading-market-room.timer'], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    if activate:
        subprocess.run(['systemctl', 'enable', '--now', 'trading-market-room.timer'], check=True)
        subprocess.run(['systemctl', 'start', '--no-block', 'trading-market-room.service'], check=True)
    print('TradingAgents pinned, isolated, existing free provider; no trading capability. Activated=' + str(activate))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    install(Path('/home/ubuntu/ai-trading-supervisor'), args.activate)
