from datetime import date
import sqlite3
import time
import unittest
from fixtures.ap_shared.duplicate_cases import bill,PIN

class CompactHistoryTests(unittest.TestCase):
    def test_profiles_and_recurrence_equal_full_scanner_without_storing_candidate_payloads(self):
        from app.ap_shared.bills.working.history import TrainingHistory
        from app.ap_shared.bills.duplicates.scan import DuplicateScan
        rows=[bill(f'INV{n:08}',amount=13800,invoice_date=f'2025-09-{1+n%28:02}') for n in range(300)]
        rows.extend([rows[0],{**rows[1],'sourceIssues':'Synthetic ambiguity'},{**bill('CREDIT',amount=-100),'kind':'credit'}])
        full=sqlite3.connect(':memory:');compact=sqlite3.connect(':memory:')
        try:
            scanner=DuplicateScan(full,{**PIN,'recordCount':len(rows)},time.monotonic)
            training=TrainingHistory(compact,len(rows),time.monotonic)
            items=[dict(ordinal=n,bill=value) for n,value in enumerate(rows)]
            scanner.ingest(items);scanner.finish_input();training.ingest(items);training.finish_input()
            patterns=scanner.vendor_candidates.patterns
            for month in [date(2025,10,1).toordinal(),date(2025,11,1).toordinal()]:
                expected=None;actual=None
                while expected is None:expected=patterns.advance('synthetic foods',month)
                while actual is None:actual=training.patterns.advance('synthetic foods',month)
                self.assertEqual(actual,expected)
            for day in [date(2025,10,1).toordinal(),date(2025,10,2).toordinal()]:
                expected=None;actual=None
                while expected is None:expected=patterns.recurrence('synthetic foods',13800,day)
                while actual is None:actual=training.patterns.recurrence('synthetic foods',13800,day)
                self.assertEqual(actual,expected)
            self.assertNotIn('preview',[r[1] for r in compact.execute('pragma table_info(nodes)')])
            self.assertLess(compact.execute('pragma page_count').fetchone()[0],full.execute('pragma page_count').fetchone()[0])
        finally:full.close();compact.close()
