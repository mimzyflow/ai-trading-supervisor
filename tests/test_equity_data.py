import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from research_lab.equity_data import (SYMBOLS, MAX_RESPONSE_BYTES, chart_url, load_calendar,
                                     build_diagnostic_bundle)
from scripts.download_equity_diagnostics import collect, download_chart
from supervisor.api import NoRedirect

NOW = '2026-10-04T12:00:00+00:00'


def fixture_calendar():
    # Small injected schedule deliberately has no verified flag.
    return {'name': 'fixture', 'sessions': [
        {'date': '2021-06-01', 'open_at': '2021-06-01T13:30:00+00:00', 'close_at': '2021-06-01T20:00:00+00:00'},
        {'date': '2021-06-02', 'open_at': '2021-06-02T13:30:00+00:00', 'close_at': '2021-06-02T20:00:00+00:00'},
        {'date': '2021-11-26', 'open_at': '2021-11-26T14:30:00+00:00', 'close_at': '2021-11-26T18:00:00+00:00'},
    ]}


def fixture_chart(symbol='SOFI', calendar=None):
    calendar = calendar or fixture_calendar()
    timestamps = [int(datetime.fromisoformat(s['open_at']).timestamp()) for s in calendar['sessions']]
    count = len(timestamps)
    return {'chart': {'error': None, 'result': [{'meta': {
        'symbol': symbol, 'currency': 'USD', 'instrumentType': 'EQUITY',
        'exchangeTimezoneName': 'America/New_York', 'dataGranularity': '1d'},
        'timestamp': timestamps, 'events': {},
        'indicators': {'quote': [{'open': [10.0] * count, 'high': [11.0] * count,
                                 'low': [9.0] * count, 'close': [10.5] * count,
                                 'volume': [10000] * count}]}}]}}


def raws(change=None):
    values = {s: fixture_chart(s) for s in SYMBOLS}
    if change:
        change(values['SOFI']['chart']['result'][0])
    return {s: json.dumps(v).encode() for s, v in values.items()}


class Response(io.BytesIO):
    status = 200

    def __init__(self, raw, url):
        super().__init__(raw)
        self.url = url
        self.read_limits = []

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_limits.append(size)
        return super().read(size)


class EquityDataTests(unittest.TestCase):
    def build(self, data=None, calendar=None, now=NOW):
        return build_diagnostic_bundle(data or raws(), calendar or fixture_calendar(), now)

    def test_preserves_values_and_exact_dst_early_close_without_claiming_verification(self):
        raw = raws()
        data = self.build(raw)
        self.assertEqual([a['id'] for a in data['assets']], list(SYMBOLS))
        self.assertEqual(data['currency'], 'USD')
        self.assertEqual(data['assets'][0]['bars'][-1]['close_at'], '2021-11-26T18:00:00+00:00')
        self.assertEqual(data['assets'][0]['bars'][0]['open_at'], '2021-06-01T13:30:00+00:00')
        self.assertEqual(data['assets'][0]['bars'][-1]['open_at'], '2021-11-26T14:30:00+00:00')
        self.assertEqual(data['assets'][0]['bars'][0]['close'], 10.5)
        self.assertEqual(data['assets'][0]['price_basis'], 'raw')
        self.assertEqual(data['assets'][0]['lot_size'], 1)
        for key in ('calendar_verified', 'corporate_actions_verified', 'historical_universe_verified',
                    'broker_connected', 'real_money_eligible'):
            self.assertIs(data[key], False)
        self.assertEqual(data['provenance']['sources'][0]['sha256'], hashlib.sha256(raw['SOFI']).hexdigest())

    def test_refuses_wrong_symbol_currency_timezone_asset_type_and_interval(self):
        for key, value in [('symbol', 'U'), ('currency', 'EUR'), ('exchangeTimezoneName', 'UTC'),
                           ('instrumentType', 'ETF'), ('dataGranularity', '1wk')]:
            with self.subTest(key=key):
                data = raws(lambda result: result['meta'].__setitem__(key, value))
                with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
                    self.build(data)

    def test_refuses_missing_null_boolean_negative_nonfinite_and_zero_ohlcv(self):
        for key, value in [('open', None), ('volume', None), ('close', True), ('low', -1),
                           ('high', float('inf')), ('close', float('nan')), ('volume', 0)]:
            with self.subTest(key=key, value=value):
                data = raws(lambda result: result['indicators']['quote'][0][key].__setitem__(0, value))
                with self.assertRaises(ValueError):
                    self.build(data)
        for key in ('volume', 'open'):
            data = raws(lambda result: result['indicators']['quote'][0].pop(key))
            with self.assertRaises(ValueError):
                self.build(data)

    def test_refuses_incomplete_arrays_and_missing_trading_days_for_either_asset(self):
        data = raws(lambda result: result['indicators']['quote'][0]['volume'].pop())
        with self.assertRaisesRegex(ValueError, 'incomplete_ohlcv'):
            self.build(data)
        for symbol in SYMBOLS:
            values = {s: fixture_chart(s) for s in SYMBOLS}
            result = values[symbol]['chart']['result'][0]
            result['timestamp'].pop(1)
            for series in result['indicators']['quote'][0].values():
                series.pop(1)
            with self.subTest(symbol=symbol), self.assertRaisesRegex(ValueError, 'missing_sessions'):
                self.build({s: json.dumps(v).encode() for s, v in values.items()})

    def test_refuses_duplicates_wrong_open_timestamps_and_non_session_dates(self):
        for change in (
            lambda r: r['timestamp'].__setitem__(1, r['timestamp'][0]),
            lambda r: r['timestamp'].__setitem__(0, r['timestamp'][0] + 60),
            lambda r: r['timestamp'].__setitem__(0, r['timestamp'][0] - 86400),
            lambda r: r['timestamp'].__setitem__(0, True),
        ):
            with self.assertRaises(ValueError):
                self.build(raws(change))

    def test_refuses_future_or_not_yet_closed_sessions(self):
        with self.assertRaisesRegex(ValueError, 'unclosed_session'):
            self.build(now='2021-11-26T17:59:59+00:00')
        values = raws(lambda r: r['timestamp'].__setitem__(0, 1_900_000_000))
        with self.assertRaisesRegex(ValueError, 'future_bar'):
            self.build(values)
        with self.assertRaisesRegex(ValueError, 'future_source_observation'):
            build_diagnostic_bundle(raws(), fixture_calendar(), NOW, {'SOFI': '2027-01-01T00:00:00Z'})
        with self.assertRaisesRegex(ValueError, 'unclosed_source_session'):
            build_diagnostic_bundle(raws(), fixture_calendar(), NOW, {'SOFI': '2021-11-26T17:59:59Z'})

    def test_pinned_calendar_is_local_and_preserves_dst_early_closes_and_complete_range(self):
        try:
            import exchange_calendars  # noqa: F401
        except ImportError:
            self.skipTest('Optional calendar dependency is not installed in this environment')
        calendar = load_calendar(NOW)
        self.assertEqual(calendar['version'], '4.13.2')
        self.assertEqual(calendar['sessions'][0]['date'], '2021-06-01')
        self.assertEqual(calendar['sessions'][-1]['date'], '2026-10-02')
        schedule = {s['date']: s for s in calendar['sessions']}
        self.assertEqual(schedule['2021-11-26']['close_at'], '2021-11-26T18:00:00+00:00')
        self.assertEqual(schedule['2022-03-11']['open_at'], '2022-03-11T14:30:00+00:00')
        self.assertEqual(schedule['2022-03-14']['open_at'], '2022-03-14T13:30:00+00:00')
        self.assertNotIn('2021-11-25', schedule)
        all_raw = {s: json.dumps(fixture_chart(s, calendar)).encode() for s in SYMBOLS}
        self.assertIs(build_diagnostic_bundle(all_raw, calendar, NOW)['calendar_verified'], True)

    def test_any_announced_split_dividend_or_capital_gain_requires_review(self):
        for kind in ('splits', 'dividends', 'capitalGains'):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'announced_action_requires_review'):
                self.build(raws(lambda result: result['events'].__setitem__(kind, {'1622554200': {'amount': 1}})))
        with self.assertRaisesRegex(ValueError, 'invalid_events'):
            self.build(raws(lambda result: result.__setitem__('events', None)))

    def test_refuses_errors_malformed_json_duplicate_keys_and_oversized_payload(self):
        for invalid in (b'{', b'{"chart":{},"chart":{}}', b'x' * (MAX_RESPONSE_BYTES + 1),
                        b'{"chart":{"error":{"code":"Not Found"},"result":null}}'):
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                self.build({'SOFI': invalid, 'U': raws()['U']})

    def test_fixed_universe_has_no_private_url_or_arbitrary_symbol_seam(self):
        for symbol in ('AAPL', '../private', 'SOFI?nonce=secret', 'https://127.0.0.1/'):
            with self.assertRaisesRegex(ValueError, 'symbol_not_allowed'):
                chart_url(symbol)
        with self.assertRaisesRegex(ValueError, 'fixed_universe_required'):
            self.build({'SOFI': raws()['SOFI']})


class DownloadTests(unittest.TestCase):
    def test_only_public_get_without_nonce_key_cookie_or_body_and_bounded_read(self):
        received = []
        response = Response(raws()['SOFI'], chart_url('SOFI'))
        def opener(request, timeout):
            received.append(request)
            self.assertEqual(timeout, 15)
            return response
        self.assertEqual(download_chart('SOFI', opener), raws()['SOFI'])
        request = received[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'query1.finance.yahoo.com')
        self.assertEqual(parsed.path, '/v8/finance/chart/SOFI')
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(set(dict(request.header_items())), {'User-agent', 'Accept'})
        params = parse_qs(parsed.query)
        self.assertEqual(params['events'], ['div,splits,capitalGains'])
        self.assertNotIn('nonce', params)
        self.assertEqual(response.read_limits, [MAX_RESPONSE_BYTES + 1])

    def test_oversize_redirect_http_error_and_provider_exception_are_sanitized(self):
        for response in (Response(b'x' * (MAX_RESPONSE_BYTES + 1), chart_url('SOFI')),
                         Response(b'{}', 'https://127.0.0.1/private')):
            with self.assertRaises(ValueError):
                download_chart('SOFI', lambda request, timeout: response)
        def fail(request, timeout):
            raise RuntimeError('private-token-and-personal-data')
        with self.assertRaisesRegex(ValueError, '^equity_download_failed$'):
            download_chart('SOFI', fail)
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, 'moved', {}, 'http://localhost/'))

    def test_default_opener_contains_no_redirect_handler(self):
        fake = lambda request, timeout: Response(raws()['SOFI'], request.full_url)
        with patch('scripts.download_equity_diagnostics.build_opener') as factory:
            factory.return_value.open = fake
            download_chart('SOFI')
            self.assertIsInstance(factory.call_args.args[0], NoRedirect)

    def test_new_run_keeps_exact_raw_hashes_validated_bundle_and_never_overwrites(self):
        data = raws()
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            symbol = urlsplit(request.full_url).path.rsplit('/', 1)[-1]
            return Response(data[symbol], request.full_url)
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / 'research_results'
            output, manifest = collect(base, 'fixture', opener, fixture_calendar(), NOW)
            self.assertEqual(manifest['state'], 'validated_diagnostic')
            self.assertEqual(manifest['session_count'], 3)
            saved = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(saved['raw/SOFI.json'], data['SOFI'])
            self.assertEqual(saved['raw/U.json'], data['U'])
            self.assertEqual(manifest['bundle_file_sha256'], hashlib.sha256(saved['equities.bundle.json']).hexdigest())
            with self.assertRaises(FileExistsError):
                collect(base, 'fixture', opener, fixture_calendar(), NOW)
            self.assertEqual(calls, [chart_url(s) for s in SYMBOLS])
            self.assertEqual(saved, {str(p.relative_to(output)): p.read_bytes() for p in output.rglob('*') if p.is_file()})

    def test_refused_run_preserves_raw_evidence_but_writes_no_bundle(self):
        data = raws(lambda r: r['events'].__setitem__('splits', {'x': {'ratio': 2}}))
        def opener(request, timeout):
            symbol = urlsplit(request.full_url).path.rsplit('/', 1)[-1]
            return Response(data[symbol], request.full_url)
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / 'research_results'
            with self.assertRaisesRegex(ValueError, 'announced_action_requires_review'):
                collect(base, 'refused', opener, fixture_calendar(), NOW)
            output = base / 'refused'
            self.assertFalse((output / 'equities.bundle.json').exists())
            self.assertEqual((output / 'raw/SOFI.json').read_bytes(), data['SOFI'])
            self.assertEqual(json.loads((output / 'manifest.json').read_text())['state'], 'refused')

    def test_output_must_be_new_named_directory_under_research_results(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'output_must_be_research_results'):
                collect(Path(temp) / 'public', calendar=fixture_calendar(), observed_at=NOW)
            for name in ('../other', 'a/b', '.hidden'):
                with self.assertRaisesRegex(ValueError, 'output_name_invalid'):
                    collect(Path(temp) / 'research_results', name, calendar=fixture_calendar(), observed_at=NOW)


if __name__ == '__main__':
    unittest.main()
