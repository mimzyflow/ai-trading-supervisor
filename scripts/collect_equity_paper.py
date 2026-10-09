#!/usr/bin/env python3
import json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.equity_live import collect, error_code
from supervisor.report import atomic_write


def run(root, now=None, collector=collect):
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
    print(json.dumps(status))
    return status


if __name__ == '__main__':
    run(Path(__file__).resolve().parents[1])
