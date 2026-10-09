import hashlib,json,unittest,tempfile
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from research_lab.equity_live import parse, collect
from research_lab.equity_paper import advance, new_state, summary
from scripts.collect_equity_paper import run
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
class RecentQuoteRepairTests(unittest.TestCase):
 def setUp(self):
  self.primary={}
  for symbol in ('SOFI','U','PLUG'):
   payload=LiveEquityTests.payload(self)
   payload['chart']['result'][0]['meta']['symbol']=symbol
   self.primary[symbol]=payload
  self.recent=deepcopy(self.primary['U'])
  result=self.recent['chart']['result'][0]
  last=result['timestamp'][-1]
  result['timestamp']=[last+300*i for i in range(78)]
  result['indicators']['quote'][0]={'open':[10]*78,'high':[11]*78,'low':[9]*78,'close':[10]*78,'volume':[100]*78}
  self.now=datetime.fromtimestamp(last,timezone.utc)+timedelta(days=1)
  self.calls=[]

 def invalid(self,symbol='U',index=-1):
  self.primary[symbol]['chart']['result'][0]['indicators']['quote'][0]['low'][index]=10.5

 def opener(self,request,timeout):
  self.assertEqual(timeout,12)
  url=request.full_url; self.calls.append(url)
  symbol=url.split('/chart/')[1].split('?')[0]
  payload=self.recent if 'range=5d&' in url else self.primary[symbol]
  if 'range=5d&' in url and symbol != 'U':
   payload=deepcopy(payload); payload['chart']['result'][0]['meta']['symbol']=symbol
  raw=json.dumps(payload).encode()
  class Response:
   status=200
   def __enter__(self): return self
   def __exit__(self,*args): pass
   def geturl(self): return url
   def read(self,maximum): return raw[:maximum]
  return Response()

 def collect(self,symbols=('SOFI','U')):
  with patch('research_lab.equity_live.SYMBOLS',symbols):
   return collect(self.now,self.opener)

 def test_valid_history_needs_no_secondary_request(self):
  bundle=self.collect()
  self.assertEqual(len(self.calls),2)
  self.assertTrue(all('repair' not in s for s in bundle['provenance']['sources']))

 def test_recent_bad_quote_is_replaced_exactly_and_provenance_is_retained(self):
  self.invalid()
  original=parse(json.dumps(self.primary['U']).encode(),'U',self.now)
  bundle=self.collect(); repaired=bundle['assets'][1]
  expected=parse(json.dumps(self.primary['SOFI']).encode(),'SOFI',self.now)['bars'][-1]
  self.assertEqual(repaired['bars'][-1],expected)
  self.assertEqual(repaired['bars'][:-1],original['bars'][:-1])
  source=bundle['provenance']['sources'][1]
  self.assertEqual(source['sha256'],hashlib.sha256(json.dumps(self.primary['U']).encode()).hexdigest())
  self.assertEqual(source['repair']['sha256'],hashlib.sha256(json.dumps(self.recent).encode()).hexdigest())
  self.assertEqual(source['repair']['sessions'],[repaired['bars'][-1]['close_at']])
  self.assertEqual(source['repair']['method'],'verified_intraday_extrema')
  self.assertEqual(source['repair']['fields'],{repaired['bars'][-1]['close_at']:['low']})
  self.assertEqual(repaired['bars'][-1]['volume'],10000)
  self.assertLess(repaired['bars'][-1]['low'],repaired['bars'][-1]['open'])
  self.assertEqual(len(self.calls),3)
  self.assertIn('events=div%2Csplits',source['url'])
  self.assertNotIn('events=',source['repair']['url'])

 def test_bad_secondary_is_refused_and_previous_bundle_remains_unchanged(self):
  self.invalid()
  self.recent['chart']['result'][0]['indicators']['quote'][0]['low'][-1]=10.5
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder); (root/'research_state').mkdir()
   previous=root/'research_state/equities.bundle.json'; previous.write_text('{"evidence":true}')
   status=run(root,self.now,lambda _:self.collect())
   self.assertEqual(status['state'],'unavailable')
   self.assertEqual(status['error_code'],'equity_recent_repair_invalid_intraday')
   self.assertEqual(previous.read_text(),'{"evidence":true}')

 def test_old_bad_history_is_not_rewritten(self):
  self.invalid(index=20)
  with self.assertRaisesRegex(ValueError,'equity_recent_repair_outside_window'): self.collect()
  self.assertFalse(any('range=5d&' in url for url in self.calls))

 def test_missing_or_unclosed_secondary_session_does_not_skip_bad_day(self):
  self.invalid()
  for future in (False,True):
   with self.subTest(future=future):
    payload=deepcopy(self.recent); result=payload['chart']['result'][0]
    if future: result['timestamp']=[t+2*86400 for t in result['timestamp']]
    else:
     result['timestamp']=result['timestamp'][:-1]
     result['indicators']['quote'][0]={k:v[:-1] for k,v in result['indicators']['quote'][0].items()}
    old=self.recent; self.recent=payload
    try:
     with self.assertRaisesRegex(ValueError,'equity_recent_repair_missing_session'): self.collect()
    finally: self.recent=old

 def test_wrong_secondary_identity_is_refused(self):
  self.invalid(); self.recent['chart']['result'][0]['meta']['currency']='EUR'
  with self.assertRaisesRegex(ValueError,'equity_live_identity'): self.collect()

 def test_event_mismatch_prevents_repair(self):
  self.invalid(); result=self.recent['chart']['result'][0]; epoch=result['timestamp'][0]
  result['events']={'dividends':{str(epoch):{'date':epoch,'amount':.25}}}
  with self.assertRaisesRegex(ValueError,'equity_recent_repair_events_mismatch'): self.collect()

 def test_zero_volume_is_not_repaired(self):
  self.primary['U']['chart']['result'][0]['indicators']['quote'][0]['volume'][-1]=0
  with self.assertRaisesRegex(ValueError,'zero_volume_session_requires_review'): self.collect()
  self.assertFalse(any('range=5d&' in url for url in self.calls))

 def test_recovery_requests_have_a_per_collection_budget(self):
  for symbol in ('SOFI','U','PLUG'): self.invalid(symbol)
  with self.assertRaisesRegex(ValueError,'equity_recent_repair_budget_exceeded'):
   self.collect(('SOFI','U','PLUG'))
  self.assertEqual(len(self.calls),5)
  self.assertEqual(sum('range=5d&' in url for url in self.calls),2)

 def test_changed_open_close_or_unchanged_extreme_is_not_repaired(self):
  self.invalid()
  for key,index,value in [('open',0,10.1),('close',-1,10.1),('high',20,11.1),('volume',20,10000)]:
   with self.subTest(key=key):
    payload=deepcopy(self.recent); payload['chart']['result'][0]['indicators']['quote'][0][key][index]=value
    old=self.recent; self.recent=payload
    try:
     with self.assertRaisesRegex(ValueError,'equity_recent_repair_quotes_mismatch'):self.collect()
    finally:self.recent=old

 def test_duplicate_or_zero_volume_intraday_bar_is_refused(self):
  self.invalid()
  for duplicate in (False,True):
   with self.subTest(duplicate=duplicate):
    payload=deepcopy(self.recent); result=payload['chart']['result'][0]
    if duplicate:result['timestamp'][20]=result['timestamp'][19]
    else:result['indicators']['quote'][0]['volume'][20]=0
    old=self.recent; self.recent=payload
    try:
     with self.assertRaises(ValueError):self.collect()
    finally:self.recent=old

if __name__=='__main__': unittest.main()
