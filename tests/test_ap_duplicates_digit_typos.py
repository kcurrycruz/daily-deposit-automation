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
   finally:db.close();context_db.close()
