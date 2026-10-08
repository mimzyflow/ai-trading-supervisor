import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from research_lab.data import validate, canonical_hash
from research_lab.engine import simulate, TEMPLATES
from research_lab.governor import Registry
from research_lab.research import cycle
from research_lab.collect import fetch_crypto
from research_lab.worker import verified_stop_simulation, once
from research_lab.paper_broker import PaperBroker


def bundle(prices=None, count=12, asset_class='crypto', start=None):
    start = start or datetime(2022, 1, 1, tzinfo=timezone.utc)
    prices = prices or [10 + i * 0.1 for i in range(count)]
    bars = []
    for i, price in enumerate(prices):
        opened = start + timedelta(days=i)
        bars.append({'open_at': opened.isoformat(), 'close_at': (opened + timedelta(hours=20)).isoformat(),
                     'open': price, 'high': price * 1.01, 'low': price * 0.99, 'close': price, 'volume': 10000})
    return {'schema_version': 1, 'currency': 'EUR', 'calendar_verified': True,
            'corporate_actions_verified': True, 'historical_universe_verified': True,
            'assets': [{'id': 'TOY', 'currency': 'EUR', 'asset_class': asset_class,
                        'price_basis': 'raw', 'lot_size': 0.00000001 if asset_class == 'crypto' else 1, 'bars': bars}]}


def report(equity=100):
    return {'schema_version': 2, 'observed_at': datetime.now(timezone.utc).isoformat(), 'mode': 'DRY-RUN',
            'api_ok': True, 'database_ok': True, 'configuration_safe': True,
            'equity_eur': equity, 'starting_balance_eur': 100, 'equity_peak_eur': 100}


class DataAndExecutionTests(unittest.TestCase):
    def test_rejects_future_duplicate_nan_and_currency_mixing(self):
        for change in ['future', 'duplicate', 'nan', 'currency']:
            data = bundle()
            if change == 'future': data['assets'][0]['bars'][0]['close_at'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            if change == 'duplicate': data['assets'][0]['bars'][1] = data['assets'][0]['bars'][0]
            if change == 'nan': data['assets'][0]['bars'][0]['close'] = float('nan')
            if change == 'currency': data['assets'][0]['currency'] = 'USD'
            with self.assertRaises(ValueError): validate(data)

    def test_equities_need_raw_prices_and_verified_fractional_support(self):
        data = bundle(asset_class='etf')
        data['assets'][0]['price_basis'] = 'adjusted'
        with self.assertRaises(ValueError): validate(data)
        data['assets'][0]['price_basis'] = 'raw'; data['assets'][0]['lot_size'] = 0.001
        with self.assertRaises(ValueError): validate(data)

    def test_no_leverage_or_growing_position_limits(self):
        for kwargs in [{'initial': 101}, {'allocation': 21}, {'max_drawdown': 0.5}, {'fee': 0.1}]:
            with self.assertRaises(ValueError): simulate(bundle(), TEMPLATES[0], **kwargs)

    def test_whole_share_minimum_prevents_impossible_small_orders(self):
        result = simulate(bundle(prices=[100]*8, asset_class='stock'), {'family': 'buy_hold'}, fee=0, slippage=0)
        self.assertEqual(result['closed_trades'], 0)
        self.assertEqual(result['equity'], 100)

    def test_both_fees_reduce_unchanged_price_portfolio(self):
        result = simulate(bundle(prices=[10]*8), {'family': 'buy_hold'}, fee=0.008, slippage=0)
        self.assertAlmostEqual(result['profit'], -20 * 0.016 / 1.008, places=5)
        self.assertEqual(result['closed_trades'], 1)

    def test_future_candles_cannot_change_prior_equity_path(self):
        data = bundle(count=30)
        spec = {'family': 'trend_breakout', 'fast': 2, 'slow': 3, 'breakout': 2, 'stop_loss': 0.05, 'max_hold': 20}
        first = copy.deepcopy(data); first['assets'][0]['bars'] = first['assets'][0]['bars'][:15]
        long = simulate(data, spec, close_at_end=False)
        short = simulate(first, spec, close_at_end=False)
        self.assertEqual(long['curve'][:15], short['curve'])

    def test_test_window_uses_warmup_without_earlier_trades(self):
        data = bundle(count=300)
        result = simulate(data, TEMPLATES[0], start_index=250)
        self.assertTrue(all(t['entry_session'] >= data['assets'][0]['bars'][250]['open_at'] for t in result['trades']))
        self.assertEqual(len(result['curve']), 50)

    def test_split_does_not_create_or_destroy_wealth(self):
        # Session 0 supplies known liquidity; the position exists before split.
        data = bundle(prices=[10,10,5,5,5], asset_class='stock')
        data['assets'][0]['bars'][2]['split_ratio'] = 2
        result = simulate(data, {'family': 'buy_hold'}, fee=0, slippage=0, risk_control=False)
        self.assertEqual(result['equity'], 100)
        self.assertEqual(result['trades'][0]['quantity'], 4)

    def test_dividend_receivable_does_not_become_spendable_before_payment(self):
        # Buy after liquidity warmup and before the dividend entitlement date.
        data = bundle(prices=[10,10,9,9,9], asset_class='etf')
        data['assets'][0]['bars'][2].update(dividend_per_share=1, dividend_paid_at='2023-01-01T00:00:00+00:00')
        result = simulate(data, {'family': 'buy_hold'}, fee=0, slippage=0, close_at_end=False, risk_control=False)
        self.assertEqual(result['cash'], 80)
        self.assertEqual(result['receivables'], 2)
        self.assertEqual(result['equity'], 100)

    def test_zero_volume_does_not_fill_an_order(self):
        data = bundle(); data['assets'][0]['bars'][0]['volume'] = 0
        with self.assertRaises(ValueError):simulate(data, {'family': 'buy_hold'})

    def test_drawdown_halt_latches_despite_later_recovery(self):
        data = bundle(prices=[10,10,5,5,10,10])
        result = simulate(data, {'family': 'buy_hold'}, fee=0, slippage=0)
        self.assertTrue(result['halted'])
        self.assertEqual(result['trades'][0]['reason'], 'risk_halt')
        self.assertLess(result['equity'], 100)


class GovernorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.registry = Registry(Path(self.temp.name)/'state.sqlite')
    def tearDown(self):
        self.registry.close(); self.temp.cleanup()
    def evidence(self, bot='root', initial=100):
        return {'bot_id': bot, 'source': 'paper_forward_ledger', 'mode': 'PAPER', 'verified_forward': True,
                'external_cashflows': 0, 'open_positions': 0, 'observed_at': datetime.now(timezone.utc).isoformat(),
                'initial_equity': initial, 'equity': initial*10, 'realized_profit': initial*9, 'sessions': 126, 'closed_trades': 30}
    def approve(self, bot):
        self.registry.db.execute("UPDATE bots SET validated=1,status='paper_validated' WHERE id=?", (bot,))

    def test_risk_stops_at_five_percent_before_zero_and_is_latched(self):
        self.assertEqual(self.registry.assess(report(94))['state'], 'paused_risk')
        self.assertEqual(self.registry.assess(report(100))['state'], 'paused_risk')
        self.assertGreater(self.registry.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)

    def test_zero_retires_without_deleting_evidence(self):
        before = len(self.registry.bots())
        decision = self.registry.assess(report(0))
        self.assertEqual(decision['state'], 'retired')
        self.assertFalse(decision['destroy_files'])
        self.assertEqual(len(self.registry.bots()), before)

    def test_live_stale_or_missing_proof_cannot_authorize_risk_actions(self):
        for change in [{'mode':'LIVE'}, {'api_ok':False}, {'observed_at':'2020-01-01T00:00:00+00:00'}, {'observed_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()}]:
            data = report(); data.update(change)
            with self.assertRaises(ValueError): self.registry.assess(data)

    def test_x10_backtest_deposit_unrealised_or_wrong_bot_cannot_reproduce(self):
        self.approve('root')
        for change in [{'mode':'BACKTEST'}, {'external_cashflows':900}, {'open_positions':1}, {'verified_forward':False}, {'bot_id':'other'}, {'realized_profit':1}, {'sessions':1}]:
            data=self.evidence();data.update(change)
            with self.assertRaises(ValueError): self.registry.create_child('root', data)

    def test_unvalidated_parent_cannot_create_children(self):
        with self.assertRaises(ValueError): self.registry.create_child('root', self.evidence())

    def test_bounded_genealogy_does_not_multiply_capacity(self):
        self.approve('root'); child=self.registry.create_child('root', self.evidence())
        self.approve(child); grandchild=self.registry.create_child(child, self.evidence(child,20))
        self.assertAlmostEqual(sum(b['capacity'] for b in self.registry.bots()), 100)
        self.assertEqual(max(b['depth'] for b in self.registry.bots()), 2)
        self.approve(grandchild)
        with self.assertRaises(ValueError): self.registry.create_child(grandchild,self.evidence(grandchild,5))
        self.assertEqual(len(self.registry.bots()), 3)

    def test_same_parent_cannot_reproduce_twice(self):
        self.approve('root'); self.registry.create_child('root',self.evidence())
        with self.assertRaises(ValueError):self.registry.create_child('root',self.evidence())

    def test_holdout_cannot_be_reused_through_another_epoch(self):
        self.registry.consume_holdout('scope','2026-01-01','2026-02-01','one')
        with self.assertRaises(ValueError):self.registry.consume_holdout('scope','2026-01-15','2026-03-01','two')
        self.assertEqual(self.registry.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],1)


class StopGuardTests(unittest.TestCase):
    def test_healthy_simulation_never_issues_stop(self):
        calls=[]
        self.assertEqual(verified_stop_simulation({'state':'research_only'}, runner=lambda *a,**k:calls.append(a)), 'not_required')
        self.assertEqual(calls,[])

    def test_live_engine_or_injected_exchange_key_is_never_stopped(self):
        for env in [['FREQTRADE__DRY_RUN=false'],['FREQTRADE__DRY_RUN=true','FREQTRADE__EXCHANGE__KEY=secret']]:
            calls=[]
            def runner(argv,**kwargs):
                calls.append(argv);return SimpleNamespace(stdout=json.dumps([{'Config':{'Env':env}}]))
            with self.assertRaises(ValueError):verified_stop_simulation({'state':'paused_risk'},runner)
            self.assertEqual(len(calls),1)

    def test_stop_requires_independent_api_proof_and_only_targets_dry_container(self):
        calls=[]
        def runner(argv,**kwargs):
            calls.append(argv);return SimpleNamespace(stdout=json.dumps([{'Config':{'Env':['FREQTRADE__DRY_RUN=true']}}]))
        api=lambda **kw:SimpleNamespace(get=lambda _:dict(dry_run=True,trading_mode='spot',exchange='kraken',stake_currency='EUR'))
        self.assertEqual(verified_stop_simulation({'state':'paused_risk'},runner,api),'simulation_container_stopped_data_preserved')
        self.assertEqual(calls[-1],['docker','stop','--time','15','ai-trading-freqtrade'])


class ResearchProtocolTests(unittest.TestCase):
    def test_changed_frozen_bars_or_instrument_metadata_never_consume_holdout(self):
        for change in ['price', 'volume', 'split', 'lot', 'missing_history']:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                reg=Registry(Path(folder)/'r.sqlite')
                start=datetime(2018,1,1,tzinfo=timezone.utc)
                good={'return_pct':3,'profit':3,'profit_factor':1.5,'max_drawdown_pct':1,
                      'closed_trades':20,'halted':False,'trades':[],'curve':[]}
                def fake(data,spec,**kw):return {**good,'return_pct':0 if spec['family']=='buy_hold' else 3}
                with patch('research_lab.research.simulate',side_effect=fake):
                    cycle(bundle(count=600,start=start),reg,datetime(2019,9,1,tzinfo=timezone.utc))
                later=bundle(count=900,start=start)
                asset=later['assets'][0]
                if change == 'price':asset['bars'][20].update(open=100,high=101,low=99,close=100)
                if change == 'volume':asset['bars'][20]['volume']=9000
                if change == 'split':asset['bars'][20]['split_ratio']=2
                if change == 'lot':asset['lot_size']=0.001
                if change == 'missing_history':asset['bars']=asset['bars'][:300]
                with patch('research_lab.research.simulate') as simulate_mock:
                    result=cycle(later,reg,datetime(2020,7,1,tzinfo=timezone.utc))
                self.assertEqual(result['state'],'frozen_history_changed_new_plan_required')
                self.assertFalse(result['real_money_eligible'])
                simulate_mock.assert_not_called()
                self.assertEqual(reg.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],0)
                reg.close()

    def test_appended_bars_preserve_frozen_data_and_can_use_one_holdout(self):
        with tempfile.TemporaryDirectory() as folder:
            reg=Registry(Path(folder)/'r.sqlite')
            start=datetime(2018,1,1,tzinfo=timezone.utc)
            good={'return_pct':3,'profit':3,'profit_factor':1.5,'max_drawdown_pct':1,
                  'closed_trades':20,'halted':False,'trades':[],'curve':[]}
            def fake(data,spec,**kw):return {**good,'return_pct':0 if spec['family']=='buy_hold' else 3}
            with patch('research_lab.research.simulate',side_effect=fake):
                frozen=cycle(bundle(count=600,start=start),reg,datetime(2019,9,1,tzinfo=timezone.utc))
                result=cycle(bundle(count=900,start=start),reg,datetime(2020,7,1,tzinfo=timezone.utc))
                repeated=cycle(bundle(count=900,start=start),reg,datetime(2020,7,2,tzinfo=timezone.utc))
            self.assertEqual(result['epoch'],frozen['epoch'])
            self.assertEqual(result['state'],'paper_candidate_passed')
            # A later monthly development plan must wait for its own future
            # sessions; it cannot validate again on the consumed holdout.
            self.assertEqual(repeated['state'],'awaiting_future_holdout')
            self.assertEqual(reg.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],1)
            reg.close()

    def test_old_plan_without_verifiable_frozen_prefix_cannot_use_holdout(self):
        with tempfile.TemporaryDirectory() as folder:
            reg=Registry(Path(folder)/'r.sqlite')
            start=datetime(2018,1,1,tzinfo=timezone.utc)
            good={'return_pct':3,'profit':3,'profit_factor':1.5,'max_drawdown_pct':1,
                  'closed_trades':20,'halted':False,'trades':[],'curve':[]}
            def fake(data,spec,**kw):return {**good,'return_pct':0 if spec['family']=='buy_hold' else 3}
            with patch('research_lab.research.simulate',side_effect=fake):
                frozen=cycle(bundle(count=600,start=start),reg,datetime(2019,9,1,tzinfo=timezone.utc))
            row=reg.db.execute('SELECT plan FROM epochs WHERE id=?',(frozen['epoch'],)).fetchone()
            plan=json.loads(row['plan'])
            del plan['frozen_history_count'];del plan['frozen_history_sha256']
            reg.db.execute('UPDATE epochs SET plan=? WHERE id=?',(json.dumps(plan),frozen['epoch']))
            with patch('research_lab.research.simulate') as simulate_mock:
                result=cycle(bundle(count=900,start=start),reg,datetime(2020,7,1,tzinfo=timezone.utc))
            self.assertEqual(result['state'],'frozen_history_verification_required')
            simulate_mock.assert_not_called()
            self.assertEqual(reg.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],0)
            reg.close()

    def test_holdout_is_reserved_before_testing_and_quality_failure_rejects(self):
        with tempfile.TemporaryDirectory() as folder:
            reg=Registry(Path(folder)/'r.sqlite')
            first=bundle(count=600,start=datetime(2018,1,1,tzinfo=timezone.utc))
            first['historical_universe_verified']=False
            good={'return_pct':3,'profit':3,'profit_factor':1.5,'max_drawdown_pct':1,'closed_trades':20,'halted':False,'trades':[],'curve':[]}
            def fake(data,spec,**kw):return {**good,'return_pct':0 if spec['family']=='buy_hold' else 3}
            with patch('research_lab.research.simulate',side_effect=fake):cycle(first,reg,datetime(2019,9,1,tzinfo=timezone.utc))
            later=bundle(count=900,start=datetime(2018,1,1,tzinfo=timezone.utc));later['historical_universe_verified']=False
            def final(data,spec,**kw):
                self.assertEqual(reg.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],1)
                return fake(data,spec,**kw)
            with patch('research_lab.research.simulate',side_effect=final):result=cycle(later,reg,datetime(2020,7,1,tzinfo=timezone.utc))
            self.assertEqual(result['state'],'candidate_rejected')
            self.assertFalse(result['result']['real_money_eligible'])
            reg.close()

    def test_implementation_change_cannot_reuse_old_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            reg=Registry(Path(folder)/'r.sqlite');data=bundle(count=600,start=datetime(2018,1,1,tzinfo=timezone.utc))
            good={'return_pct':3,'profit':3,'profit_factor':1.5,'max_drawdown_pct':1,'closed_trades':20,'halted':False,'trades':[],'curve':[]}
            with patch('research_lab.research.simulate',return_value=good):cycle(data,reg,datetime(2019,9,1,tzinfo=timezone.utc))
            with patch('research_lab.research.implementation_hash',return_value='different'):
                result=cycle(data,reg,datetime(2019,9,2,tzinfo=timezone.utc))
            self.assertEqual(result['state'],'implementation_changed_new_plan_required');reg.close()
    def test_strategy_variants_frozen_once_and_future_holdout_waits(self):
        with tempfile.TemporaryDirectory() as folder:
            reg=Registry(Path(folder)/'r.sqlite'); data=bundle(count=600,start=datetime(2018,1,1,tzinfo=timezone.utc))
            now=datetime(2019,9,1,tzinfo=timezone.utc)
            good={'return_pct':3,'profit':3,'profit_factor':1.5,'max_drawdown_pct':1,'closed_trades':20,'halted':False,'trades':[],'curve':[]}
            def fake(data,spec,**kw):return {**good,'return_pct':0 if spec['family']=='buy_hold' else 3}
            with patch('research_lab.research.simulate',side_effect=fake) as mocked:
                first=cycle(data,reg,now);calls=mocked.call_count
                second=cycle(data,reg,datetime(2019,10,1,tzinfo=timezone.utc))
                self.assertEqual(mocked.call_count,calls)
            self.assertEqual(calls, 1 + 3 * len(TEMPLATES))
            self.assertEqual(first['epoch'],second['epoch'])
            self.assertEqual(second['state'],'awaiting_future_holdout')
            self.assertEqual(reg.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],0)
            reg.close()

    def test_missing_history_never_forces_a_winner(self):
        with tempfile.TemporaryDirectory() as folder:
            reg=Registry(Path(folder)/'r.sqlite'); result=cycle(bundle(count=100),reg)
            self.assertEqual(result['state'],'insufficient_development_history')
            self.assertFalse(result['real_money_eligible']);reg.close()



    def test_position_count_is_unbounded_by_default_but_cash_still_limits_exposure(self):
        data=bundle(count=260)
        base=data['assets'][0]
        data['assets']=[{**base, 'id':f'TOY{i}'} for i in range(12)]
        spec={'family':'buy_hold'}
        result=simulate(data,spec,initial=100,allocation=10,fee=0,slippage=0,risk_control=False)
        self.assertGreaterEqual(result['entry_attempts'], 10)
        self.assertNotIn('max_positions', result)

class PaperBrokerTests(unittest.TestCase):
    def test_paper_sell_can_only_reduce_owned_quantity(self):
        broker,calls=self.broker({'positions':[{'symbol':'TOY','qty':'1','market_value':'10'}]})
        broker.sell_limit('TOY',1,10,'moussa-paper-sell')
        self.assertEqual(calls[-1][2]['side'],'sell')
        broker,calls=self.broker()
        with self.assertRaises(ValueError):broker.sell_limit('TOY',1,10,'moussa-paper-sell')
        self.assertFalse(any(c[0]=='POST' for c in calls))
    def broker(self, overrides=None):
        responses={'orders:by_client_order_id':None,'clock':{'is_open':True},'account':{'cash':'100','status':'ACTIVE','trading_blocked':False,'account_blocked':False,'trade_suspended_by_user':False},
                   'positions':[],'orders':[],'assets/TOY':{'tradable':True,'class':'us_equity','status':'active','fractionable':False}}
        responses.update(overrides or {})
        broker=PaperBroker('private-key','private-secret',['TOY']);calls=[]
        def request(method,path,payload=None,query=None):
            calls.append((method,path,payload));return responses.get(path) if method=='GET' else {'id':'simulated-order'}
        broker._request=request
        return broker,calls

    def test_direct_order_call_cannot_bypass_pending_exposure_or_fraction_limits(self):
        payload={'symbol':'TOY','qty':'1','side':'buy','type':'limit','limit_price':'10',
                 'time_in_force':'day','client_order_id':'moussa-paper-direct'}
        broker,calls=self.broker({'orders':[{'symbol':'TOY','side':'buy','type':'limit','qty':'2','filled_qty':'0','limit_price':'10'}]})
        with self.assertRaises(ValueError):broker.request('POST','orders',payload)
        self.assertFalse(any(c[0]=='POST' for c in calls))
        broker,calls=self.broker();payload['qty']='0.5'
        with self.assertRaises(ValueError):broker.request('POST','orders',payload)
        self.assertEqual(calls,[])

    def test_direct_order_reconciles_identity_and_prevents_double_sell(self):
        payload={'symbol':'TOY','qty':'1','side':'sell','type':'limit','limit_price':'10',
                 'time_in_force':'day','client_order_id':'moussa-paper-direct'}
        broker,calls=self.broker({'positions':[{'symbol':'TOY','qty':'1','market_value':'10'}],
                                  'orders':[{'symbol':'TOY','side':'sell','qty':'1','filled_qty':'0'}]})
        with self.assertRaises(ValueError):broker.request('POST','orders',payload)
        self.assertFalse(any(c[0]=='POST' for c in calls))
        existing={**payload,'id':'existing'}
        broker,calls=self.broker({'orders:by_client_order_id':existing})
        self.assertEqual(broker.request('POST','orders',payload)['id'],'existing')
        self.assertEqual(len(calls),1)

    def test_paper_order_is_limit_long_only_with_identity(self):
        broker,calls=self.broker();broker.buy_limit('TOY',1,10,'moussa-paper-test')
        payload=calls[-1][2]
        self.assertEqual(payload['type'],'limit');self.assertEqual(payload['side'],'buy')
        self.assertEqual(payload['client_order_id'],'moussa-paper-test')

    def test_pending_orders_count_against_shared_limit(self):
        broker,calls=self.broker({'orders':[{'symbol':'TOY','side':'buy','type':'limit','qty':'2','filled_qty':'0','limit_price':'10'}]})
        with self.assertRaises(ValueError):broker.buy_limit('TOY',1,10,'moussa-paper-test')
        self.assertFalse(any(c[0]=='POST' for c in calls))

    def test_retries_reconcile_the_same_client_id_instead_of_resubmitting(self):
        broker,calls=self.broker({'orders:by_client_order_id':{'symbol':'TOY','side':'buy','qty':'1','limit_price':'10','id':'existing'}})
        self.assertEqual(broker.buy_limit('TOY',1,10,'moussa-paper-test')['id'],'existing')
        self.assertEqual(len(calls),1)

    def test_market_closed_excessive_order_and_unsupported_fraction_are_blocked(self):
        for quantity,price,overrides in [(3,10,{}),(1,10,{'clock':{'is_open':False}}),(0.5,10,{})]:
            broker,calls=self.broker(overrides)
            with self.assertRaises(ValueError):broker.buy_limit('TOY',quantity,price,'moussa-paper-test')
            self.assertFalse(any(c[0]=='POST' for c in calls))

    def test_live_host_replacement_and_funding_endpoint_are_forbidden(self):
        broker=PaperBroker('k','s',['TOY']);broker.URL='https://api.alpaca.markets/v2'
        with self.assertRaises(ValueError):broker.request('GET','account')
        broker.URL=PaperBroker.URL
        with self.assertRaises(ValueError):broker.request('POST','funding',{})

    def test_network_error_never_exposes_keys_or_credentials(self):
        def fail(*a,**kw):raise OSError('private-key private-secret')
        broker=PaperBroker('private-key','private-secret',['TOY'],opener=fail)
        with self.assertRaises(RuntimeError) as ctx:broker.request('GET','account')
        self.assertNotIn('private-key',str(ctx.exception));self.assertNotIn('private-secret',str(ctx.exception))

    def test_actual_request_host_is_paper_and_redirect_cannot_select_live(self):
        requests=[]
        def opener(request,**kw):
            requests.append(request)
            return io.BytesIO(b'{"cash":"100"}')
        broker=PaperBroker('k','s',['TOY'],opener=opener)
        broker.request('GET','account')
        self.assertEqual(requests[0].full_url,'https://paper-api.alpaca.markets/v2/account')
        self.assertEqual(requests[0].get_method(),'GET')


class CollectionAndWorkerTests(unittest.TestCase):
    def test_corrupt_or_malformed_daily_marker_recovers_without_losing_risk_report(self):
        for raw in ['broken json', '[]', '{}', '{"day":"invalid","result":{"state":"old"}}']:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                root=Path(folder);(root/'user_data/reports').mkdir(parents=True)
                (root/'user_data/reports/latest.json').write_text(json.dumps(report()))
                (root/'research_state').mkdir()
                marker=root/'research_state/last_daily.json';marker.write_text(raw)
                with patch('sys.stdout',new=io.StringIO()):
                    result=once(root,stop=False,collector=lambda **kw:bundle(count=20))
                self.assertEqual(result['risk']['state'],'research_only')
                self.assertTrue(result['risk']['observation_verified'])
                self.assertTrue(any(e.startswith('crypto_research_marker_') for e in result['errors']))
                self.assertEqual(json.loads(marker.read_text())['result']['state'],'insufficient_development_history')
                self.assertEqual(json.loads((root/'user_data/reports/autonomy.json').read_text())['risk'],result['risk'])

    def test_marker_recovery_failure_is_reported_and_keeps_registry_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'user_data/reports').mkdir(parents=True)
            (root/'user_data/reports/latest.json').write_text(json.dumps(report()))
            (root/'research_state').mkdir()
            reg=Registry(root/'research_state/registry.sqlite')
            reg.consume_holdout('scope','2026-01-01','2026-02-01','reserved');reg.close()
            (root/'research_state/last_daily.json').write_text('broken json')
            with patch('sys.stdout',new=io.StringIO()):
                result=once(root,stop=False,collector=lambda **kw:(_ for _ in ()).throw(OSError('private upstream text')))
            self.assertEqual(result['crypto_research']['state'],'data_unavailable')
            self.assertIn('crypto_research_OSError',result['errors'])
            self.assertNotIn('private upstream text',json.dumps(result))
            self.assertTrue((root/'user_data/reports/autonomy.json').exists())
            reg=Registry(root/'research_state/registry.sqlite')
            self.assertEqual(reg.db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0],1);reg.close()

    def test_failed_latched_stop_retries_with_current_dry_proof_when_report_is_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'user_data/reports').mkdir(parents=True)
            report_file=root/'user_data/reports/latest.json';report_file.write_text(json.dumps(report(94)))
            commands=[]
            def runner(argv,**kw):
                commands.append(argv)
                if argv[1] == 'stop':
                    if sum(command[1]=='stop' for command in commands) == 1:
                        raise RuntimeError('private stop error')
                    return SimpleNamespace(stdout='')
                return SimpleNamespace(stdout=json.dumps([{'State':{'Running':True},'Config':{'Env':['FREQTRADE__DRY_RUN=true']}}]))
            api=lambda **kw:SimpleNamespace(get=lambda _:dict(dry_run=True,trading_mode='spot',exchange='kraken',stake_currency='EUR'))
            guard=lambda decision:verified_stop_simulation(decision,runner,api)
            with patch('sys.stdout',new=io.StringIO()),patch('research_lab.worker.verified_stop_simulation',side_effect=guard):
                first=once(root,collector=lambda **kw:bundle(count=20))
                report_file.write_text('broken json')
                second=once(root,collector=lambda **kw:bundle(count=20))
            self.assertEqual(first['risk']['state'],'paused_risk')
            self.assertTrue(first['risk']['observation_verified'])
            self.assertEqual(first['risk']['stop_result'],'verification_or_stop_failed')
            self.assertNotIn('private stop error',json.dumps(first))
            self.assertFalse(second['risk']['observation_verified'])
            self.assertEqual(second['risk']['state'],'paused_risk')
            self.assertEqual(second['risk']['stop_result'],'simulation_container_stopped_data_preserved')
            self.assertEqual(sum(command[1]=='inspect' for command in commands),2)
            self.assertEqual(sum(command[1]=='stop' for command in commands),2)
            self.assertTrue(all(command[-1]=='ai-trading-freqtrade' for command in commands))

    def test_missing_observation_without_recorded_halt_never_attempts_docker_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);commands=[]
            guard=lambda decision:verified_stop_simulation(decision,runner=lambda *a,**kw:commands.append(a))
            with patch('sys.stdout',new=io.StringIO()),patch('research_lab.worker.verified_stop_simulation',side_effect=guard):
                result=once(root,collector=lambda **kw:bundle(count=20))
            self.assertEqual(result['risk']['state'],'unverified')
            self.assertEqual(result['risk']['stop_result'],'not_required')
            self.assertEqual(commands,[])

    def test_collector_drops_unfinished_candle_and_refuses_closed_revisions(self):
        opened=int(datetime(2022,1,1,tzinfo=timezone.utc).timestamp())
        rows=[[opened+i*86400,'10','11','9','10','10','100',1] for i in range(4)]
        def opener(req,**kw):
            self.assertEqual(req.get_method(),'GET');self.assertTrue(req.full_url.startswith('https://api.kraken.com/0/public/OHLC?'))
            return io.BytesIO(json.dumps({'error':[],'result':{'PAIR':rows,'last':0}}).encode())
        first=fetch_crypto(opener=opener)
        self.assertEqual(len(first['assets'][0]['bars']),3)
        first['assets'][0]['bars'][0]['close']=10.5
        with self.assertRaises(ValueError):fetch_crypto(previous=first,opener=opener)

    def test_worker_runs_research_once_per_day_and_keeps_risk_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'user_data/reports').mkdir(parents=True)
            (root/'user_data/reports/latest.json').write_text(json.dumps(report()))
            calls=[]
            def collector(**kw):calls.append(kw);return bundle(count=20)
            with patch('sys.stdout',new=io.StringIO()):
                first=once(root,stop=False,collector=collector)
                second=once(root,stop=False,collector=collector)
            self.assertEqual(len(calls),1)
            self.assertEqual(second['risk']['state'],'research_only')
            self.assertEqual(first['equities']['state'],'awaiting_broker_data')
            self.assertEqual(first['crypto_research']['state'],'insufficient_development_history')


if __name__=='__main__':unittest.main()
