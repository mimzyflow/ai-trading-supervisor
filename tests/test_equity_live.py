import json,unittest
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from research_lab.equity_live import parse
from research_lab.equity_paper import advance, new_state, summary
class LiveEquityTests(unittest.TestCase):
 def payload(self):
  start=datetime(2025,1,1,14,30,tzinfo=timezone.utc)
  ts=[int((start+timedelta(days=i)).timestamp()) for i in range(400)]
  quote={'open':[10]*400,'high':[11]*400,'low':[9]*400,'close':[10]*400,'volume':[10000]*400}
  return {'chart':{'result':[{'meta':{'symbol':'SOFI','currency':'USD','instrumentType':'EQUITY'},'timestamp':ts,'indicators':{'quote':[quote]}}]}}

 def test_incomplete_current_session_is_excluded(self):
  start=datetime(2025,1,1,14,30,tzinfo=timezone.utc); ts=[]; vals=[]
  for i in range(400):
   d=start+timedelta(days=i); ts.append(int(d.timestamp())); vals.append(10+i*.01)
  payload={'chart':{'result':[{'meta':{'symbol':'SOFI','currency':'USD','instrumentType':'EQUITY'},'timestamp':ts,'indicators':{'quote':[{'open':vals,'high':[x+1 for x in vals],'low':[x-1 for x in vals],'close':vals,'volume':[10000]*len(vals)}]}}]}}
  now=datetime.fromtimestamp(ts[-1],timezone.utc)+timedelta(hours=1)
  a=parse(json.dumps(payload).encode(),'SOFI',now)
  self.assertLess(datetime.fromisoformat(a['bars'][-1]['close_at']),now)

 def test_action_dates_survive_parsing_without_synthetic_accounting(self):
  p=self.payload(); result=p['chart']['result'][0]; split=result['timestamp'][20]; dividend=result['timestamp'][-1]
  result['events']={'splits':{str(split):{'date':split,'numerator':1,'denominator':10,'splitRatio':'1:10'}},
                    'dividends':{str(dividend):{'date':dividend,'amount':.25}}}
  now=datetime.fromtimestamp(dividend,timezone.utc)+timedelta(days=1)
  asset=parse(json.dumps(p).encode(),'SOFI',now)
  self.assertEqual([x['kind'] for x in asset['corporate_actions']],['split','dividend'])
  self.assertEqual(asset['corporate_actions'][0]['date'],'2025-01-21')
  self.assertFalse(asset['corporate_actions_verified'])
  self.assertFalse(asset['price_basis_verified'])
  self.assertFalse(any('split_ratio' in bar or 'dividend_per_share' in bar for bar in asset['bars']))

 def test_malformed_or_unbounded_action_metadata_is_refused(self):
  p=self.payload(); epoch=p['chart']['result'][0]['timestamp'][-1]
  malformed=[None, {'dividends':[]}, {'unknown':{}},
             {'dividends':{str(epoch):{'date':epoch,'amount':True}}},
             {'dividends':{str(epoch):{'date':epoch,'amount':float('inf')}}},
             {'splits':{str(epoch):{'date':epoch,'numerator':1,'denominator':0}}},
             {'splits':{str(epoch):{'date':epoch,'numerator':1,'denominator':10,'splitRatio':'10:1'}}},
             {'splits':{str(epoch):{'date':epoch,'numerator':1,'denominator':10,'splitRatio':'-1:-10'}}},
             {'dividends':{str(epoch+1):{'date':epoch,'amount':.25}}},
             {'dividends':{str(epoch+i):{'date':epoch+i,'amount':.25} for i in range(257)}}]
  for events in malformed:
   with self.subTest(events=repr(events)[:80]):
    payload=deepcopy(p); payload['chart']['result'][0]['events']=events
    with self.assertRaisesRegex(ValueError,'equity_live_invalid_events'):
     parse(json.dumps(payload).encode(),'SOFI',datetime.fromtimestamp(epoch,timezone.utc)+timedelta(days=1))

 def test_new_split_and_dividend_block_paper_without_false_profit(self):
  for kind,event in [('splits',{'numerator':1,'denominator':10,'splitRatio':'1:10'}),
                     ('dividends',{'amount':.25})]:
   with self.subTest(kind=kind):
    payload=self.payload(); result=payload['chart']['result'][0]; epoch=result['timestamp'][-1]
    result['events']={kind:{str(epoch):{'date':epoch,**event}}}
    now=datetime.fromtimestamp(epoch,timezone.utc)+timedelta(days=1)
    asset=parse(json.dumps(payload).encode(),'SOFI',now)
    previous=asset['bars'][-2]['close_at']; state=new_state(now,last_session=previous)
    state['cash']=90
    state['positions']={'SOFI':{'quantity':1,'cost':10,'entry_price':10,'entry_session':previous,'entry_index':398,'highest_price':10}}
    state['trades']=[{'asset':'OLD','profit':2,'reason':'fixed_horizon'}]
    before=deepcopy(state)
    spec={'family':'trend_breakout','fast':2,'slow':3,'breakout':2,'stop_loss':.05,'max_hold':30}
    advance({'assets':[asset]},state,spec,now=now)
    for field in ('cash','initial_cash','equity','positions','trades','last_session'):
     self.assertEqual(state[field],before[field])
    self.assertEqual(summary(state)['state'],'paper_blocked')
    self.assertEqual(summary(state)['blocked_reason'],'corporate_action_requires_review')
if __name__=='__main__': unittest.main()
