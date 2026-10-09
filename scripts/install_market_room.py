"""Explicit Oracle-only installation of isolated, existing-free-tier research."""
import argparse
import os
import pwd
import subprocess
from pathlib import Path


def bridge_environment(path):
    token = path.read_text().strip()
    if not 24 <= len(token) <= 256 or not token.replace('-', '').replace('_', '').isalnum():
        raise ValueError('existing_jarvis_reasoning_bridge_required')
    return 'MARKET_ROOM_BACKEND=jarvis_bridge\nMARKET_ROOM_BRIDGE_TOKEN=' + token + '\n'


def install(root, activate=False):
    if os.geteuid() != 0 or root != Path('/home/ubuntu/ai-trading-supervisor'):
        raise ValueError('oracle_authorized_install_only')
    # Use the existing reasoning-only gateway: provider credentials, fallback,
    # cooldowns and shared quota accounting stay inside Jarvis.
    environment = bridge_environment(Path('/var/lib/jarvis/secrets/hermes-proxy-token'))
    from urllib.request import Request, build_opener, ProxyHandler
    import json
    token = environment.split('MARKET_ROOM_BRIDGE_TOKEN=', 1)[1].strip()
    request = Request('http://127.0.0.1:20129/v1/models', headers={'Authorization': 'Bearer ' + token})
    with build_opener(ProxyHandler({})).open(request, timeout=10) as response:
        models = json.loads(response.read(4096))
    if not any(item.get('id') == 'jarvis/router-shadow' for item in models.get('data', [])):
        raise ValueError('existing_bridge_unavailable')
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
    print('TradingAgents pinned, isolated, existing Jarvis reasoning gateway; no trading capability. Activated=' + str(activate))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    install(Path('/home/ubuntu/ai-trading-supervisor'), args.activate)
