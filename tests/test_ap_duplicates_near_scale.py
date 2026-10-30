import json,subprocess,sys,unittest
class NearScaleTests(unittest.TestCase):
 sizes=(223425,500000)
 def test_new_rule_sizes_are_bounded_and_repeatable(self):
  for count in self.sizes:
   with self.subTest(records=count):
    try:result=subprocess.run([sys.executable,'-X','utf8','tests/fixtures/ap_shared/duplicate_scale_check.py','--records',str(count),'--near','--progress'],stdout=subprocess.PIPE,text=True,timeout=1200)
    except subprocess.TimeoutExpired as error:
     self.fail('Numeric scan exceeded 1200s; see phase diagnostics above.')
    self.assertEqual(result.returncode,0,'Synthetic helper failed; see diagnostics above.');r=json.loads(result.stdout);print(json.dumps(r,sort_keys=True),file=sys.stderr)
    self.assertEqual(r['ruleVersion'],'bill-duplicates-v5');self.assertEqual(r['recordCount'],count)
    self.assertTrue(r['repeatKeysStable']);self.assertEqual(r['findingCount'],3);self.assertEqual(r['visibleFindingCount'],1);self.assertEqual(r['excludedExactReferenceCount'],2)
    self.assertLessEqual(r['maxRecordsPerStep'],5000);self.assertLessEqual(r['maxProbesPerStep'],10000);self.assertLess(r['maxStepSeconds'],6)
    self.assertLess(r['peakRssIncreaseBytes'],268435456);self.assertLessEqual(r['expandedBytes'],536870912);self.assertLessEqual(r['compressedBytes'],33554432)
