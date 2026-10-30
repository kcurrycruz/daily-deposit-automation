import unittest
from fixtures.ap_shared.duplicate_cases import PIN
from app.ap_shared.bills.duplicates import contracts as c

class NearContractTests(unittest.TestCase):
 def test_old_and_new_pin_versions_are_distinct_and_scope_bound(self):
  self.assertEqual(c.rule_for_pin(c.validate_pin(PIN)),'bill-duplicates-v3')
  near={**PIN,'ruleVersion':'bill-duplicates-v5'}
  self.assertEqual(c.rule_for_pin(c.validate_pin(near)),'bill-duplicates-v5')
  for rule in ['bill-duplicates-v6','bill-duplicates-v3','invented']:
   with self.assertRaises(ValueError):c.validate_pin({**PIN,'ruleVersion':rule})
 def test_new_full_manifest_preserves_old_format_and_owned_rule_path(self):
  rule='bill-duplicates-v5';mf=dict(format='bill-duplicates-v2',ruleVersion=rule,sourceDigest='a'*64,importId=PIN['importId'],key=f'{PIN["importId"]}/bill-duplicates/v2/{PIN["importId"]}/{rule}/'+ 'b'*64+'.sqlite.gz',hash='b'*64,bytes=50,expandedHash='c'*64,expandedBytes=4096,findingCount=1,recordCount=2)
  self.assertEqual(c.validate_manifest(mf),mf)
  with self.assertRaises(ValueError):c.validate_manifest({**mf,'ruleVersion':'bill-duplicates-v6'})
 def test_repository_feature_flag_selects_new_pin_without_changing_source(self):
  import test_ap_duplicates_repository as f
  from app.ap_shared.bills.duplicates.repository import DuplicateRepository
  repo=DuplicateRepository(f.make_repository(f.DuplicateTransport()))
  before=repo.current();home=repo._home;repo._home=lambda:{**home(),'duplicate_near_schema_version':1}
  self.assertEqual(repo.current(),{**before,'ruleVersion':'bill-duplicates-v5'})

 def test_scoped_source_adopts_the_enabled_new_rule(self):
  import test_ap_bill_working_operations as f
  from app.ap_shared.bills.duplicates.source import DuplicateSource
  from types import SimpleNamespace
  harness=f.WorkingOperationsTests();harness.setUp();self.addCleanup(harness.doCleanups)
  harness.repo._home['duplicate_near_schema_version']=1
  job=harness.begin();harness.prepare(job);harness.activate(job)
  source=DuplicateSource(SimpleNamespace(config=harness.repo.config),harness.bill_ops,working=harness.ops)
  pin=source.pin(harness.auth);self.assertEqual(pin['ruleVersion'],'bill-duplicates-v6')
  self.assertEqual(c.rule_for_pin(c.validate_pin(pin)),'bill-duplicates-v6')
  with self.assertRaises(ValueError):c.validate_pin({**pin,'ruleVersion':'bill-duplicates-v5'})
 def test_new_full_artifact_roundtrip_and_rule_label_are_bound(self):
  import json,sqlite3,tempfile,time
  from pathlib import Path
  from app.ap_shared.bills.duplicates.scan import DuplicateScan
  from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter,DuplicateArtifactCache
  from fixtures.ap_shared.duplicate_cases import bill
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'scan.sqlite';db=sqlite3.connect(path);pin={**PIN,'ruleVersion':'bill-duplicates-v5'}
   engine=DuplicateScan(db,pin,time.monotonic);engine.ingest([dict(ordinal=n,bill=bill(ref)) for n,ref in enumerate(['271712','271712X'])]);engine.finish_input()
   while not engine.step(time.monotonic()+5)['done']:pass
   engine.finish();db.close()
   writer=DuplicateArtifactWriter(path,Path(folder)/'result.gz')
   try:
    while not writer.step()['done']:pass
    info=writer.info
   finally:writer.close()
   mf={**info,'key':f'{PIN["importId"]}/bill-duplicates/v2/{PIN["importId"]}/bill-duplicates-v5/{info["hash"]}.sqlite.gz'}
   self.assertEqual(c.validate_manifest(mf)['ruleVersion'],'bill-duplicates-v5')
   cache=DuplicateArtifactCache(None)
   try:
    checked=cache._open(Path(folder)/'result.sqlite',mf);checked.close()
    wrong={**mf,'ruleVersion':'bill-duplicates-v3','key':mf['key'].replace('/bill-duplicates-v5/','/bill-duplicates-v3/')}
    with self.assertRaises(ValueError):cache._open(Path(folder)/'result.sqlite',wrong)
   finally:cache.close()
