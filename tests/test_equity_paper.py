import tempfile, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from research_lab.equity_paper import new_state, advance, save, load, summary

class EquityPaperTests(unittest.TestCase):
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
if __name__=='__main__': unittest.main()
