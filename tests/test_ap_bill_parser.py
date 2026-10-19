import importlib
import io
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
import unittest
from fixtures.ap_shared.bill_exports import export


class BillParserTests(unittest.TestCase):
    def setUp(self):
        try:
            self.norm = importlib.import_module('app.ap_shared.bills.normalization')
            self.parser = importlib.import_module('app.ap_shared.bills.parser')
        except ModuleNotFoundError:
            self.fail('Streaming BILL parser has not been implemented')
        self.connection = sqlite3.connect(':memory:')
        self.addCleanup(self.connection.close)

    def stage(self, csv, step=2):
        stage = self.parser.CsvStage(self.connection, io.StringIO(csv, newline=''))
        self.addCleanup(stage.close)
        progress = stage.read_step(max_rows=step, deadline=float('inf'))
        while not progress['done']:
            progress = stage.read_step(max_rows=step, deadline=float('inf'))
        return progress

    def test_money_dates_and_reference_keys_have_exact_expected_values(self):
        self.assertEqual(self.norm.parse_cents('($138.00)'), -13800)
        self.assertIsNone(self.norm.parse_cents('1.234'))
        self.assertEqual(self.norm.invoice_key(' 00 142-A '), '00142-A')
        self.assertEqual(self.norm.date_iso('02/30/26'), '')

    def test_unicode_whitespace_and_suffix_keys_match_js(self):
        values = [' A\u00a0&\u2007B ', '\ufeff00042-A\u2028', '١٣٨.00', '138.00-', '$-138.00',
                  '+138.2', '1,38.00', '02/29/24', '2/29/26', '1/2/99', 'ΣΟΣ', 'İNC', 'Straße']
        result = subprocess.run(['node', 'tests/fixtures/ap_shared/bill_parser_oracle.mjs', '--keys'],
                                input=json.dumps(values), capture_output=True, encoding='utf8', check=True)
        actual = [dict(vendor=self.norm.vendor_key(v), reference=self.norm.invoice_key(v),
                       amount=self.norm.parse_cents(v), date=self.norm.date_iso(v)) for v in values]
        self.assertEqual(actual, json.loads(result.stdout))

    def test_bom_crlf_and_quoted_newlines_keep_source_record_numbers(self):
        self.stage('\ufeff' + export([{'Vendor Name': 'Synthetic\r\nVendor'}, {'Invoice #': '00043'}]))
        rows = self.connection.execute('select source_row,record from bill_stage order by source_row').fetchall()
        self.assertEqual([r[0] for r in rows], [2, 3])
        self.assertEqual(json.loads(rows[0][1])['vendor'], 'Synthetic\r\nVendor')

    def test_malformed_money_is_not_zero_and_inactive_rows_are_reported(self):
        self.stage(export([{'Amount': 'bad'}, {'Active?': 'Inactive'}, {'Vendor Name': ''}]))
        row = json.loads(self.connection.execute('select record from bill_stage').fetchone()[0])
        self.assertIsNone(row['amount'])
        self.assertEqual(self.connection.execute('select count(*) from bill_warnings').fetchone()[0], 2)

    def test_same_vendor_reference_different_dates_stays_distinct(self):
        self.stage(export([{}, {'Invoice Date': '10/02/2026'}]))
        self.assertEqual(self.connection.execute('select count(distinct group_key) from bill_stage').fetchone()[0], 2)

    def test_structural_errors_and_duplicate_headers_are_not_accepted(self):
        for source in ['Vendor Name,Invoice #,Amount,Amount\nA,1,1,1',
                       export([{}]) + 'wrong,column,count\n', 'Vendor Name,Invoice #,Amount\n"unclosed,1,1']:
            with self.subTest(source=source[:20]), self.assertRaises(ValueError):
                self.connection = sqlite3.connect(':memory:')
                self.addCleanup(self.connection.close)
                self.stage(source)

    def test_each_step_is_bounded_without_losing_rows(self):
        stage = self.parser.CsvStage(self.connection, io.StringIO(export([{'Invoice #': str(i)} for i in range(5)])))
        self.addCleanup(stage.close)
        p = stage.read_step(max_rows=2, deadline=float('inf'))
        self.assertFalse(p['done']); self.assertEqual(p['sourceRowCount'], 2)
        while not p['done']:
            p = stage.read_step(max_rows=2, deadline=float('inf'))
        self.assertEqual(p['sourceRowCount'], 5)
        self.assertEqual(self.connection.execute('select count(*) from bill_stage').fetchone()[0], 5)

    def test_multibyte_header_field_obeys_byte_limit(self):
        source = export([{}]).replace('Vendor Name', 'Vendor Name' + '\u00a0' * 524288, 1)
        with self.assertRaises(ValueError):
            self.stage(source)
