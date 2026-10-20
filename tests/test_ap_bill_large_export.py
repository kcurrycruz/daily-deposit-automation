import json
from pathlib import Path
import subprocess
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch
from test_ap_shared_access import CONFIG


class BillLargeExportTests(unittest.TestCase):
    def test_streaming_limits_reject_without_truncating(self):
        import io,gzip,sqlite3,tempfile
        from app.ap_shared.bills.parser import CsvStage
        from app.ap_shared.bills.index import SnapshotIndex
        from app.ap_shared.bills.archive import verify_csv_archive,IndexArchiveWriter
        with sqlite3.connect(':memory:') as db,patch('app.ap_shared.bills.parser.MAX_SOURCE_ROWS',2):
            parser=CsvStage(db,io.StringIO('vendor,invoiceNumber,amount\nSynthetic,1,1\nSynthetic,2,1\nSynthetic,3,1\n'))
            with self.assertRaises(ValueError):parser.read_step()
        with sqlite3.connect(':memory:') as db,patch('app.ap_shared.bills.index.MAX_RECORDS',2):
            parser=CsvStage(db,io.StringIO('vendor,invoiceNumber,amount\nSynthetic,1,1\nSynthetic,2,1\nSynthetic,3,1\n'));parser.read_step()
            index=SnapshotIndex(db)
            with self.assertRaises(ValueError):index.consolidate_step()
        with tempfile.TemporaryDirectory(prefix='ap-bill-bounds-') as folder:
            target=Path(folder)/'expanded';source=Path(folder)/'source';source.write_bytes(b'x'*100)
            with patch('app.ap_shared.bills.archive.MAX_SOURCE_BYTES',99),self.assertRaises(ValueError):
                verify_csv_archive(io.BytesIO(gzip.compress(b'x'*100)),target)
            with patch('app.ap_shared.bills.archive.MAX_ARCHIVE_BYTES',1),self.assertRaises(ValueError):
                verify_csv_archive(io.BytesIO(gzip.compress(b'x'*100)),target)
            writer=IndexArchiveWriter(source,Path(folder)/'packed')
            try:
                with patch('app.ap_shared.bills.archive.MAX_INDEX_BYTES',99),self.assertRaises(ValueError):writer.step()
            finally:writer.close()

    def test_representative_large_export_in_a_fresh_process(self):
        result = subprocess.run([sys.executable, '-X', 'utf8', 'tests/fixtures/ap_shared/bill_scale_check.py',
                                 '--synthetic-records', '223425'], capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout)
        self.assertEqual(report['recordCount'], 223425)
        self.assertEqual(report['activeRecordCountAfterRepeat'], 223425)
        self.assertEqual(report['originalHash'], report['decompressedArchiveHash'])
        self.assertLess(report['peakRssIncreaseBytes'], 256 * 1024 * 1024)
        self.assertLessEqual(report['maxSourceRowsPerStep'], 5000)
        self.assertLessEqual(report['indexArchiveBytes'], 32 * 1024 * 1024)
        self.assertLessEqual(report['expandedIndexBytes'], 512 * 1024 * 1024)
        self.assertEqual(report['deepQueryCandidateCount'], 223425)

    def test_configurable_bucket_budget_is_validated(self):
        from app.ap_shared.models import read_config, ApValidationError
        cfg = dict(password=CONFIG.password,supabase_url=CONFIG.supabase_url,
                   supabase_secret_key=CONFIG.supabase_secret_key,workspace_id=CONFIG.workspace_id,bucket=CONFIG.bucket)
        self.assertEqual(read_config({'ap':cfg}).bill_storage_budget_bytes, 900000000)
        self.assertEqual(read_config({'ap':{**cfg,'bill_storage_budget_bytes':200000000}}).bill_storage_budget_bytes, 200000000)
        for bad in [True,'900000000',0,-1,9000000001]:
            with self.subTest(value=bad),self.assertRaises(ApValidationError):
                read_config({'ap':{**cfg,'bill_storage_budget_bytes':bad}})

    def test_storage_reservation_uses_configured_budget(self):
        from test_ap_bill_storage import BillTransport
        from test_ap_shared_repository import make_repository
        from app.ap_shared.bills.repository import BillRepository
        transport=BillTransport();base=make_repository(transport)
        base.config=replace(base.config,bill_storage_budget_bytes=200000000)
        repo=BillRepository(base)
        from uuid import uuid4
        repo.reserve(transport.job['id'],1000,str(uuid4()))
        request=next(r for r in transport.requests if r.url.path.endswith('/rpc/ap_bill_quota_reserve'))
        self.assertEqual(json.loads(request.content)['p_data']['budget_bytes'],200000000)
