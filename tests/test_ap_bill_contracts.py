import copy
import importlib
import unittest


WORKSPACE = '00000000-0000-4000-8000-000000000001'


def manifest():
    prefix = f'{WORKSPACE}/bills/v2/' + 'a' * 64 + '/'
    return dict(format='snapshot-v2', parserVersion='bill-csv-v1', indexVersion=1,
                originalHash='a' * 64, originalBytes=155585995,
                originalArchive=dict(key=prefix + 'b' * 64 + '.csv.gz', hash='b' * 64, bytes=14312222),
                indexArchive=dict(key=prefix + 'c' * 64 + '.sqlite.gz', hash='c' * 64,
                                  bytes=10000000, expandedHash='d' * 64, expandedBytes=200000000),
                recordCount=223425, sourceRowCount=284365, collapsedRowCount=59592,
                excludedRowCount=1348, warningCount=1784, vendorDigest='e' * 64)


class BillContractTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module('app.ap_shared.bills.contracts')
        except ModuleNotFoundError:
            self.fail('BILL snapshot contracts have not been implemented')

    def test_large_manifest_preserves_source_counts_and_rejects_unknown_fields(self):
        result = self.api.validate_manifest(manifest())
        self.assertEqual(result['recordCount'], 223425)
        self.assertEqual(result['originalBytes'], 155585995)
        with self.assertRaises(ValueError):
            self.api.validate_manifest({**manifest(), 'publicURL': 'https://example.invalid'})

    def test_manifest_limits_and_count_consistency_fail_without_truncation(self):
        for field, value in [('originalBytes', 256 * 1024 * 1024 + 1), ('recordCount', 500001),
                             ('sourceRowCount', 750001), ('indexVersion', True), ('collapsedRowCount', -1)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.api.validate_manifest({**manifest(), field: value})
        changed = manifest()
        changed['indexArchive']['bytes'] = 32 * 1024 * 1024 + 1
        with self.assertRaises(ValueError):
            self.api.validate_manifest(changed)
        changed = manifest()
        changed['indexArchive']['key'] = WORKSPACE + '/pdf/' + 'c' * 64 + '.pdf'
        with self.assertRaises(ValueError):
            self.api.validate_manifest(changed)

    def test_query_bounds_unknown_fields_and_unsafe_cents(self):
        query = dict(importId=WORKSPACE, references=[dict(invoiceKey='00042-A', kind='invoice')],
                     amounts=[dict(vendorKey='alpha', kind='invoice', amount=13800)])
        self.assertEqual(self.api.validate_query(query), query)
        for altered in [{**query, 'sql': 'select 1'}, {**query, 'references': query['references'] * 101},
                        {**query, 'amounts': [dict(vendorKey='alpha', kind='invoice', amount=True)]},
                        {**query, 'amounts': [dict(vendorKey='alpha', kind='invoice', amount=9007199254740992)]}]:
            with self.assertRaises(ValueError):
                self.api.validate_query(altered)

    def test_cursor_is_query_pinned_and_rejects_forgery(self):
        token = self.api.encode_cursor(WORKSPACE, 'f' * 64, 499)
        self.assertEqual(self.api.decode_cursor(token, WORKSPACE, 'f' * 64), 499)
        for wrong in [token[:-2] + 'xx', 'not-a-cursor']:
            with self.assertRaises(ValueError):
                self.api.decode_cursor(wrong, WORKSPACE, 'f' * 64)
        with self.assertRaises(ValueError):
            self.api.decode_cursor(token, WORKSPACE, '0' * 64)


if __name__ == '__main__':
    unittest.main()
