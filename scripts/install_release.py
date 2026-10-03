"""Run on Oracle only through the authorized deployment command."""
import hashlib
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def restore_files(root, backup, files, existed):
    """Restore this release's files without touching secrets or trading data."""
    for relative in files:
        destination = root / relative
        if relative in existed:
            shutil.copy2(backup / relative, destination)
        elif destination.is_file():
            destination.unlink()


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
    try:
        for relative in files:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / relative, destination)
        (root / 'build-info.json').write_text(json.dumps({**params, 'deployed_at': datetime.now(timezone.utc).isoformat(), 'backup': str(backup)}, indent=2))
        # Suppress resolved config: it includes UI credentials.
        run(compose + ['config', '--quiet'], stdout=subprocess.DEVNULL)
        run(compose + ['up', '-d', '--wait', '--wait-timeout', '120'])
        containers = json.loads(run(['docker', 'inspect', 'ai-trading-freqtrade', 'ai-trading-supervisor'], capture_output=True, text=True).stdout)
        for container in containers:
            if container['State'].get('Health', {}).get('Status') != 'healthy':
                raise RuntimeError('container_not_healthy')
            if container['Name'] == '/ai-trading-freqtrade':
                env = dict(item.split('=', 1) for item in container['Config']['Env'])
                if env.get('FREQTRADE__DRY_RUN') != 'true' or env.get('FREQTRADE__EXCHANGE__KEY') or env.get('FREQTRADE__EXCHANGE__SECRET'):
                    raise RuntimeError('simulation_environment_violation')
        print(json.dumps({'deployment': 'ok', 'commit': params['commit'], 'rollback': str(backup), 'mode': 'DRY-RUN'}))
        archive.unlink()
    except Exception:
        restore_files(root, backup, files + [Path('build-info.json')], existed)
        run(compose + ['up', '-d'])
        print(json.dumps({'deployment': 'rolled_back', 'backup': str(backup)}))
        raise


if __name__ == '__main__':
    install(PARAMS)
