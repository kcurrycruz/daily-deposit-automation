import json
from pathlib import Path
import subprocess
import sys
import unittest

class WorkingScaleTests(unittest.TestCase):
    def test_supported_active_range_sizes_in_fresh_processes(self):
        helper=Path('tests/fixtures/ap_shared/bill_working_scale_check.py')
        self.assertTrue(helper.is_file(),'The active range release checker has not been implemented')
        for count,mode in [(223425,'last_12_months'),(500000,'all')]:
            with self.subTest(records=count,mode=mode):
                result=subprocess.run([sys.executable,'-X','utf8',str(helper),'--records',str(count),'--mode',mode],capture_output=True,text=True,timeout=1200)
                self.assertEqual(result.returncode,0,result.stderr[-3000:])
                report=json.loads(result.stdout);print(json.dumps(report,sort_keys=True),file=sys.stderr)
                self.assertEqual(report['fullRecordCount'],count)
                self.assertTrue(report['sourceUnchanged']);self.assertTrue(report['contextParity']);self.assertTrue(report['warmReadsWithoutDownload'])
                self.assertLess(report['maxStepSeconds'],6)
                self.assertLess(report['peakRssIncreaseBytes'],268435456)
                self.assertLessEqual(report['indexExpandedBytes']+report['contextExpandedBytes'],536870912)
                if mode=='all':self.assertEqual(report['activeCount'],count)
                else:self.assertLess(report['activeCount'],count//5)
