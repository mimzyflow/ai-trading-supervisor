import json,unittest
from datetime import datetime,timezone,timedelta
from research_lab.equity_live import parse
class LiveEquityTests(unittest.TestCase):
 def test_incomplete_current_session_is_excluded(self):
  start=datetime(2025,1,1,14,30,tzinfo=timezone.utc); ts=[]; vals=[]
  for i in range(400):
   d=start+timedelta(days=i); ts.append(int(d.timestamp())); vals.append(10+i*.01)
  payload={'chart':{'result':[{'meta':{'symbol':'SOFI','currency':'USD','instrumentType':'EQUITY'},'timestamp':ts,'indicators':{'quote':[{'open':vals,'high':[x+1 for x in vals],'low':[x-1 for x in vals],'close':vals,'volume':[10000]*len(vals)}]}}]}}
  now=datetime.fromtimestamp(ts[-1],timezone.utc)+timedelta(hours=1)
  a=parse(json.dumps(payload).encode(),'SOFI',now)
  self.assertLess(datetime.fromisoformat(a['bars'][-1]['close_at']),now)
if __name__=='__main__': unittest.main()
