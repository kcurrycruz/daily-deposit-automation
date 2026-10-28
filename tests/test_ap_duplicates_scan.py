import json
import sqlite3
import time
import unittest
from unittest.mock import patch
from fixtures.ap_shared.duplicate_cases import bill, changed, PIN


class DuplicateScanTests(unittest.TestCase):
    def scan(self, bills, probes=10000):
        from app.ap_shared.bills.duplicates.scan import DuplicateScan
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        engine = DuplicateScan(db, {**PIN, 'recordCount': len(bills)}, time.monotonic)
        for at in range(0, len(bills), 5000):
            engine.ingest([dict(ordinal=n, bill=bills[n]) for n in range(at, min(at + 5000, len(bills)))])
        engine.finish_input()
        calls = 0
        last_probes = 0
        while True:
            progress = engine.step(time.monotonic() + 5, max_probes=probes)
            self.assertLessEqual(progress['probes'] - last_probes, probes)
            last_probes = progress['probes']
            calls += 1
            if progress['done']:
                break
            self.assertLess(calls, max(100, len(bills) * 10))
        summary = engine.finish()
        return db, engine, summary, calls

    def test_recurring_different_day_swaps_are_not_fetched_as_candidates(self):
        # Existing exact/stem/swap queries plus bounded v3 profile/cross lookups.
        # No different-day digit-swap finding or unbounded amount-bucket work.
        rows = [bill('1234', amount=10000), bill('1243', amount=10000, invoice_date='2026-10-02')]
        _, _, report, _ = self.scan(rows, probes=1)
        self.assertEqual(report['findingCount'], 0)
        self.assertLessEqual(report['probes'], 30)

    def test_same_day_swaps_remain_visible(self):
        db, _, report, _ = self.scan([bill('1234', amount=10000), bill('1243', amount=10000)], probes=1)
        self.assertEqual(report['findingCount'], 1)
        self.assertEqual(json.loads(db.execute('select reasons from findings').fetchone()[0]), ['digit_transposition'])

    def test_exact_reference_checks_remain_visible_across_dates(self):
        for amount, classification in [(10000, 'exact_pattern'), (10001, 'amount_difference')]:
            with self.subTest(amount=amount):
                rows = [bill('REF1234', amount=10000),
                        bill('REF 1234', amount=amount, invoice_date='2026-12-01')]
                db, _, report, _ = self.scan(rows, probes=1)
                self.assertEqual(report['findingCount'], 1)
                self.assertEqual(db.execute('select classification from findings').fetchone()[0], classification)

    def test_suffix_swap_and_amount_difference_are_direct_pairs(self):
        rows = [bill('271712'), bill('271712X'), bill('888812'), bill('888821'),
                bill('9000', amount=500), bill('9000', amount=501)]
        db, _, report, _ = self.scan(rows, probes=2)
        findings = db.execute('select classification,reasons from findings order by id').fetchall()
        self.assertEqual(report['findingCount'], 3)
        self.assertEqual(sorted(r[0] for r in findings), ['amount_difference', 'possible_duplicate', 'possible_duplicate'])
        self.assertEqual(db.execute('select count(*) from members').fetchone()[0], 6)

    def test_ambiguous_ten_thousand_rows_produce_one_group_not_cartesian_pairs(self):
        db, _, report, calls = self.scan([changed(bill(), id=str(i), sourceRows=str(i + 2)) for i in range(10000)], probes=500)
        self.assertEqual(report['findingCount'], 1)
        self.assertEqual(db.execute('select classification,member_count from findings').fetchone(), ('export_review', 10000))
        self.assertEqual(db.execute('select count(*) from members').fetchone()[0], 10000)
        self.assertGreater(calls, 1)
        self.assertLess(report['probes'], 50000)

    def test_equal_amount_bucket_does_not_scan_all_pairs(self):
        _, _, report, _ = self.scan([bill(f'UNRELATED-{i:06d}', invoice_date='') for i in range(10000)])
        self.assertEqual(report['findingCount'], 0)
        self.assertLess(report['probes'], 200000)

    def test_chain_does_not_invent_a_third_edge(self):
        # A and B differ by the suffix rule. B and C differ by a digit swap;
        # A and C differ by both, so there is no direct A-C evidence.
        db, _, report, _ = self.scan([bill('1234'), bill('1234X'), bill('1243X')], probes=1)
        self.assertEqual(report['findingCount'], 2)
        pairs = [tuple(x[0] for x in db.execute('select ordinal from members where finding_id=? order by ordinal', (r[0],)))
                 for r in db.execute('select id from findings')]
        self.assertEqual(sorted(pairs), [(0, 1), (1, 2)])

    def test_source_row_order_and_payment_fields_do_not_reset_finding_key(self):
        a = [bill(), bill('271712X')]
        first, _, _, _ = self.scan(a)
        key = first.execute('select key from findings').fetchone()[0]
        second, _, _, _ = self.scan([changed(x, sourceRows='999', reportedPaidAmount=100) for x in reversed(a)])
        self.assertEqual(second.execute('select key from findings').fetchone()[0], key)

    def test_incomplete_input_and_finding_limit_never_claim_completion(self):
        from app.ap_shared.bills.duplicates.scan import DuplicateScan
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        engine = DuplicateScan(db, PIN, time.monotonic)
        engine.ingest([dict(ordinal=0, bill=bill())])
        with self.assertRaises(ValueError):
            engine.finish_input()
        with patch('app.ap_shared.bills.duplicates.scan.MAX_FINDINGS', 1), self.assertRaises(ValueError):
            self.scan([bill('1234'), bill('1234X'), bill('1243X')])

    def test_safely_consolidated_bill_is_not_its_own_duplicate(self):
        import io
        from app.ap_shared.bills.parser import CsvStage
        from app.ap_shared.bills.index import SnapshotIndex
        from fixtures.ap_shared.bill_exports import export
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        csv = export([{'Total Line Items': '2', 'Bill Line Item Order': '0', 'Bill Line Item Amount': '100.00'},
                      {'Total Line Items': '2', 'Bill Line Item Order': '1', 'Bill Line Item Amount': '38.00'}])
        parser = CsvStage(db, io.StringIO(csv)); parser.read_step()
        index = SnapshotIndex(db)
        while not index.consolidate_step()['done']:
            pass
        index.finish()
        bills = [json.loads(x[0]) for x in db.execute('select record from bill_records')]
        self.assertEqual(len(bills), 1)
        _, _, report, _ = self.scan(bills)
        self.assertEqual(report['findingCount'], 0)

    def test_expired_step_deadline_does_not_skip_unprocessed_candidates(self):
        from app.ap_shared.bills.duplicates.scan import DuplicateScan
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        engine = DuplicateScan(db, PIN, lambda: 10)
        engine.ingest([dict(ordinal=0, bill=bill()), dict(ordinal=1, bill=bill('271712X'))])
        engine.finish_input()
        self.assertFalse(engine.step(9)['done'])
        while not engine.step(20)['done']:
            pass
        self.assertEqual(engine.finish()['findingCount'], 1)

    def test_ingestion_yields_at_deadline_and_resumes_every_record(self):
        from app.ap_shared.bills.duplicates.scan import DuplicateScan
        now=[0]
        def clock():
            now[0]+=1
            return now[0]
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        engine=DuplicateScan(db,{**PIN,'recordCount':5},clock)
        rows=[dict(ordinal=n,bill=bill('REF'+str(n))) for n in range(5)]
        consumed=engine.ingest(rows,deadline=3)
        self.assertGreater(consumed,0);self.assertLess(consumed,5)
        self.assertEqual(engine.read,consumed)
        engine.ingest(rows[consumed:],deadline=100)
        engine.finish_input()
        self.assertEqual(engine.read,5)
