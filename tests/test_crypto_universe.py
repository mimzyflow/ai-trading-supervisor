import io, json, unittest
from research_lab.crypto_universe import discover_eur_universe

class R(io.BytesIO):
    status=200
    def __init__(self, payload, url): super().__init__(json.dumps(payload).encode()); self.url=url
    def geturl(self): return self.url
class Opener:
    def __init__(self): self.calls=[]
    def __call__(self, request, timeout=0):
        self.calls.append(request.full_url)
        if 'AssetPairs' in request.full_url:
            result={f'X{i}EUR':{'wsname':f'C{i}/EUR','status':'online'} for i in range(15)}
            result['USDTEUR']={'wsname':'USDT/EUR','status':'online'}
        else:
            result={f'X{i}EUR':{'c':[str(i+1)],'v':['1',str(100-i)]} for i in range(15)}
        return R({'error':[],'result':result}, request.full_url)
class Tests(unittest.TestCase):
    def test_scans_all_then_ranks_without_return_data(self):
        op=Opener(); result=discover_eur_universe(op, 12)
        self.assertEqual(result['evaluated_pairs'],15)
        self.assertEqual(len(result['selected']),12)
        self.assertFalse(result['return_data_used_for_selection'])
        self.assertTrue(all(x['id']!='USDT/EUR' for x in result['selected']))
        self.assertEqual(len(op.calls),2)
    def test_limit_is_bounded(self):
        with self.assertRaises(ValueError): discover_eur_universe(Opener(), 30)
if __name__=='__main__': unittest.main()
