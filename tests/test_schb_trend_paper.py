import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_lab import schb_trend_paper as m
from research_lab.worker import advance_market_room_schb
from scripts.collect_equity_paper import collect_schb

NOW = datetime(2026, 10, 21, 22, tzinfo=timezone.utc)


def make_bars(prices, end=datetime(2026, 10, 21, tzinfo=timezone.utc)):
    days, d = [], end
    while len(days) < len(prices):
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return [{'date': x.date().isoformat(), 'close_at': (x + timedelta(hours=20)).isoformat(),
             'open': p, 'high': p, 'low': p, 'close': p, 'volume': 1} for x, p in zip(days, prices)]


def bundle(prices, splits=()):
    return {'symbol': 'SCHB', 'real_money_eligible': False, 'bars': make_bars(prices), 'splits': list(splits)}


def yahoo(bars, kind='ETF', symbol='SCHB'):
    ts = [int((datetime.fromisoformat(b['close_at']) - timedelta(hours=6)).timestamp()) for b in bars]
    q = {k: [b[k] for b in bars] for k in ('open', 'high', 'low', 'close', 'volume')}
    return json.dumps({'chart': {'result': [{'meta': {'symbol': symbol, 'currency': 'USD', 'instrumentType': kind},
                                             'timestamp': ts, 'indicators': {'quote': [q]},
                                             'events': {'splits': {'1': {'date': ts[5], 'numerator': 3, 'denominator': 1}}}}]}}).encode()


def replay(prices, start, splits=()):
    full = bundle(prices, splits)
    state = m.new_state(NOW, 116.0, full['bars'][start]['close_at'])
    for k in range(start + 1, len(prices) + 1):
        m.advance(state, {**full, 'bars': full['bars'][:k]}, NOW)
    return state


class SchbTrendPaperTests(unittest.TestCase):
    def test_parse_requires_etf_identity_closed_sessions_and_history(self):
        bars = make_bars([29.5] * 230)
        parsed = m.parse(yahoo(bars), NOW)
        self.assertEqual(len(parsed['bars']), 230)
        self.assertEqual(parsed['splits'][0][1], 3.0)
        self.assertEqual(len(m.parse(yahoo(bars), NOW - timedelta(hours=3))['bars']), 229)
        with self.assertRaises(ValueError):
            m.parse(yahoo(bars, kind='EQUITY'), NOW)
        with self.assertRaises(ValueError):
            m.parse(yahoo(bars[:150]), NOW)

    def test_initial_allocation_buys_whole_shares_next_open(self):
        prices = [20 + i * .05 for i in range(260)]
        state = replay(prices, 250)
        buy = [o for o in state['orders'] if o['side'] == 'buy'][0]
        self.assertEqual(buy['session'], make_bars(prices)[251]['close_at'])
        self.assertEqual(buy['quantity'], int(buy['quantity']))
        self.assertGreaterEqual(state['cash'], 0)
        self.assertEqual(state['positions']['SCHB']['quantity'], state['shares'])

    def test_below_sma_goes_to_cash_only_at_month_start(self):
        prices = [20 + i * .05 for i in range(240)] + [32 - i * .3 for i in range(60)]
        state = replay(prices, 230)
        sells = [o for o in state['orders'] if o['side'] == 'sell']
        self.assertTrue(sells)
        bars = make_bars(prices)
        index = {b['close_at']: i for i, b in enumerate(bars)}
        for order in sells:
            i = index[order['session']] - 1  # décision la veille = 1re séance du mois
            self.assertNotEqual(bars[i]['date'][:7], bars[i - 1]['date'][:7])
        self.assertEqual(state['shares'], 0)

    def test_split_multiplies_held_shares(self):
        prices = [20 + i * .05 for i in range(260)]
        full = bundle(prices)
        split_day = full['bars'][255]['date']
        state = replay(prices, 250, splits=[[split_day, 3.0]])
        bought = [o for o in state['orders'] if o['side'] == 'buy'][0]['quantity']
        self.assertEqual(state['shares'], bought * 3)

    def test_alerts_are_notify_only_and_unique(self):
        prices = [20 + i * .05 for i in range(250)] + [32 * (1 - .01 * i) for i in range(1, 15)]
        state = replay(prices, 249)
        self.assertTrue(state['alerts'])
        self.assertTrue(all(a['action'] == 'notify_only' for a in state['alerts']))
        self.assertLessEqual(len(state['alerts']), 2)
        self.assertFalse([o for o in state['orders'] if o['side'] == 'sell'])

    def test_idempotent(self):
        b = bundle([20 + i * .05 for i in range(260)])
        state = m.new_state(NOW, 116.0, b['bars'][-5]['close_at'])
        m.advance(state, b, NOW)
        before = json.dumps(state, sort_keys=True)
        m.advance(state, b, NOW)
        state['updated_at'] = json.loads(before)['updated_at']
        self.assertEqual(json.dumps(state, sort_keys=True), before)

    def test_worker_creates_new_plan_and_never_touches_legacy_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); st = root / 'research_state'; st.mkdir()
            legacy = st / 'equity_market_room_v1.json'
            legacy.write_text(json.dumps({'execution_revision': 'market_room_no_loss_stops_v1', 'equity': 111.0,
                                          'positions': {'SOFI': {}, 'MARA': {}}, 'trades': [{}], 'last_session': 'x'}))
            before = legacy.read_bytes()
            b = bundle([20 + i * .05 for i in range(260)])
            b['bars'][-1]['close_at'] = (NOW - timedelta(hours=2)).isoformat()
            (st / 'schb.bundle.json').write_text(json.dumps(b))
            fx = {'usd_per_eur': 1.16, 'date': '2026-10-21'}
            current = advance_market_room_schb(st, NOW, {'id': 'market_room_v1'}, fx, root)
            self.assertEqual(legacy.read_bytes(), before)
            self.assertEqual(current['plan_id'], 'market_room_schb_slow_trend_v1')
            self.assertEqual(current['supersedes']['open_symbols'], ['MARA', 'SOFI'])
            self.assertFalse(current['supersedes']['positions_carried_over'])
            self.assertEqual(current['initial_eur'], 100)
            self.assertFalse(current['real_money_eligible'])
            self.assertTrue((st / 'equity_market_room_v1_market_room_schb_slow_trend_v1.json').exists())
            with self.assertRaises(ValueError):
                m.load(legacy)

    def test_stale_or_short_bundle_refused(self):
        b = bundle([29.5] * 260)
        with self.assertRaises(ValueError):
            m.validate_bundle(b, NOW + timedelta(days=10))
        with self.assertRaises(ValueError):
            m.validate_bundle({**b, 'bars': b['bars'][:100]}, NOW)

    def test_collect_schb_isolated_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'research_state').mkdir()
            def boom(now):
                raise ValueError('schb_http_refused')
            self.assertEqual(collect_schb(root, NOW, boom)['state'], 'unavailable')
            ok = collect_schb(root, NOW, lambda now: bundle([29.5] * 260))
            self.assertEqual(ok['sessions'], 260)

    def test_frozen_research_universe_unchanged(self):
        from research_lab.equity_data import SYMBOLS
        self.assertEqual(SYMBOLS, m.LEGACY_SYMBOLS)


if __name__ == '__main__':
    unittest.main()
