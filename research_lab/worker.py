"""Oracle coordinator, every five minutes; bounded daily data/research work."""
import argparse
import json
import os
import subprocess
import fcntl
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from supervisor.api import ReadOnlyAPI
from supervisor.report import atomic_write
from .collect import fetch_crypto_broad
from .data import validate, stamp, canonical_hash
from .governor import Registry
from .research import cycle, research_scope
from .equity_paper import load as load_equity_paper, advance as advance_equity_paper, save as save_equity_paper, summary as equity_paper_summary, new_state
from .fx import collect as collect_fx
from supervisor.paper_policy import read_policy, advice
from supervisor.market_context import market_features
from .engine import TEMPLATES
from .v3_challengers import CHALLENGERS, evaluate as evaluate_v3_challengers
from .freqai_shadow import status as freqai_shadow_status


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


def daily_cycle_required(marker, registry, now):
    if marker.get('day') != now.date().isoformat():
        return True
    epoch = marker.get('result', {}).get('epoch')
    if epoch is not None and (not isinstance(epoch, str) or len(epoch) > 160):
        return True
    row = registry.db.execute('SELECT status FROM epochs WHERE id=?', (epoch,)).fetchone() if epoch else None
    return row is not None and row['status'] == 'superseded'


def v3_implementation_hash():
    package = Path(__file__).resolve().parent
    names = ['engine.py', 'v3_challengers.py', 'robustness.py', 'research.py']
    return hashlib.sha256(b''.join((package / name).read_bytes() for name in names)).hexdigest()


def v3_data_signature(bundle):
    # These are the simulator's inputs, including asset order (cash allocation
    # depends on it). Refreshed discovery/provenance metadata is not market data.
    return {'data_sha256': canonical_hash({key: bundle[key]
                                          for key in ['schema_version', 'currency', 'assets']}),
            'scope': research_scope(bundle)}


def archive_v3_marker(path, previous):
    # Research computed with older code/data is evidence, never overwritten.
    if previous:
        payload = json.dumps(previous, ensure_ascii=False, sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        archived = path.parent / 'archive' / ('v3-' + digest + '.json')
        if not archived.exists():
            atomic_write(archived, payload)


def replace_v3_marker(path, previous, current):
    archive_v3_marker(path, previous)
    atomic_write(path, json.dumps(current, ensure_ascii=False, allow_nan=False))


def current_equity_bundle(state, now):
    collection = read_json(state / 'equity_collection.json')
    age = (now - stamp(collection['observed_at'])).total_seconds()
    if collection.get('state') != 'current' or not 0 <= age <= 900:
        raise ValueError('equity_collection_unavailable')
    bundle = read_json(state / 'equities.bundle.json')
    if stamp(bundle['observed_at']) != stamp(collection['observed_at']):
        raise ValueError('equity_collection_bundle_mismatch')
    bundle = validate(bundle, now)
    # Weekends/holidays are allowed; a freshly downloaded obsolete chart is not.
    market_age = (now - stamp(bundle['assets'][0]['bars'][-1]['close_at'])).total_seconds()
    if not 0 <= market_age <= 96 * 3600:
        raise ValueError('equity_market_data_stale')
    return bundle


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


def once(root, stop=True, now=None, collector=fetch_crypto_broad):
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
    policy = read_policy(root)
    status = {'schema_version': 1, 'generated_at': now.isoformat(), 'mode': 'RESEARCH_AND_PAPER_ONLY',
              'live_orders_supported': False, 'max_bots': 3, 'max_generation': 2,
              'crypto_research': {}, 'v3_challengers': {},
              'freqai_shadow': freqai_shadow_status(),
              'equities': {'state': 'awaiting_broker_data', 'broker_orders_activated': False}, 'errors': []}
    contexts = {'crypto': [], 'equities': []}
    try:
        report_file = root / 'user_data/reports/latest.json'
        try:
            decision = registry.assess(read_json(report_file), now, loss_limit=None if policy else .05)
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
        # A durable stop is a decision, not an API outage. Preserve the last
        # verified risk checkpoint independently of the now-stopped engine.
        event = registry.db.execute("SELECT at,payload FROM events WHERE type='risk_state' ORDER BY id DESC LIMIT 1").fetchone()
        if event and status['risk']['state'] in {'paused_risk', 'retired'}:
            checkpoint = json.loads(event['payload'])
            status['risk'].update(recorded_at=event['at'], reason=checkpoint.get('reason'),
                                  last_verified_equity_eur=checkpoint.get('equity'))
        marker_file = state / 'last_daily.json'
        marker = read_daily_marker(marker_file, 'crypto_research', status['errors'])
        if daily_cycle_required(marker, registry, now):
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
        v3_marker_file = state / 'last_v3_challengers.json'
        v3_marker = read_daily_marker(v3_marker_file, 'v3_challengers', status['errors'])
        v3_hash = v3_implementation_hash()
        v3_signature, v3_cache_matches = None, False
        try:
            data_file = state / 'crypto_daily.json'
            v3_bundle = validate(read_json(data_file), now)
            contexts['crypto'] = market_features(v3_bundle, now)
            v3_signature = v3_data_signature(v3_bundle)
            v3_cache_matches = (v3_marker.get('implementation_sha256') == v3_hash
                                and all(v3_marker.get(key) == value for key, value in v3_signature.items()))
            if daily_cycle_required(v3_marker, registry, now) or not v3_cache_matches:
                archive_v3_marker(v3_marker_file, v3_marker)
                result = evaluate_v3_challengers(v3_bundle, now)
                result.update(v3_signature)
                updated_marker = {'day': now.date().isoformat(), 'implementation_sha256': v3_hash,
                                  **v3_signature, 'result': result}
                replace_v3_marker(v3_marker_file, v3_marker, updated_marker)
                v3_marker = updated_marker
                v3_cache_matches = True
        except Exception as exc:
            status['errors'].append('v3_challengers_' + type(exc).__name__)
        status['v3_challengers'] = v3_marker.get('result', {'state': 'data_unavailable'})
        if not v3_cache_matches:
            reason = ('implementation_changed_recalculation_required'
                      if v3_marker.get('implementation_sha256') != v3_hash
                      else ('data_changed_recalculation_required' if v3_signature else 'data_unavailable'))
            status['v3_challengers'] = {'state': reason}
        equities_file = state / 'equities.bundle.json'
        if equities_file.exists():
            try:
                bundle = current_equity_bundle(state, now)
                contexts['equities'] = market_features(bundle, now)
                if any(a['asset_class'] not in {'stock', 'etf'} for a in bundle['assets']):
                    raise ValueError('equities_data_scope')
                equity_marker_file = state / 'last_equities.json'
                equity_marker = read_daily_marker(equity_marker_file, 'equities_research', status['errors'])
                if daily_cycle_required(equity_marker, registry, now):
                    equity_marker = {'day': now.date().isoformat(), 'result': cycle(bundle, registry, now)}
                    atomic_write(equity_marker_file, json.dumps(equity_marker, allow_nan=False))
                paper_file = state / 'equity_paper.json'
                paper = load_equity_paper(paper_file, now, last_session=bundle['assets'][0]['bars'][-1]['close_at'])
                # Forward paper decisions use only sessions present in the current bundle at this observation.
                paper = advance_equity_paper(bundle, paper, TEMPLATES[0], now=now)
                save_equity_paper(paper_file, paper)
                shadows = {}
                for name, spec in CHALLENGERS.items():
                    shadow_file = state / ('equity_paper_v3_' + name + '.json')
                    shadow = load_equity_paper(
                        shadow_file, now,
                        last_session=bundle['assets'][0]['bars'][-1]['close_at']
                    )
                    shadow = advance_equity_paper(
                        bundle, shadow, spec, now=now,
                        allocation=20, reserve_ratio=.30, risk_model=True
                    )
                    save_equity_paper(shadow_file, shadow)
                    shadows[name] = equity_paper_summary(shadow)
                status['equities'] = {**equity_marker['result'], 'paper': equity_paper_summary(paper),
                                      'v3_shadow': shadows, 'broker_orders_activated': False}
                if policy:
                    fx = collect_fx(state / 'eur-usd.json', now)
                    funded_file = state / ('equity_' + policy['id'] + '.json')
                    if funded_file.exists():
                        funded = load_equity_paper(funded_file, now)
                    else:
                        funded = new_state(now, initial=100 * fx['usd_per_eur'],
                                           last_session=bundle['assets'][0]['bars'][-1]['close_at'])
                        funded.update(policy_id=policy['id'], initial_eur=100,
                                      funding_fx=fx, funded_at=now.isoformat())
                    ai = advice(root / 'user_data/reports', 'ACTIONS-USD', now, policy)
                    funded = advance_equity_paper(bundle, funded, TEMPLATES[0], now=now,
                        max_drawdown=None, loss_stops=False, allocation=10 * fx['usd_per_eur'],
                        advisory=ai, execution_revision='market_room_no_loss_stops_v1')
                    funded.update(advisory=ai, loss_limit_pct=None, position_loss_stops=False)
                    save_equity_paper(funded_file, funded)
                    current = equity_paper_summary(funded)
                    current.update(initial_eur=100, equity_eur=round(funded['equity']/fx['usd_per_eur'],4),
                                   return_eur_pct=round((funded['equity']/fx['usd_per_eur']/100-1)*100,4),
                                   funding_usd=round(funded['initial_cash'],4), funding_fx_date=funded['funding_fx']['date'],
                                   fx_usd_per_eur=fx['usd_per_eur'], fx_date=fx['date'],
                                   policy_id=policy['id'], funded_at=funded['funded_at'], advisory=ai,
                                   loss_limit_pct=None, position_loss_stops=False)
                    status['equities'].update(control=status['equities']['paper'], paper=current)
            except Exception as exc:
                status['equities'] = {'state': 'invalid_broker_data', 'error_type': type(exc).__name__, 'broker_orders_activated': False}
                status['errors'].append('equity_collection_' + type(exc).__name__)
        # Factory needs verifiable forward evidence; backtests never satisfy it.
        evidence_file = state / 'forward_growth.json'
        if evidence_file.exists():
            try:
                evidence = read_json(evidence_file)
                status['child_created'] = registry.create_child(evidence['bot_id'], evidence, now)
            except Exception as exc:
                status['factory'] = {'state': 'not_eligible', 'error_type': type(exc).__name__}
        status['bots'] = registry.bots()
        atomic_write(root / 'user_data/reports/market-context.json', json.dumps(
            {'schema_version': 1, 'generated_at': now.isoformat(),
             'policy_id': policy['id'] if policy else None, **contexts}, allow_nan=False))
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
