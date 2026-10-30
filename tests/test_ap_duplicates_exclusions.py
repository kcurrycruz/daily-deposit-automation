from contextlib import closing
import sqlite3,time,unittest
from types import SimpleNamespace
from fixtures.ap_shared.duplicate_cases import bill,PIN
from app.ap_shared.bills.duplicates.rules import bill_fingerprint
from app.ap_shared.bills.duplicates.scan import DuplicateScan

class ExclusionTests(unittest.TestCase):
 def fixture(self,rows,groups=None,clock=time.monotonic):
  from app.ap_shared.bills.duplicates.exclusions import ExactReferenceExclusions
  artifact=sqlite3.connect(':memory:');local=sqlite3.connect(':memory:');self.addCleanup(artifact.close);self.addCleanup(local.close)
  artifact.executescript('create table findings(id integer primary key,key text,member_count integer);create table members(finding_id integer,ordinal integer,fp text,primary key(finding_id,ordinal));')
  rows=[{**r,'id':f'{PIN["importId"]}:{n}'} for n,r in enumerate(rows)]
  for n,group in enumerate(groups or [list(range(len(rows)))]):
   artifact.execute('insert into findings values(?,?,?)',(n,f'{n:064x}',len(group)))
   artifact.executemany('insert into members values(?,?,?)',[(n,i,bill_fingerprint(rows[i])) for i in group])
  local.execute('create table findings(id integer primary key,key text,member_count integer)')
  local.executemany('insert into findings values(?,?,?)',artifact.execute('select * from findings'))
  calls=[]
  def members(pin,ordinals,auth):calls.append(ordinals);return [dict(ordinal=i,bill=rows[i]) for i in ordinals]
  source=SimpleNamespace(members=members,ops=SimpleNamespace(_check=lambda _:None))
  helper=ExactReferenceExclusions(source,clock=clock);helper.initialize(local)
  return helper,local,artifact,source,calls,{**PIN,'recordCount':len(rows)}
 def run_all(self,f):
  h,local,artifact,source,calls,pin=f
  for _ in range(100):
   if h.advance(local,artifact,{},pin,None,time.monotonic()+5):break
  else:self.fail('exclusions did not complete')
  return [key for key, in local.execute('select key from exact_reference_exclusions')]
 def test_identical_and_different_amount_date_exact_groups_are_excluded(self):
  for rows in [[bill('N2609-61636')]*3,[bill('N2609-61636'),bill('n2609-61636',amount=99,invoice_date='2025-01-01')]]:
   self.assertEqual(len(self.run_all(self.fixture(rows))),1)
 def test_later_different_member_and_meaningful_reference_differences_stay_visible(self):
  for other in [bill('OTHER'),bill('N2609-61636',vendor='Other vendor'),bill('N2609-61636X'),bill('0N2609-61636'),bill('N260961636')]:
   self.assertEqual(self.run_all(self.fixture([bill('N2609-61636'),bill('N2609-61636'),other])),[])
 def test_partial_or_swapped_source_evidence_cannot_exclude(self):
  for mode in ['partial','fingerprint','id']:
   f=self.fixture([bill(),bill()]);h,local,artifact,source,calls,pin=f;original=source.members
   def corrupt(pin,ordinals,auth):
    values=original(pin,ordinals,auth)
    if mode=='partial':return values[:-1]
    values[-1]['bill']={**values[-1]['bill'],('amount' if mode=='fingerprint' else 'id'):(1 if mode=='fingerprint' else 'foreign:0')};return values
   source.members=corrupt
   with self.assertRaises(ValueError):self.run_all(f)
   self.assertEqual(local.execute('select count(*) from exact_reference_exclusions').fetchone()[0],0)
 def test_deadline_resumes_without_excluding_partially_verified_group(self):
  now=[0.0];f=self.fixture([bill()]*301,clock=lambda:now[0]);h,local,artifact,source,calls,pin=f;original=source.members
  def slow(*args):out=original(*args);now[0]+=1;return out
  source.members=slow
  self.assertFalse(h.advance(local,artifact,{},pin,None,0));self.assertEqual(calls,[])
  self.assertFalse(h.advance(local,artifact,{},pin,None,1));self.assertEqual(local.execute('select count(*) from exact_reference_exclusions').fetchone()[0],0)
  self.assertTrue(h.advance(local,artifact,{},pin,None,20));self.assertEqual(len(calls),4);self.assertTrue(all(len(c)<=100 for c in calls))

 def test_interrupted_write_resumes_without_losing_previously_verified_exclusions(self):
  f=self.fixture([bill('FIRST'),bill('FIRST'),bill('SECOND'),bill('SECOND')],groups=[[0,1],[2,3]])
  h,local,artifact,source,calls,pin=f
  class Interrupted:
   def __init__(self):self.inserts=0
   def execute(self,sql,args=()):
    if sql.startswith('insert into exact_reference_exclusions'):
     self.inserts+=1
     if self.inserts==2:raise sqlite3.OperationalError('interrupted')
    return local.execute(sql,args)
   def commit(self):return local.commit()
  wrapped=Interrupted()
  with self.assertRaises(sqlite3.OperationalError):h.advance(wrapped,artifact,{},pin,None,time.monotonic()+5)
  local.rollback()
  self.assertTrue(h.advance(wrapped,artifact,{},pin,None,time.monotonic()+5))
  self.assertEqual(local.execute('select count(*) from exact_reference_exclusions').fetchone()[0],2)

 def test_source_members_are_batched_across_small_groups(self):
  rows=[bill(f'INV{n//2:05}') for n in range(200)];groups=[[n,n+1] for n in range(0,200,2)]
  f=self.fixture(rows,groups=groups);self.assertEqual(len(self.run_all(f)),100)
  self.assertEqual(len(f[4]),2);self.assertTrue(all(len(page)<=100 for page in f[4]))
