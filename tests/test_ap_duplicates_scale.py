import json
from pathlib import Path
import subprocess
import sys
import unittest


class DuplicateScaleTests(unittest.TestCase):
    def test_supported_record_counts_in_fresh_processes(self):
        helper=Path('tests/fixtures/ap_shared/duplicate_scale_check.py')
        self.assertTrue(helper.is_file(), 'The release scale checker has not been implemented')
        for count in (223425,500000):
            with self.subTest(records=count):
                result=subprocess.run([sys.executable,'-X','utf8',str(helper),'--records',str(count)],
                                      capture_output=True,text=True,timeout=1200)
                self.assertEqual(result.returncode,0,result.stderr[-2000:])
                report=json.loads(result.stdout)
                print(json.dumps(report,sort_keys=True),file=sys.stderr)
                self.assertEqual(report['recordCount'],count)
                self.assertEqual(report['findingCount'],2)
                self.assertTrue(report['repeatKeysStable'])
                self.assertLessEqual(report['maxRecordsPerStep'],5000)
                self.assertLessEqual(report['maxProbesPerStep'],10000)
                # One second permits scheduler/I/O jitter around the cooperative
                # five-second deadline, not an unbounded whole-export operation.
                self.assertLess(report['maxStepSeconds'],6)
                self.assertLess(report['peakRssIncreaseBytes'],268435456)
                self.assertLessEqual(report['expandedBytes'],536870912)
                self.assertLessEqual(report['compressedBytes'],33554432)
