import json,sqlite3,time,unittest
import httpx
from fixtures.ap_shared.duplicate_cases import bill,PIN
import test_ap_duplicates_source as source_f
import test_ap_duplicates_exclusions as exclusion_f
from test_ap_shared_repository import BackendTransport,make_repository,IMPORT
from test_ap_shared_access import CONFIG
from app.ap_shared.repository import ApStoreError

class BulkTransport(BackendTransport):
 def respond(self,request):
  if request.url.path.endswith('/ap_bill_records') and request.url.params.get('ordinal','').startswith('in.'):
   self.requests.append(request);p=request.url.params
   assert p['workspace_id']=='eq.'+CONFIG.workspace_id and p['import_id']=='eq.'+IMPORT
   ns=[int(n) for n in p['ordinal'][4:-1].split(',')]
   values=[dict(ordinal=n,record=bill(str(n))) for n in sorted(ns)]
   if self.gap:values=values[:-1]
   return httpx.Response(200,json=values)
  return super().respond(request)

class LegacyMemberTests(unittest.TestCase):
 def test_actual_legacy_reader_batches_fifty_groups_inside_one_budget(self):
  s=source_f.SourceTests();self.addCleanup(s.doCleanups);reader,_,db,base=s.fixture(True)
  rows=[bill(f'INV{n//2:05}') for n in range(100)]
  db.execute('delete from bill_records');db.executemany('insert into bill_records values(?,?)',[(n,json.dumps(row)) for n,row in enumerate(rows)])
  reader.ops.repository.source(PIN['importId'])['record_count']=100
  now=[0.0];calls=[0,0]
  def page(workspace,ident,after,limit):
   calls[0]+=1;now[0]+=.1;last=min(after+limit,99)
   return dict(importId=ident,recordCount=100,nextCursor=last if last<99 else None,records=[{**rows[n],'id':f'{ident}:{n}'} for n in range(after+1,last+1)])
  def bulk(workspace,ident,ordinals):
   calls[1]+=1;now[0]+=.1
   return dict(importId=ident,recordCount=100,records=[{**rows[n],'id':f'{ident}:{n}'} for n in ordinals])
  base.records_page=page;base.records_members=bulk
  e=exclusion_f.ExclusionTests();self.addCleanup(e.doCleanups)
  h,local,artifact,_,_,_=e.fixture(rows,groups=[[n,n+1] for n in range(0,100,2)],clock=lambda:now[0]);h.source=reader
  self.assertTrue(h.advance(local,artifact,{},reader.pin(None),None,5))
  self.assertEqual(calls,[0,1]);self.assertLess(now[0],5);self.assertEqual(local.execute('select count(*) from exact_reference_exclusions').fetchone()[0],50)
 def test_bulk_query_is_private_complete_and_preserves_requested_order(self):
  transport=BulkTransport();repo=make_repository(transport)
  result=repo.records_members(CONFIG.workspace_id,IMPORT,[80,2,9])
  self.assertEqual(result['recordCount'],1001);self.assertEqual(result['importId'],IMPORT)
  self.assertEqual([v['id'] for v in result['records']],[f'{IMPORT}:{n}' for n in [80,2,9]])
  self.assertEqual(sum(r.url.path.endswith('/ap_bill_records') for r in transport.requests),1)
  transport.gap=True
  with self.assertRaises(ApStoreError):repo.records_members(CONFIG.workspace_id,IMPORT,[2,9])
 def test_malformed_or_foreign_requests_do_not_read_records(self):
  from uuid import uuid4
  transport=BulkTransport();repo=make_repository(transport)
  with self.assertRaises(PermissionError):repo.records_members(str(uuid4()),IMPORT,[0])
  self.assertEqual(transport.requests,[])
  for values in [[],list(range(101)),[0,0],[True],[1001]]:
   with self.assertRaises(ApStoreError):repo.records_members(CONFIG.workspace_id,IMPORT,values)
  self.assertFalse(any(r.url.path.endswith('/ap_bill_records') for r in transport.requests))
