"""Explicit public GET download into a new ignored directory; no account/order API."""
import argparse
import hashlib
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_lab.data import canonical_hash, stamp
from research_lab.equity_data import (SYMBOLS, START_DATE, END_DATE, LIMITATIONS,
                                     MAX_RESPONSE_BYTES, chart_url, load_calendar,
                                     build_diagnostic_bundle)
from supervisor.api import NoRedirect


def download_chart(symbol, opener=None):
    url = chart_url(symbol)
    request = Request(url, headers={'User-Agent': 'EquityDiagnostics/1.0',
                                   'Accept': 'application/json'}, method='GET')
    opener = opener or build_opener(NoRedirect()).open
    try:
        with opener(request, timeout=15) as response:
            if response.geturl() != url or response.status != 200:
                raise ValueError('equity_redirect_or_non_success_refused')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('equity_response_too_large_or_invalid')
        return raw
    except ValueError:
        raise
    except Exception:
        raise ValueError('equity_download_failed') from None


def _write_new(path, payload):
    with path.open('xb') as handle:
        handle.write(payload)
    path.chmod(0o600)


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def collect(output_root, name=None, opener=None, calendar=None, observed_at=None):
    """Online access lives only in this explicit CLI; injectable seams are for fixtures."""
    fixed_time = stamp(observed_at) if observed_at is not None else None
    calendar = calendar if calendar is not None else load_calendar(observed_at)
    output_root = Path(output_root)
    if output_root.name != 'research_results' or output_root.is_symlink():
        raise ValueError('equity_output_must_be_research_results')
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = name or ('equity-diagnostics-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4))
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', name):
        raise ValueError('equity_output_name_invalid')
    output = output_root / name
    output.mkdir(mode=0o700)  # exist_ok is deliberately false; never reuse or overwrite a run.
    (output / 'raw').mkdir(mode=0o700)
    manifest = {'schema_version': 1, 'state': 'incomplete', 'provider': 'yahoo_public_chart',
                'symbols': list(SYMBOLS), 'date_range': {'start': START_DATE, 'end': END_DATE},
                'diagnostic_only': True, 'broker_connected': False, 'real_money_eligible': False,
                'sources': [], 'limitations': list(LIMITATIONS),
                'calendar': {key: value for key, value in calendar.items() if key != 'sessions'}}
    raw_by_symbol, source_times = {}, {}
    try:
        for symbol in SYMBOLS:
            raw = download_chart(symbol, opener)
            observed = fixed_time or datetime.now(timezone.utc)
            _write_new(output / 'raw' / (symbol + '.json'), raw)
            raw_by_symbol[symbol] = raw
            source_times[symbol] = observed.isoformat()
            manifest['sources'].append({'symbol': symbol, 'url': chart_url(symbol), 'method': 'GET',
                                        'observed_at': observed.isoformat(), 'raw_file': 'raw/' + symbol + '.json',
                                        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
        observed = fixed_time or datetime.now(timezone.utc)
        bundle = build_diagnostic_bundle(raw_by_symbol, calendar, observed.isoformat(), source_times)
        payload = _json_bytes(bundle)
        _write_new(output / 'equities.bundle.json', payload)
        manifest.update(state='validated_diagnostic', observed_at=observed.isoformat(),
                        bundle_file='equities.bundle.json', bundle_sha256=canonical_hash(bundle),
                        bundle_file_sha256=hashlib.sha256(payload).hexdigest(),
                        session_count=len(bundle['assets'][0]['bars']),
                        calendar_verified=bundle['calendar_verified'], corporate_actions_verified=False,
                        historical_universe_verified=False)
    except Exception as exc:
        manifest['state'] = 'refused'
        reason = str(exc) if isinstance(exc, ValueError) else 'equity_collection_failed'
        manifest['reason'] = reason if re.fullmatch(r'equity_[a-z_]+', reason) else 'equity_validation_failed'
        _write_new(output / 'manifest.json', _json_bytes(manifest))
        raise ValueError(manifest['reason']) from None
    _write_new(output / 'manifest.json', _json_bytes(manifest))
    return output, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download fixed SOFI/U public diagnostic data, without an account.')
    parser.add_argument('--name', help='New directory name under ignored research_results; existing names are refused.')
    args = parser.parse_args(argv)
    output_root = Path(__file__).resolve().parents[1] / 'research_results'
    output, manifest = collect(output_root, args.name)
    print(json.dumps({'state': manifest['state'], 'directory': str(output),
                      'sessions': manifest['session_count'], 'broker_connected': False,
                      'real_money_eligible': False}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileExistsError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else 'equity_output_already_exists'
        print(json.dumps({'state': 'refused', 'reason': reason}), file=sys.stderr)
        sys.exit(1)
