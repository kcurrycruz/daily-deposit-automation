import sqlite3,time,unittest
from fixtures.ap_shared.duplicate_cases import bill,PIN
from app.ap_shared.bills.duplicates.rules import classify
from app.ap_shared.bills.duplicates.scan import DuplicateScan

class DigitTypoTests(unittest.TestCase):
 def scan(self,rows,rule='bill-duplicates-v5',probes=1):
  db=sqlite3.connect(':memory:');self.addCleanup(db.close)
  pin={**PIN,'recordCount':len(rows),**({'ruleVersion':rule} if rule=='bill-duplicates-v5' else {})}
  engine=DuplicateScan(db,pin,time.monotonic);engine.ingest([dict(ordinal=n,bill=r) for n,r in enumerate(rows)]);engine.finish_input()
  while not engine.step(time.monotonic()+5,max_probes=probes)['done']:pass
  return db,engine.finish()
 def test_single_digit_change_same_vendor_amount_and_day_is_new_rule_only(self):
  for a,b in [('261398','261399'),('AB1-238','AB1-239'),('0008','0009')]:
   first,second=bill(a),bill(b)
   self.assertIsNone(classify(first,second))
   result=classify(first,second,rule_version='bill-duplicates-v5')
   self.assertEqual(result['classification'],'possible_duplicate');self.assertIn('single_digit_substitution',result['reasons'])
   db,summary=self.scan([first,second]);self.assertEqual(summary['findingCount'],1)
   self.assertEqual(db.execute('select count(*) from members').fetchone()[0],2)
 def test_different_dates_amounts_vendors_unknown_dates_and_currency_conflicts_do_not_qualify(self):
  a=bill('261398')
  for changes in [dict(invoiceDate='2026-10-02'),dict(invoiceDate=''),dict(invoiceDate='invalid'),dict(amount=1),dict(vendor='Other'),dict(currency='CAD')]:
   b={**bill('261399'),**changes};self.assertIsNone(classify(a,b,rule_version='bill-duplicates-v5'))
   if changes.get('invoiceDate')=='invalid':
    with self.assertRaises(ValueError):self.scan([a,b])
   else:
    _,summary=self.scan([a,b]);self.assertEqual(summary['findingCount'],0)
  for ref in ['261489','0261398','26139X','261-399','18']:
   self.assertIsNone(classify(a,bill(ref),rule_version='bill-duplicates-v5'))
 def test_legacy_scan_and_daily_sequential_references_keep_their_behavior(self):
  rows=[bill('261398'),bill('261399')]
  _,report=self.scan(rows,rule='bill-duplicates-v3');self.assertEqual(report['findingCount'],0)
  _,report=self.scan([bill(str(261390+n),invoice_date=f'2026-10-{1+n:02}') for n in range(10)])
  self.assertEqual(report['findingCount'],0)
 def test_source_warnings_remain_export_review_and_order_preserves_key(self):
  rows=[bill('261398'),{**bill('261399'),'sourceIssues':'Synthetic ambiguous source'}]
  first,_=self.scan(rows);second,_=self.scan(list(reversed(rows)))
  self.assertEqual(first.execute('select classification from findings').fetchone()[0],'export_review')
  self.assertEqual(first.execute('select key from findings').fetchone(),second.execute('select key from findings').fetchone())
 def test_many_digits_and_small_probe_steps_are_bounded_and_stable(self):
  a='INV'+'0'*120+'8';b=a[:-1]+'9';db,summary=self.scan([bill(a),bill(b)],probes=1)
  self.assertEqual(summary['findingCount'],1);self.assertLess(summary['probes'],200)

 def test_scoped_near_rule_has_the_same_pair_and_original_ids(self):
  import tempfile,gzip,json
  from pathlib import Path
  import test_ap_bill_working_builds as f
  from test_ap_duplicates_working_scope import pin_for
  from app.ap_shared.bills.working.context import HistoryContext
  rows=[bill('261398'),bill('261399')];source=f.source_db(rows);self.addCleanup(source.close)
  with tempfile.TemporaryDirectory() as folder:
   built=f.build(source,rows,Path(folder)/'working',mode='all');mf=f.manifest_for_built(built)
   context_path=Path(folder)/'context.sqlite';context_path.write_bytes(gzip.decompress(built['contextArchivePath'].read_bytes()))
   context_db=sqlite3.connect(context_path);db=sqlite3.connect(':memory:')
   try:
    pin={**pin_for(mf),'ruleVersion':'bill-duplicates-v6'};engine=DuplicateScan(db,pin,time.monotonic)
    engine.ingest([dict(ordinal=n,sourceOrdinal=n,bill={**r,'id':f'{pin["importId"]}:{n}'}) for n,r in enumerate(rows)]);engine.finish_input()
    engine.vendor_candidates.patterns.context=HistoryContext(context_db)
    while not engine.step(time.monotonic()+5)['done']:pass
    self.assertEqual(engine.finish()['findingCount'],1)
    self.assertEqual(db.execute('select source_ordinal from source_map order by ordinal').fetchall(),[(0,),(1,)])
    self.assertIn('single_digit_substitution',json.loads(db.execute('select reasons from findings').fetchone()[0]))
    from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter,DuplicateArtifactCache
    backup=sqlite3.connect(Path(folder)/'scan.sqlite');db.backup(backup);backup.close()
    writer=DuplicateArtifactWriter(Path(folder)/'scan.sqlite',Path(folder)/'scope.gz')
    try:
     while not writer.step()['done']:pass
     info=writer.info
    finally:writer.close()
    manifest={**info,'key':f'{f.W}/bill-duplicates/v3/{pin["importId"]}/bill-duplicates-v6/{info["hash"]}.sqlite.gz'}
    cache=DuplicateArtifactCache(None)
    try:
     checked=cache._open(Path(folder)/'scope.sqlite',manifest)
     try:self.assertTrue(all(isinstance(fp,str) and len(fp)==64 for fp, in checked.execute('select fp from members')))
     finally:checked.close()
    finally:cache.close()
   finally:db.close();context_db.close()

 def test_numeric_lookup_work_grows_linearly_with_input(self):
  class WorkConnection(sqlite3.Connection):
   work=0
   def set_progress_handler(self,callback,count):
    if callback is None:return super().set_progress_handler(None,0)
    def measured():self.work+=100;return callback()
    return super().set_progress_handler(measured,100)
  def measure(size):
   db=sqlite3.connect(':memory:',factory=WorkConnection);self.addCleanup(db.close)
   rows=[bill(f'INV{n:08}',amount=10000+n%17,vendor=f'Synthetic {n%64:02}') for n in range(size)]
   e=DuplicateScan(db,{**PIN,'recordCount':len(rows),'ruleVersion':'bill-duplicates-v5'},time.monotonic)
   e.ingest([dict(ordinal=n,bill=r) for n,r in enumerate(rows)]);e.finish_input()
   while not e.step(time.monotonic()+5)['done']:pass
   self.assertEqual(e.finish()['findingCount'],0);return db.work
  small=measure(1000);large=measure(2000)
  self.assertLess(large,small*2.3)
 def test_numeric_candidate_queries_are_batched_and_reuse_verified_profiles(self):
  class Counted(sqlite3.Connection):
   calls=0
   def execute(self,*args,**kw):self.calls+=1;return super().execute(*args,**kw)
  db=sqlite3.connect(':memory:',factory=Counted);self.addCleanup(db.close)
  rows=[bill(f'INV{n:08}',amount=10000+n%17,vendor=f'Synthetic {n%64:02}') for n in range(1000)]
  e=DuplicateScan(db,{**PIN,'recordCount':len(rows),'ruleVersion':'bill-duplicates-v5'},time.monotonic)
  e.ingest([dict(ordinal=n,bill=r) for n,r in enumerate(rows)]);e.finish_input();db.calls=0
  while not e.step(time.monotonic()+5)['done']:pass
  self.assertEqual(e.finish()['findingCount'],0);self.assertLess(db.calls,4500)
 def test_batched_candidates_keep_all_existing_and_new_pair_rules(self):
  rows=[bill('261398'),bill('261399'),bill('261389'),bill('261398X'),bill('261398',amount=222),bill('261398',invoice_date='2026-05-02'),bill('261398',invoice_date=''),bill('261398',currency='EUR'),bill('26-1398'),bill('26-1399')]
  expected={tuple([a,b]) for a in range(len(rows)) for b in range(a+1,len(rows)) if classify(rows[a],rows[b],rule_version='bill-duplicates-v5') is not None}
  db,_=self.scan(rows)
  actual={tuple(n for n, in db.execute('select ordinal from members where finding_id=? order by ordinal',(ident,))) for ident, in db.execute('select id from findings')}
  self.assertEqual(actual,expected)
 def test_finding_key_keeps_full_fingerprints_and_unrelated_refs_do_not_match(self):
  from app.ap_shared.bills.duplicates.rules import bill_fingerprint,finding_key
  rows=[bill('261398'),bill('261399'),bill('UNRELATED'),bill('OTHER')]
  db,summary=self.scan(rows);self.assertEqual(summary['findingCount'],1)
  expected=finding_key([[bill_fingerprint(r),1] for r in rows[:2]],'possible_duplicate',[],rule_version='bill-duplicates-v5')
  self.assertEqual(db.execute('select key from findings').fetchone()[0],expected)
