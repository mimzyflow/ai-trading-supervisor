#!/usr/bin/env python3
import json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.equity_live import collect, error_code
from research_lab import schb_trend_paper
from supervisor.report import atomic_write


def run(root, now=None, collector=collect, schb_collector=None):
    now = now or datetime.now(timezone.utc)
    status = {'state': 'unavailable', 'observed_at': now.isoformat()}
    try:
        bundle = collector(now)
        repairs = [{'symbol': source['symbol'], 'reason': source['repair']['reason'],
                    'sessions': source['repair']['sessions']}
                   for source in bundle.get('provenance', {}).get('sources', []) if 'repair' in source]
        atomic_write(root / 'research_state/equities.bundle.json', json.dumps(bundle, ensure_ascii=False, allow_nan=False))
        status.update(state='current', assets=len(bundle['assets']),
                      last_closed_session=bundle['assets'][0]['bars'][-1]['close_at'], repairs=repairs)
    except Exception as exc:
        # A failed market source never disables the independent crypto guardian.
        # Keep the old bundle as evidence, but mark it unusable for new decisions.
        status['error_type'] = type(exc).__name__
        if error_code(exc):
            status['error_code'] = error_code(exc)
    atomic_write(root / 'research_state/equity_collection.json', json.dumps(status, allow_nan=False))
    if schb_collector is not None:
        status['schb'] = collect_schb(root, now, schb_collector)
    print(json.dumps(status))
    return status


def collect_schb(root, now, collector=schb_trend_paper.collect):
    """Historique SCHB (Yahoo, >= 210 séances) du plan papier market_room_schb_slow_trend_v1.
    Indépendant : un échec n'invalide ni l'univers figé ni la garde crypto."""
    result = {'state': 'unavailable', 'observed_at': now.isoformat()}
    try:
        bundle = collector(now)
        atomic_write(root / 'research_state/schb.bundle.json', json.dumps(bundle, allow_nan=False))
        result.update(state='current', sessions=len(bundle['bars']), last_closed_session=bundle['bars'][-1]['close_at'])
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    atomic_write(root / 'research_state/schb_collection.json', json.dumps(result, allow_nan=False))
    return result


if __name__ == '__main__':
    run(Path(__file__).resolve().parents[1], schb_collector=schb_trend_paper.collect)
