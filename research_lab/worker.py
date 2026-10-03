"""Oracle coordinator, every five minutes; bounded daily data/research work."""
import argparse
import json
import os
import subprocess
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from supervisor.api import ReadOnlyAPI
from supervisor.report import atomic_write
from .collect import fetch_crypto
from .data import validate
from .governor import Registry
from .research import cycle


def read_json(path, maximum=8_000_000):
    if path.stat().st_size > maximum:
        raise ValueError('state_or_data_too_large')
    return json.loads(path.read_text())


def read_daily_marker(path, error_prefix, errors):
    try:
        if not path.exists():
            return {}
        marker = read_json(path)
        if not isinstance(marker, dict) or not isinstance(marker.get('day'), str) or not isinstance(marker.get('result'), dict):
            raise ValueError('invalid_daily_marker')
        datetime.strptime(marker['day'], '%Y-%m-%d')
        if not isinstance(marker['result'].get('state'), str):
            raise ValueError('invalid_daily_result')
        return marker
    except Exception as exc:
        # Markers are a cache; the registry remains the authority for one-use
        # holdouts. Recovering this cache never clears evidence or reservations.
        errors.append(error_prefix + '_marker_' + type(exc).__name__)
        return {}


def verified_stop_simulation(decision, runner=subprocess.run, api_factory=ReadOnlyAPI):
    """A fixed Docker stop command, only after independent current DRY-RUN proof."""
    if decision['state'] not in {'paused_risk', 'retired'}:
        return 'not_required'
    inspected = runner(['docker', 'inspect', 'ai-trading-freqtrade'], check=True, capture_output=True, text=True, timeout=8)
    container = json.loads(inspected.stdout)[0]
    env = dict(item.split('=', 1) for item in container['Config']['Env'])
    if env.get('FREQTRADE__DRY_RUN') != 'true' or env.get('FREQTRADE__EXCHANGE__KEY') or env.get('FREQTRADE__EXCHANGE__SECRET'):
        raise ValueError('refuse_stop_unverified_or_live_engine')
    if container.get('State', {}).get('Running') is False:
        return 'already_stopped_data_preserved'
    api = api_factory(url='http://127.0.0.1:8080', username=env.get('FREQTRADE__API_SERVER__USERNAME', ''), password=env.get('FREQTRADE__API_SERVER__PASSWORD', ''))
    cfg = api.get('show_config')
    if cfg.get('dry_run') is not True or cfg.get('trading_mode') != 'spot' or cfg.get('exchange') != 'kraken' or cfg.get('stake_currency') != 'EUR':
        raise ValueError('refuse_stop_unverified_or_live_engine')
    # No API order, withdrawal, liquidation or deletion is made.
    runner(['docker', 'stop', '--time', '15', 'ai-trading-freqtrade'], check=True, capture_output=True, text=True, timeout=30)
    return 'simulation_container_stopped_data_preserved'


def once(root, stop=True, now=None, collector=fetch_crypto):
    now = now or datetime.now(timezone.utc)
    state = root / 'research_state'
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (state / 'worker.lock').open('a')
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return {'state': 'already_running'}
    registry = Registry(state / 'registry.sqlite')
    status = {'schema_version': 1, 'generated_at': now.isoformat(), 'mode': 'RESEARCH_AND_PAPER_ONLY',
              'live_orders_supported': False, 'max_bots': 3, 'max_generation': 2,
              'crypto_research': {}, 'equities': {'state': 'awaiting_broker_data', 'broker_orders_activated': False}, 'errors': []}
    try:
        report_file = root / 'user_data/reports/latest.json'
        try:
            decision = registry.assess(read_json(report_file), now)
            status['risk'] = {**decision, 'observation_verified': True}
        except Exception as exc:
            stored_state = registry.db.execute("SELECT status FROM bots WHERE id='root'").fetchone()[0]
            status['risk'] = {'state': stored_state if stored_state in {'paused_risk', 'retired'} else 'unverified',
                              'observation_verified': False, 'error_type': type(exc).__name__, 'destroy_files': False}
        try:
            # A recorded halt remains in force even when telemetry is down.
            # The stop guard still verifies the current Docker/API DRY-RUN
            # configuration independently before stopping this one container.
            status['risk']['stop_result'] = verified_stop_simulation(status['risk']) if stop else 'read_only_diagnostic'
        except Exception as exc:
            status['risk'].update(stop_result='verification_or_stop_failed', stop_error_type=type(exc).__name__)
            status['errors'].append('risk_stop_' + type(exc).__name__)
        marker_file = state / 'last_daily.json'
        marker = read_daily_marker(marker_file, 'crypto_research', status['errors'])
        if marker.get('day') != now.date().isoformat():
            data_file = state / 'crypto_daily.json'
            try:
                previous = read_json(data_file) if data_file.exists() else None
                bundle = collector(previous=previous, now=now)
                atomic_write(data_file, json.dumps(bundle, ensure_ascii=False, allow_nan=False))
                result = cycle(bundle, registry, now)
                marker = {'day': now.date().isoformat(), 'result': result}
                atomic_write(marker_file, json.dumps(marker, allow_nan=False))
            except Exception as exc:
                status['errors'].append('crypto_research_' + type(exc).__name__)
        status['crypto_research'] = marker.get('result', {'state': 'data_unavailable'})
        equities_file = state / 'equities.bundle.json'
        if equities_file.exists():
            try:
                bundle = validate(read_json(equities_file), now)
                if any(a['asset_class'] not in {'stock', 'etf'} for a in bundle['assets']):
                    raise ValueError('equities_data_scope')
                equity_marker_file = state / 'last_equities.json'
                equity_marker = read_daily_marker(equity_marker_file, 'equities_research', status['errors'])
                if equity_marker.get('day') != now.date().isoformat():
                    equity_marker = {'day': now.date().isoformat(), 'result': cycle(bundle, registry, now)}
                    atomic_write(equity_marker_file, json.dumps(equity_marker, allow_nan=False))
                status['equities'] = {**equity_marker['result'], 'broker_orders_activated': False}
            except Exception as exc:
                status['equities'] = {'state': 'invalid_broker_data', 'error_type': type(exc).__name__, 'broker_orders_activated': False}
        # Factory needs verifiable forward evidence; backtests never satisfy it.
        evidence_file = state / 'forward_growth.json'
        if evidence_file.exists():
            try:
                evidence = read_json(evidence_file)
                status['child_created'] = registry.create_child(evidence['bot_id'], evidence, now)
            except Exception as exc:
                status['factory'] = {'state': 'not_eligible', 'error_type': type(exc).__name__}
        status['bots'] = registry.bots()
        atomic_write(root / 'user_data/reports/autonomy.json', json.dumps(status, ensure_ascii=False, indent=2, allow_nan=False))
        print(json.dumps({k: status[k] for k in ['generated_at', 'mode', 'risk', 'equities', 'errors']}, ensure_ascii=False))
        return status
    finally:
        registry.close()
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--diagnostic-only', action='store_true')
    args = parser.parse_args()
    once(args.root.resolve(), stop=not args.diagnostic_only)


if __name__ == '__main__':
    main()
