from datetime import date
from contextlib import closing
import gzip
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from fixtures.ap_shared.duplicate_cases import bill
import test_ap_bill_working_builds as build_fixtures
from app.ap_shared.bills.duplicates.scan import DuplicateScan

try:
    from app.ap_shared.bills.working.context import HistoryContext
except ImportError:
    HistoryContext = None


class WorkingContextTests(unittest.TestCase):
    def test_frozen_context_matches_complete_source_and_survives_source_close(self):
        self.assertIsNotNone(HistoryContext,'Compact full-source vendor context is not implemented')
        rows=[bill(f'INV{1000+n:06}',amount=1000+n,invoice_date='2025-10-20',status='PaidInFull',reportedAmountDue=0) for n in range(24)]
        rows += [bill(f'INV{900000+n}',amount=88888,invoice_date=f'2025-10-{20+n%6:02}',status='PaidInFull',reportedAmountDue=0) for n in range(10)]
        rows += [bill('INV451234',amount=88888,invoice_date='2025-11-01',status='PaidInFull',reportedAmountDue=0),
                 bill('INV45124',amount=88888,invoice_date='2025-11-02',status='PaidInFull',reportedAmountDue=0)]
        source=build_fixtures.source_db(rows)
        full=sqlite3.connect(':memory:')
        engine=DuplicateScan(full,dict(importId=build_fixtures.I,importVersion=1,sourceDigest='a'*64,storageFormat='snapshot-v2',recordCount=len(rows)),time.monotonic)
        engine.ingest([dict(ordinal=n,bill=r) for n,r in enumerate(rows)]);engine.finish_input()
        patterns=engine.vendor_candidates.patterns
        def profile(vendor,month):
            for _ in range(1000):
                value=patterns.advance(vendor,month)
                if value is not None:return value
            self.fail('Full-source profile did not finish')
        def recurrence(vendor,amount,day):
            for _ in range(1000):
                value=patterns.recurrence(vendor,amount,day)
                if value is not None:return value
            self.fail('Full-source recurrence did not finish')
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=build_fixtures.build(source,rows,Path(folder)/'build');source.close();source=None
                context_path=Path(folder)/'context.sqlite'
                with gzip.open(result['contextArchivePath'],'rb') as packed:context_path.write_bytes(packed.read())
                with closing(sqlite3.connect(context_path)) as context_db:
                    context=HistoryContext(context_db)
                    for day in [date(2025,10,29),date(2025,10,30),date(2025,11,1),date(2025,11,2)]:
                        month=day.replace(day=1).toordinal()
                        self.assertEqual(context.profile('synthetic foods',month),profile('synthetic foods',month))
                        self.assertEqual(context.recurring('synthetic foods',88888,day.toordinal()),recurrence('synthetic foods',88888,day.toordinal()))
                    self.assertTrue(context.recurring('synthetic foods',88888,date(2025,11,1).toordinal()))
                    with self.assertRaises(ValueError):context.profile('missing vendor',date(2025,11,1).toordinal())
                    with self.assertRaises(ValueError):context.recurring('synthetic foods',12,date(2025,11,1).toordinal())
        finally:
            if source:source.close()
            full.close()


if __name__=='__main__':unittest.main()
