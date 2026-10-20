import tempfile, unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from research_lab.equity_paper import new_state, advance, save, load, summary

class EquityPaperTests(unittest.TestCase):
    spec = {'family':'trend_breakout','fast':2,'slow':3,'breakout':2,'stop_loss':.05,'max_hold':30}

    def small_bundle(self, count=8, price=10):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = [{'open_at':(start+timedelta(days=i)).isoformat(),
                 'close_at':(start+timedelta(days=i,hours=6)).isoformat(),
                 'open':price,'high':price,'low':price,'close':price,'volume':100000}
                for i in range(count)]
        return {'assets':[{'id':'TEST','bars':bars}]}

    def seeded_position(self, bundle, last_index, quantity=1, held_sessions=None):
        bars = bundle['assets'][0]['bars']
        state = new_state(last_session=bars[last_index]['close_at'])
        state['cash'] = 100 - quantity * 10
        state['positions']['TEST'] = {
            'quantity':quantity, 'cost':quantity*10, 'entry_price':10,
            'entry_session':bars[last_index]['close_at'], 'entry_index':last_index,
            'highest_price':10}
        if held_sessions is not None:
            state['positions']['TEST'].update(held_sessions=held_sessions,
                held_as_of=bars[last_index]['close_at'])
        return state

    def run_paper(self, bundle, state, **kwargs):
        now = datetime.fromisoformat(bundle['assets'][0]['bars'][-1]['close_at'])
        spec = kwargs.pop('spec', self.spec)
        return advance(bundle, state, spec, now=now, fee=0, min_commission=0, slippage=0, **kwargs)

    def bundle(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc); bars=[]
        for i in range(70):
            p=10+i*.1; bars.append({'open_at':(start+timedelta(days=i)).isoformat(),'close_at':(start+timedelta(days=i,hours=6)).isoformat(),'open':p,'high':p*1.01,'low':p*.99,'close':p,'volume':100000})
        return {'schema_version':1,'currency':'USD','provider':'fixture','observed_at':bars[-1]['close_at'],'diagnostic_only':True,'broker_connected':False,'real_money_eligible':False,'assets':[{'id':'TEST','currency':'USD','asset_class':'stock','price_basis':'raw','lot_size':1,'bars':bars}]}
    def test_new_forward_state_can_start_after_existing_history(self):
        b=self.bundle(); last=b['assets'][0]['bars'][-1]['close_at']; s=new_state(datetime.now(timezone.utc),last_session=last)
        self.assertEqual(s['equity'],100); self.assertEqual(s['last_session'],last); self.assertEqual(s['trades'],[])
    def test_persistent_brokerless_portfolio_is_idempotent(self):
        b=self.bundle(); spec={'family':'trend_breakout','fast':10,'slow':50,'breakout':10,'stop_loss':.05,'max_hold':30}; now=datetime.fromisoformat(b['assets'][0]['bars'][-1]['close_at'])
        s=advance(b,new_state(now),spec,now=now); before=(s['equity'],len(s['trades']),len(s['positions']),s['last_session']); advance(b,s,spec,now=now); self.assertEqual(before,(s['equity'],len(s['trades']),len(s['positions']),s['last_session']))
        self.assertFalse(summary(s)['real_money_eligible'])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json'; save(p,s); self.assertEqual(load(p)['last_session'],s['last_session'])

    def test_v2_stop_gap_fills_at_open_not_stop_level(self):
        b = self.small_bundle(count=5)
        b['assets'][0]['bars'][-1].update(open=8, high=9, low=7, close=8)
        s = self.seeded_position(b, 3)
        self.run_paper(b, s)
        self.assertEqual(s['positions'], {})
        self.assertEqual(s['trades'][0]['reason'], 'stop_loss_gap')
        self.assertEqual(s['trades'][0]['profit'], -2)
        self.assertEqual(s['equity'], 98)

    def test_v2_intraday_stop_precedes_profit_barrier(self):
        b = self.small_bundle(count=5)
        b['assets'][0]['bars'][-1].update(open=10, high=12, low=9.4, close=11)
        s = self.seeded_position(b, 3)
        self.run_paper(b, s, spec={**self.spec, 'take_profit':.08})
        self.assertEqual(s['trades'][0]['reason'], 'stop_loss')
        self.assertEqual(s['trades'][0]['profit'], -.5)
        self.assertEqual(s['equity'], 99.5)

    def test_open_portfolio_halt_liquidates_with_costs_and_survives_restart(self):
        b = self.small_bundle(count=5)
        b['assets'][0]['bars'][-1].update(open=9.5, high=12, low=9.4, close=12)
        s = self.seeded_position(b, 3, quantity=10)
        now = datetime.fromisoformat(b['assets'][0]['bars'][-1]['close_at'])
        advance(b, s, self.spec, now=now, halt_action='liquidate')
        self.assertTrue(s['halted'])
        self.assertEqual(s['positions'], {})
        self.assertEqual(s['trades'][0]['reason'], 'risk_halt_open')
        self.assertAlmostEqual(s['equity'], 93.905)
        self.assertEqual(s['initial_cash'], 100)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'state.json'
            save(path, s)
            restored = load(path)
            # A subsequent qualifying breakout cannot restart a halted portfolio.
            next_bundle = self.small_bundle(count=9, price=5)
            for i, bar in enumerate(next_bundle['assets'][0]['bars']):
                price = 5 + i * .1
                bar.update(open=price, high=price, low=price, close=price)
            self.run_paper(next_bundle, restored, halt_action='liquidate')
            self.assertEqual(restored['positions'], {})
            self.assertEqual(restored['trades'], s['trades'])
            self.assertEqual(restored['cash'], s['cash'])
            self.assertEqual(summary(restored)['state'], 'paper_halted')

    def test_closing_portfolio_halt_liquidates_remaining_exposure(self):
        b = self.small_bundle(count=5)
        b['assets'][0]['bars'][-1].update(open=10, high=10, low=9.3, close=9.4)
        s = self.seeded_position(b, 3, quantity=10)
        self.run_paper(b, s, spec={**self.spec, 'stop_loss':.10}, halt_action='liquidate')
        self.assertTrue(s['halted'])
        self.assertEqual(s['positions'], {})
        self.assertEqual(s['trades'][0]['reason'], 'risk_halt_close')
        self.assertEqual(s['equity'], 94)
        self.assertEqual(s['max_drawdown_pct'], 6)

    def test_max_hold_counts_new_sessions_in_a_rolling_window(self):
        b = self.small_bundle()
        s = self.seeded_position(b, 7)
        self.run_paper(b, s, spec={**self.spec, 'max_hold':2}, risk_model=True)
        self.assertEqual(s['positions']['TEST']['held_sessions'], 0)
        for index in range(8, 10):
            next_bar = self.small_bundle(count=index+1)['assets'][0]['bars'][-1]
            b['assets'][0]['bars'] = b['assets'][0]['bars'][1:] + [next_bar]
            self.run_paper(b, s, spec={**self.spec, 'max_hold':2}, risk_model=True)
            if index == 8:
                self.assertEqual(s['positions']['TEST']['held_sessions'], 1)
        self.assertEqual(s['positions'], {})
        self.assertEqual(s['trades'][0]['reason'], 'time_limit')

    def test_legacy_age_uses_dates_and_preserves_existing_evidence(self):
        b = self.small_bundle(count=6)
        s = self.seeded_position(b, 4)
        s['positions']['TEST']['entry_session'] = b['assets'][0]['bars'][1]['close_at']
        s['positions']['TEST']['entry_index'] = 499
        s['trades'] = [{'asset':'OLD', 'profit':2, 'reason':'fixed_horizon'}]
        previous_trade = deepcopy(s['trades'][0])
        self.run_paper(b, s, spec={**self.spec, 'max_hold':4})
        self.assertEqual(s['positions'], {})
        self.assertEqual(s['trades'][0], previous_trade)
        self.assertEqual(s['trades'][1]['reason'], 'time_limit')
        self.assertEqual(s['initial_cash'], 100)
        self.assertEqual(s['equity'], 100)

    def test_unknown_legacy_age_blocks_without_reset_or_fabrication(self):
        b = self.small_bundle(count=6)
        s = self.seeded_position(b, 4)
        s['positions']['TEST']['entry_session'] = '2025-01-01T06:00:00+00:00'
        s['trades'] = [{'asset':'OLD', 'profit':2, 'reason':'fixed_horizon'}]
        before = deepcopy(s)
        self.run_paper(b, s)
        for field in ('cash','initial_cash','equity','positions','trades','last_session'):
            self.assertEqual(s[field], before[field])
        self.assertEqual(summary(s)['state'], 'paper_blocked')
        self.assertEqual(summary(s)['blocked_reason'], 'age_history_unavailable')
        self.assertNotIn('held_sessions', s['positions']['TEST'])

    def test_historical_drawdown_breach_stays_halted_after_recovery(self):
        b = self.small_bundle(count=5)
        s = self.seeded_position(b, 3)
        s['max_drawdown_pct'] = 6
        self.run_paper(b, s, halt_action='liquidate')
        self.assertTrue(s['halted'])
        self.assertEqual(s['trades'][0]['reason'], 'risk_halt_open')
        self.assertEqual(s['max_drawdown_pct'], 6)
        self.assertEqual(summary(s)['state'], 'paper_halted')

    def test_fill_cost_breach_prevents_further_entries_that_session(self):
        b = self.small_bundle(count=5, price=1)
        for i, bar in enumerate(b['assets'][0]['bars']):
            price = 1 + i * .01
            bar.update(open=price, high=price, low=price, close=price)
        b['assets'] = [{**deepcopy(b['assets'][0]), 'id':'TEST' + str(i)} for i in range(8)]
        s = new_state(last_session=b['assets'][0]['bars'][3]['close_at'])
        now = datetime.fromisoformat(b['assets'][0]['bars'][-1]['close_at'])
        advance(b, s, self.spec, now=now, fee=0, min_commission=1, slippage=0, halt_action='liquidate')
        self.assertTrue(s['halted'])
        self.assertEqual(s['positions'], {})
        self.assertEqual(len(s['trades']), 5)
        self.assertAlmostEqual(s['equity'], 90)

    def test_corporate_action_block_clears_with_safe_input_without_reset(self):
        b = self.small_bundle(count=5)
        s = self.seeded_position(b, 3)
        b['assets'][0]['corporate_actions'] = [{'kind':'split','date':'2026-01-05'}]
        self.run_paper(b, s)
        self.assertEqual(summary(s)['blocked_reason'], 'corporate_action_requires_review')
        self.assertEqual(s['last_session'], b['assets'][0]['bars'][3]['close_at'])
        b['assets'][0]['corporate_actions'] = []
        self.run_paper(b, s)
        self.assertEqual(summary(s)['state'], 'paper_active')
        self.assertIsNone(summary(s)['blocked_reason'])
        self.assertEqual(s['initial_cash'], 100)
        self.assertEqual(s['cash'], 90)
        self.assertEqual(s['positions']['TEST']['quantity'], 1)
        self.assertEqual(s['positions']['TEST']['held_sessions'], 1)
        self.assertEqual(s['trades'], [])
        self.assertEqual(summary(s)['execution_revision'], 'paper_engine_v2')
        self.assertIn('current_close', summary(s)['execution_model'])

    def test_historical_action_does_not_replay_or_block_existing_forward_state(self):
        b = self.small_bundle(count=5)
        s = self.seeded_position(b, 3)
        b['assets'][0]['corporate_actions'] = [{'kind':'dividend','date':'2026-01-02'}]
        self.run_paper(b, s)
        self.assertEqual(summary(s)['state'], 'paper_active')
        self.assertEqual(s['trades'], [])
        self.assertEqual(s['cash'], 90)
        self.assertEqual(s['positions']['TEST']['quantity'], 1)

    def test_future_action_does_not_block_sessions_before_its_effective_date(self):
        b = self.small_bundle(count=5)
        s = self.seeded_position(b, 3)
        b['assets'][0]['corporate_actions'] = [{'kind':'split','date':'2026-01-07'}]
        self.run_paper(b, s)
        self.assertEqual(summary(s)['state'], 'paper_active')
        self.assertEqual(s['last_session'], b['assets'][0]['bars'][-1]['close_at'])
        self.assertEqual(s['cash'], 90)
        self.assertEqual(s['trades'], [])

    def test_malformed_action_metadata_blocks_before_mutating_position_age(self):
        b = self.small_bundle(count=5)
        s = self.seeded_position(b, 3)
        b['assets'][0]['corporate_actions'] = [{'kind':'split','date':'unknown'}]
        before = deepcopy(s)
        self.run_paper(b, s)
        self.assertEqual(summary(s)['blocked_reason'], 'corporate_action_metadata_invalid')
        for field in ('positions','cash','trades','last_session'):
            self.assertEqual(s[field], before[field])

    def breakout_bundle(self):
        b = self.small_bundle(count=5, price=5)
        for i, bar in enumerate(b['assets'][0]['bars']):
            price = 5 + i * .1
            bar.update(open=price, high=price, low=price, close=price)
        return b

    def test_v3_volume_filter_uses_previous_closed_volume(self):
        b = self.breakout_bundle()
        b['assets'][0]['bars'][-1]['volume'] = 100000000
        last = b['assets'][0]['bars'][-2]['close_at']
        control = new_state(last_session=last)
        self.run_paper(b, control)
        self.assertEqual(len(control['positions']), 1)
        filtered = new_state(last_session=last)
        self.run_paper(b, filtered, spec={**self.spec,'min_volume_ratio':1.1})
        self.assertEqual(filtered['positions'], {})
        self.assertEqual(filtered['cash'], 100)

    def test_v3_atr_band_uses_previous_closed_prices(self):
        b = self.breakout_bundle()
        b['assets'][0]['bars'][-1].update(high=30, low=.1)
        last = b['assets'][0]['bars'][-2]['close_at']
        for minimum, maximum in ((.10,.20),(0,.015)):
            with self.subTest(minimum=minimum, maximum=maximum):
                filtered = new_state(last_session=last)
                self.run_paper(b, filtered, spec={**self.spec,'min_atr_pct':minimum,'max_atr_pct':maximum})
                self.assertEqual(filtered['positions'], {})
        accepted = new_state(last_session=last)
        self.run_paper(b, accepted, spec={**self.spec,'min_atr_pct':.01,'max_atr_pct':.03})
        self.assertEqual(len(accepted['positions']), 1)
if __name__=='__main__': unittest.main()
