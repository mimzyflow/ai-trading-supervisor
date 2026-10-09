"""Run on Oracle only through the authorized deployment command."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def preflight_simulation_compose(compose):
    """Inspect private resolved configuration without emitting credentials."""
    try:
        resolved = run(compose + ['config', '--format', 'json'], capture_output=True, text=True)
        config = json.loads(resolved.stdout)
        environment = config['services']['freqtrade']['environment']
    except Exception:
        raise ValueError('resolved_compose_unavailable') from None
    if not isinstance(environment, dict):
        raise ValueError('resolved_compose_environment_invalid')
    dry_run = environment.get('FREQTRADE__DRY_RUN')
    if dry_run is not True and dry_run != 'true':
        raise ValueError('resolved_compose_requires_dry_run')
    for name in ['FREQTRADE__EXCHANGE__KEY', 'FREQTRADE__EXCHANGE__SECRET']:
        value = environment.get(name)
        if value is not None and value != '':
            raise ValueError('resolved_compose_exchange_credentials_present')


def activate_simulation(compose, arguments):
    preflight_simulation_compose(compose)
    run(compose + ['up'] + arguments)


def risk_halted(root):
    path = root / 'research_state/registry.sqlite'
    if not path.exists():
        return False
    # An unreadable existing registry must stop deployment, never imply consent
    # to resume a halted simulation. Registry and portfolios remain untouched.
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        row = db.execute("SELECT status FROM bots WHERE id='root'").fetchone()
    if not row:
        raise ValueError('risk_registry_missing_root')
    return row[0] in {'paused_risk', 'retired'}


def activate_preserving_risk(compose, arguments, root):
    preflight_simulation_compose(compose)
    if risk_halted(root):
        # Explicit service + no-deps prevents Compose from reviving Freqtrade.
        run(compose + ['up'] + arguments + ['--force-recreate', '--no-deps', 'supervisor'])
        return True
    run(compose + ['up'] + arguments)
    return False


def restore_files(root, backup, files, existed):
    """Restore this release's files without touching secrets or trading data."""
    for relative in files:
        destination = root / relative
        if relative in existed:
            shutil.copy2(backup / relative, destination)
        elif destination.is_file():
            destination.unlink()


def install_research_units(root):
    (root / 'research_state').mkdir(mode=0o700, exist_ok=True)
    for name in ['trading-research.service', 'trading-research.timer']:
        shutil.copy2(root / 'deploy' / name, Path('/etc/systemd/system') / name)
    run(['systemd-analyze', 'verify', '/etc/systemd/system/trading-research.service', '/etc/systemd/system/trading-research.timer'], capture_output=True)
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'trading-research.timer'], capture_output=True)
    # First cycle performs actual public-data research and writes its status.
    run(['systemctl', 'start', 'trading-research.service'], timeout=190)
    run(['systemctl', 'is-active', '--quiet', 'trading-research.timer'])


def install(params):
    root = Path('/home/ubuntu/ai-trading-supervisor')
    archive = Path(params['archive'])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != params['sha256']:
        raise ValueError('release_hash_mismatch')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    releases = Path('/home/ubuntu/trading-releases')
    stage = releases / ('candidate-' + stamp + '-' + params['commit'][:12])
    backup = releases / ('previous-' + stamp)
    stage.mkdir(parents=True)
    backup.mkdir()
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name)
            if parts.is_absolute() or '..' in parts.parts or not (member.isfile() or member.isdir()) or parts.name == '.env' or 'config.private' in member.name:
                raise ValueError('unsafe_archive_member')
        tar.extractall(stage, filter='data')
    run(['python3', 'scripts/check_simulation.py'], cwd=stage)
    run(['python3', '-m', 'unittest', 'discover', '-s', 'tests'], cwd=stage)
    # Resolve the candidate using the existing private project environment before
    # changing active files. A refusal here must never enter activation/rollback.
    candidate_compose = ['docker', 'compose', '--project-directory', str(root), '-f', str(stage / 'docker-compose.yml')]
    preflight_simulation_compose(candidate_compose)
    files = [p.relative_to(stage) for p in stage.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    existed = []
    for relative in files + [Path('build-info.json')]:
        source = root / relative
        if source.is_file():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            existed.append(relative)
    compose = ['docker', 'compose', '--project-directory', str(root), '-f', str(root / 'docker-compose.yml')]
    unit_paths = [Path('/etc/systemd/system') / name for name in ['trading-research.service', 'trading-research.timer']]
    saved_units = {p: p.read_bytes() if p.exists() else None for p in unit_paths}
    timer_previously_enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', 'trading-research.timer'], capture_output=True).returncode == 0
    try:
        for relative in files:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / relative, destination)
        (root / 'build-info.json').write_text(json.dumps({**params, 'deployed_at': datetime.now(timezone.utc).isoformat(), 'backup': str(backup)}, indent=2))
        install_research_units(root)
        run(['docker', 'exec', 'ai-trading-supervisor', 'python', 'supervisor/report.py'], capture_output=True, timeout=45)
        halted = activate_preserving_risk(compose, ['-d', '--wait', '--wait-timeout', '120'], root)
        containers = json.loads(run(['docker', 'inspect', 'ai-trading-freqtrade', 'ai-trading-supervisor'], capture_output=True, text=True).stdout)
        for container in containers:
            if halted and container['Name'] == '/ai-trading-freqtrade':
                if container['State'].get('Running') is not False:
                    raise RuntimeError('risk_halt_not_preserved')
                continue
            if container['State'].get('Health', {}).get('Status') != 'healthy':
                raise RuntimeError('container_not_healthy')
            if container['Name'] == '/ai-trading-freqtrade':
                env = dict(item.split('=', 1) for item in container['Config']['Env'])
                if env.get('FREQTRADE__DRY_RUN') != 'true' or env.get('FREQTRADE__EXCHANGE__KEY') or env.get('FREQTRADE__EXCHANGE__SECRET'):
                    raise RuntimeError('simulation_environment_violation')
        print(json.dumps({'deployment': 'ok', 'commit': params['commit'], 'rollback': str(backup), 'mode': 'DRY-RUN', 'risk_halt_preserved': halted}))
        archive.unlink()
    except Exception:
        subprocess.run(['systemctl', 'stop', 'trading-research.timer', 'trading-research.service'], capture_output=True)
        restore_files(root, backup, files + [Path('build-info.json')], existed)
        for path, previous in saved_units.items():
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(previous)
        subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
        # Restored code still uses the current private environment. Validate it
        # before either the research timer or a container can resume.
        preflight_simulation_compose(compose)
        if timer_previously_enabled:
            subprocess.run(['systemctl', 'enable', '--now', 'trading-research.timer'], capture_output=True)
        else:
            subprocess.run(['systemctl', 'disable', 'trading-research.timer'], capture_output=True)
        activate_preserving_risk(compose, ['-d'], root)
        print(json.dumps({'deployment': 'rolled_back', 'backup': str(backup)}))
        raise


if __name__ == '__main__':
    install(PARAMS)
