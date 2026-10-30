from types import SimpleNamespace
import unittest
from app.ap_shared.bills.working.protections import ProtectionRepository
from app.ap_shared.bills.contracts import SnapshotError
from test_ap_bill_working_policy import I
from test_ap_shared_access import CONFIG

class Query:
    def __init__(self,base,name):self.base,self.name=base,name;self.after=None;self.key='id';self.limit_n=500;self.matches={}
    def select(self,*args):return self
    def eq(self,key,value):self.matches[key]=value;return self
    def gt(self,key,value):self.after=value;return self
    def order(self,key):self.key=key;return self
    def limit(self,n):self.limit_n=n;return self
    def execute(self):
        self.base.clock[0]+=1;self.base.calls.append(self.name)
        rows=self.base.rows[self.name]
        if self.name=='ap_workspaces':rows=[{'bill_protection_epoch':self.base.epoch}]
        rows=[r for r in rows if all(r.get(k,v)==v for k,v in self.matches.items())]
        rows=sorted(rows,key=lambda r:r.get(self.key,''))
        return SimpleNamespace(data=[r for r in rows if self.after is None or r[self.key]>self.after][:self.limit_n])

class Base:
    def __init__(self):
        self.config=CONFIG;self.clock=[0];self.calls=[];self.epoch=0;self.client=SimpleNamespace(table=lambda name:Query(self,name))
        statements=[{'id':f'00000000-0000-4000-8000-{n:012}', 'current_revision_id':f'00000000-0000-4000-8001-{n:012}', 'completed':False} for n in range(20)]
        self.rows={'ap_workspaces':[],'ap_vendor_mappings':[],'ap_statements':statements,'ap_duplicate_reviews':[],'ap_statement_revisions':[dict(id=s['current_revision_id'],statement_id=s['id'],doc={'vendor':'Synthetic','rows':[]},results=[],resolutions={}) for s in statements]}
    def _private_bucket(self):pass
    def _table(self,name):return Query(self,name)
    def _one(self,q):return q.execute().data[0]
    def import_info(self,*args):return {'state':'ready'}

class ProtectionPreparationTests(unittest.TestCase):
    def test_collection_yields_resumes_and_reuses_immutable_revision_keys(self):
        base=Base();state={};snapshot=None;attempts=0
        for _ in range(30):
            before=base.clock[0];attempts+=1
            repo=ProtectionRepository(base,lambda _:None,state=state,monotonic=lambda:base.clock[0])
            try:snapshot=repo.snapshot(I,'auth',deadline=before+5)
            except SnapshotError as error:self.assertEqual(error.code,'bill_range_loading')
            self.assertLessEqual(base.clock[0]-before,6,'Collection exceeded its cooperative request budget')
            if snapshot is not None:break
        self.assertIsNotNone(snapshot);self.assertGreater(attempts,1)
        self.assertEqual(base.calls.count('ap_statement_revisions'),20)
        base.epoch+=1;base.calls=[]
        for _ in range(10):
            try:snapshot=repo.snapshot(I,'auth',deadline=base.clock[0]+5);break
            except SnapshotError as error:self.assertEqual(error.code,'bill_range_loading')
        else:self.fail('New epoch did not finish')
        self.assertEqual(snapshot['epoch'],1)
        self.assertNotIn('ap_statement_revisions',base.calls,'Unchanged immutable revisions were fetched again')
