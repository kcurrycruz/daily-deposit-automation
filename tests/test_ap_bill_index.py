import importlib
import io
import json
import sqlite3
import subprocess
import unittest
from fixtures.ap_shared.bill_exports import export
from app.ap_shared.bills.parser import CsvStage

IMPORT_ID = '00000000-0000-4000-8000-000000000001'


class BillIndexTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module('app.ap_shared.bills.index')
        except ModuleNotFoundError:
            self.fail('Indexed BILL snapshot builder has not been implemented')

    def build(self, source):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        parser = CsvStage(db, io.StringIO(source, newline=''))
        while not parser.read_step(deadline=float('inf'))['done']:
            pass
        index = self.api.SnapshotIndex(db)
        while not index.consolidate_step(max_groups=2, deadline=float('inf'))['done']:
            pass
        index.finish()
        return db, index

    def test_complete_line_group_collapses_once_without_summing_bill_totals(self):
        db, index = self.build(export([{'Total Line Items': '2', 'Bill Line Item Amount': '100.00'},
                                       {'Total Line Items': '2', 'Bill Line Item Order': '1', 'Bill Line Item Amount': '38.00'}]))
        records = [json.loads(r[0]) for r in db.execute('select record from bill_records')]
        self.assertEqual(len(records), 1); self.assertEqual(records[0]['amount'], 13800)
        self.assertEqual(records[0]['sourceRows'], '2,3')
        self.assertEqual(index.finish()['counts']['collapsedRowCount'], 1)

    def test_identical_single_line_bills_stay_ambiguous(self):
        db, index = self.build(export([{}, {}]))
        self.assertEqual(db.execute('select count(*) from bill_records').fetchone()[0], 2)
        self.assertEqual(index.finish()['counts']['warningCount'], 2)

    def test_native_and_template_results_match_existing_importer(self):
        sources = [export([{}]), export([{}, {'Invoice Date': '10/02/2026'}]), export([{}, {}]),
                   export([{'Amount': 'bad'}, {'Active?': 'Inactive'}, {'Vendor Name': ''}]),
                   export([{'Total Line Items': '2', 'Bill Line Item Amount': '140.00'},
                           {'Total Line Items': '2', 'Bill Line Item Order': '1', 'Bill Line Item Amount': '-2.00'}]),
                   export([{'Status': '?'}, {'Invoice Date': 'invalid'}, {'Bill Line Item Order': '1'}]),
                   'vendor,invoiceNumber,amount,clearedPaymentAmount\nSynthetic,00042,138.00,10.00\n']
        for source in sources:
            with self.subTest(source=source[:30]):
                db, index = self.build(source)
                oracle = subprocess.run(['node', 'tests/fixtures/ap_shared/bill_parser_oracle.mjs'], input=source,
                                        capture_output=True, encoding='utf8', check=True)
                expected = json.loads(oracle.stdout)
                self.assertEqual([json.loads(r[0]) for r in db.execute('select record from bill_records order by ordinal')], expected['records'])
                details = index.finish()['counts']
                self.assertEqual(details['sourceRowCount'], expected['summary']['inputRows'])
                self.assertEqual(details['excludedRowCount'], expected['summary']['excludedRows'])
                self.assertEqual(details['collapsedRowCount'], expected['summary']['collapsedRows'])
                actual = [dict(rows=r[0], reason=r[1]) for r in db.execute('select source_rows,reason from bill_warnings order by id')]
                self.assertEqual(actual, expected['summary']['issues'])

    def test_candidate_page_has_total_digest_and_complete_cursor(self):
        _, index = self.build(export([{'Invoice #': str(i)} for i in range(7)]))
        query = dict(importId=IMPORT_ID, references=[dict(invoiceKey='0', kind='invoice')],
                     amounts=[dict(vendorKey='synthetic & co.', kind='invoice', amount=13800)])
        first = index.candidates_page(query, -1, 3, 100000)
        self.assertEqual(first['total'], 7); self.assertEqual(len(first['records']), 3)
        self.assertEqual(first['records'][0]['id'], IMPORT_ID + ':0')
        self.assertEqual(first['nextCursor'], 2)
        second = index.candidates_page(query, 2, 3, 100000)
        self.assertEqual(second['queryDigest'], first['queryDigest'])
        self.assertEqual(second['records'][0]['invoiceNumber'], '3')
        final = index.candidates_page(query, 5, 3, 100000)
        self.assertIsNone(final['nextCursor']); self.assertEqual(len(final['records']), 1)

    def test_candidate_page_respects_bytes_before_row_limit(self):
        _, index = self.build(export([{'Invoice #': str(i)} for i in range(7)]))
        query = dict(importId=IMPORT_ID, references=[], amounts=[dict(vendorKey='synthetic & co.', kind='invoice', amount=13800)])
        page = index.candidates_page(query, -1, 500, 2000)
        self.assertLessEqual(len(json.dumps(page).encode()), 2000)
        self.assertIsNotNone(page['nextCursor']); self.assertLess(len(page['records']), 7)

    def test_oversized_group_resumes_without_splitting(self):
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        source = export([{'Total Line Items': '5100', 'Amount': '51.00', 'Bill Line Item Order': str(i),
                          'Bill Line Item Amount': '0.01'} for i in range(5100)])
        parser = CsvStage(db, io.StringIO(source))
        while not parser.read_step(deadline=float('inf'))['done']: pass
        index = self.api.SnapshotIndex(db)
        first = index.consolidate_step(deadline=float('inf'))
        self.assertFalse(first['done'])
        self.assertEqual(db.execute('select count(*) from bill_records').fetchone()[0], 0)
        # Its full provenance exceeds the existing record field bound: fail explicitly,
        # never split it into new bills or silently truncate source rows.
        with self.assertRaises(ValueError):
            while not index.consolidate_step(deadline=float('inf'))['done']: pass

    def test_large_ambiguous_group_resumes_and_keeps_every_candidate(self):
        _, index = self.build(export([{} for _ in range(5100)]))
        query = dict(importId=IMPORT_ID, references=[dict(invoiceKey='00042-A', kind='invoice')], amounts=[])
        first = index.candidates_page(query, -1, 500, 1000000)
        self.assertEqual(first['total'], 5100)
        self.assertEqual(len(first['records']), 500)
        self.assertEqual(index.finish()['counts']['collapsedRowCount'], 0)
