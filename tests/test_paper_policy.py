import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from supervisor.paper_policy import read_policy, advice, POLICY_ID, PIN
from supervisor.loss_alerts import update
from research_lab.governor import Registry
from research_lab.equity_paper import new_state, advance
from scripts.activate_paper_policy import activate, rollback
from research_lab.fx import validate_fx, URL

ROOT=Path(__file__).resolve().parents[1]


class PaperPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=datetime.now(timezone.utc)
        self.policy=json.loads((ROOT/'simulation-policy.json').read_text())
        (self.root/'simulation-policy.json').write_text(json.dumps(self.policy))

    def test_advice_changes_sizing_and_exits_only_for_current_authorized_policy(self):
        source={'schema_version':1,'generated_at':self.now.isoformat(),'policy_id':POLICY_ID,
                'upstream_commit':PIN,'can_trade':False,'budget_eur':0,
                'analyses':[{'ticker':'CRYPTO-EUR','state':'complete','as_of':self.now.isoformat(),'rating':'Buy'}]}
        path=self.root/'tradingagents.json'
        for rating,multiplier,exit in [('Buy',2,False),('Underweight',.5,False),('Sell',0,True)]:
            source['analyses'][0]['rating']=rating;path.write_text(json.dumps(source))
            result=advice(self.root,'CRYPTO-EUR',self.now,self.policy)
            self.assertEqual(result['stake_multiplier'],multiplier);self.assertEqual(result['exit'],exit)
        for change in [{'policy_id':'old'},{'generated_at':(self.now+timedelta(minutes=1)).isoformat()},
                       {'generated_at':(self.now-timedelta(hours=37)).isoformat()},{'can_trade':True}]:
            path.write_text(json.dumps({**source,**change}))
            self.assertEqual(advice(self.root,'CRYPTO-EUR',self.now,self.policy)['state'],'fallback')

    def test_explicit_authorization_preserves_old_events_and_rolls_back_state(self):
        (self.root/'research_state').mkdir();(self.root/'user_data').mkdir()
        (self.root/'user_data/config.dryrun.json').write_text((ROOT/'user_data/config.dryrun.json').read_text())
        registry=Registry(self.root/'research_state/registry.sqlite')
        registry.db.execute("UPDATE bots SET status='paused_risk' WHERE id='root'")
        registry.event('risk_state',{'equity':94.7907});registry.close()
        before=activate(self.root)
        self.assertEqual(before['status'],'paused_risk');self.assertIsNone(activate(self.root))
        registry=Registry(self.root/'research_state/registry.sqlite')
        self.assertEqual(registry.db.execute('select count(*) from events').fetchone()[0],2)
        report={'schema_version':2,'observed_at':self.now.isoformat(),'mode':'DRY-RUN',
                'api_ok':True,'database_ok':True,'configuration_safe':True,
                'starting_balance_eur':100,'equity_eur':15,'equity_peak_eur':100}
        self.assertEqual(registry.assess(report,self.now,loss_limit=None)['state'],'monitoring_only')
        report['equity_eur']=0
        self.assertEqual(registry.assess(report,self.now,loss_limit=None)['state'],'capital_exhausted')
        self.assertEqual(registry.assess(report,self.now,loss_limit=None)['state'],'capital_exhausted')
        registry.close();rollback(self.root,before)
        registry=Registry(self.root/'research_state/registry.sqlite')
        self.assertEqual(registry.db.execute("select status from bots where id='root'").fetchone()[0],'paused_risk')
        self.assertEqual(registry.db.execute('select count(*) from events').fetchone()[0],3);registry.close()

    def test_eighty_five_percent_fall_has_no_stop_and_can_recover_without_replay(self):
        dates=[self.now-timedelta(days=3-i) for i in range(3)]
        bars=[{'open_at':(d-timedelta(hours=6)).isoformat(),'close_at':d.isoformat(),
               'open':p,'high':p,'low':p,'close':p,'volume':1000} for d,p in zip(dates,[10,1.5,10])]
        bundle={'assets':[{'id':'TEST','bars':bars}]}
        state=new_state(self.now,last_session=bars[0]['close_at']);state['cash']=0
        state['positions']['TEST']={'quantity':10,'cost':100,'entry_price':10,'highest_price':10,
            'entry_session':bars[0]['close_at'],'held_sessions':0,'held_as_of':bars[0]['close_at']}
        spec={'family':'trend_breakout','fast':10,'slow':50,'breakout':10,'stop_loss':.08,'max_hold':30}
        advance(bundle,state,spec,fee=0,min_commission=0,slippage=0,now=dates[1],max_drawdown=None,loss_stops=False)
        self.assertEqual(state['equity'],15);self.assertFalse(state['halted']);self.assertEqual(state['trades'],[])
        advance(bundle,state,spec,fee=0,min_commission=0,slippage=0,now=self.now,max_drawdown=None,loss_stops=False)
        self.assertEqual(state['equity'],100);self.assertEqual(state['max_drawdown_pct'],85)
        self.assertEqual(state['trades'],[])

    def test_alert_is_durable_deduplicated_and_never_halts(self):
        report={'api_ok':True,'database_ok':True,'equity_eur':15,'research':{}}
        first=update(report,self.root,self.now,self.policy)
        second=update(report,self.root,self.now+timedelta(minutes=5),self.policy)
        self.assertEqual(first,second);self.assertEqual(first[0]['loss_level_pct'],85)
        self.assertEqual(first[0]['action'],'notify_only');self.assertNotIn('halted',report)

    def test_fx_requires_dated_reference_and_has_no_one_to_one_default(self):
        value={'source':URL,'rate_at':self.now.isoformat(),'usd_per_eur':1.1206}
        self.assertEqual(validate_fx(value,self.now)['usd_per_eur']*100,112.06)
        for value in [{**value,'rate_at':(self.now-timedelta(days=5)).isoformat()},{**value,'usd_per_eur':True}]:
            with self.assertRaises(ValueError):validate_fx(value,self.now)

    def test_crypto_callbacks_refuse_live_and_veto_loss_stops(self):
        baseline=types.ModuleType('MoussaBaseline');baseline.MoussaBaseline=type('Baseline',(),{})
        from supervisor import paper_policy
        with patch.dict(sys.modules,{'MoussaBaseline':baseline,'paper_policy':paper_policy}):
            spec=importlib.util.spec_from_file_location('market_room_strategy_test',ROOT/'user_data/strategies/MoussaMarketRoom.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        bot=module.MoussaMarketRoom();bot.config={'dry_run':True,'trading_mode':'spot'};bot.bot_start()
        args=dict(pair='XBT/EUR',trade=None,order_type='limit',amount=1,rate=1,time_in_force='GTC',current_time=self.now)
        self.assertFalse(bot.confirm_trade_exit(exit_reason='stop_loss',**args))
        self.assertTrue(bot.confirm_trade_exit(exit_reason='exit_signal',**args))
        bot.config['dry_run']=False
        with self.assertRaises(ValueError):bot.bot_start()

    def test_model_market_context_rejects_future_stale_and_invalid_prices(self):
        from integrations.tradingagents_runner import market_features
        bar = {'close_at': self.now.isoformat(), 'close': 10}
        bundle = {'observed_at': self.now.isoformat(), 'currency': 'USD',
                  'assets': [{'id': 'TEST', 'bars': [dict(bar) for _ in range(21)]}]}
        self.assertEqual(market_features(bundle, self.now)[0]['return_20_sessions_pct'], 0)
        for stamp in [self.now + timedelta(seconds=1), self.now - timedelta(days=5)]:
            bundle['assets'][0]['bars'][-1]['close_at'] = stamp.isoformat()
            self.assertEqual(market_features(bundle, self.now), [])
        bundle['assets'][0]['bars'][-1]['close_at'] = self.now.isoformat()
        for price in [True, 0, float('nan')]:
            bundle['assets'][0]['bars'][-1]['close'] = price
            self.assertEqual(market_features(bundle, self.now), [])
