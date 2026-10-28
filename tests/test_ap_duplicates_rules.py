import unittest
from fixtures.ap_shared.duplicate_cases import bill, changed, PIN


class DuplicateRuleTests(unittest.TestCase):
    def setUp(self):
        from app.ap_shared.bills.duplicates import rules
        self.rules = rules

    def test_suffix_variations_require_same_total_and_thirty_day_window(self):
        for a, b in [('271712', '271712X'), ('271712A', '271712B')]:
            with self.subTest(left=a, right=b):
                result = self.rules.classify(bill(a), bill(b, invoice_date='2026-10-31'))
                self.assertEqual(result['classification'], 'possible_duplicate')
                self.assertIn('trailing_letter', result['reasons'])
                self.assertIsNone(self.rules.classify(bill(a), bill(b, invoice_date='2026-11-01')))
                self.assertIsNone(self.rules.classify(bill(a), bill(b, amount=129980)))

    def test_adjacent_digit_swap_is_not_general_fuzzy_matching(self):
        self.assertIn('digit_transposition', self.rules.classify(bill(), bill('271721'))['reasons'])
        for ref in ['271713', '27171', '271712XX', '0271712', '731712', '712']:
            with self.subTest(reference=ref):
                self.assertIsNone(self.rules.classify(bill(), bill(ref)))
        self.assertIsNone(self.rules.classify(bill('123'), bill('123X')))

    def test_digit_swaps_require_same_valid_invoice_day(self):
        for vendor in ['Synthetic Daily Doughnuts', 'Synthetic Daily Deliveries']:
            for a, b in [('990000-R-1303', '990000-R-1330'),
                         ('990000-R-1312', '990000-R-1321'),
                         ('990000-R-1302', '990000-R-1320'),
                         ('990000-R-1301', '990000-R-1310')]:
                left = bill(a, vendor=vendor, amount=10000, currency='')
                for day in ['2026-10-02', '2026-10-18', '', '2026-02-30']:
                    right = bill(b, vendor=vendor, amount=10000, currency='', invoice_date=day)
                    with self.subTest(vendor=vendor, references=(a, b), date=day):
                        self.assertIsNone(self.rules.classify(left, right))
                        self.assertIsNone(self.rules.classify(right, left))
                right = bill(b, vendor=vendor, amount=10000, currency='')
                for first, second in [(left, right), (right, left)]:
                    result = self.rules.classify(first, second)
                    self.assertEqual(result['classification'], 'possible_duplicate')
                    self.assertIn('digit_transposition', result['reasons'])
                for day in ['', '2026-02-30']:
                    self.assertIsNone(self.rules.classify(changed(left, invoiceDate=day), changed(right, invoiceDate=day)))

    def test_exact_reference_checks_survive_different_dates(self):
        left = bill('990000-R-1303', amount=10000)
        right = bill('990000 -r- 1303', amount=10000, invoice_date='2026-12-01')
        result = self.rules.classify(left, right)
        self.assertEqual(result['classification'], 'exact_pattern')
        self.assertIn('different_invoice_dates', result['reasons'])
        self.assertEqual(self.rules.classify(left, changed(right, amount=10001))['classification'], 'amount_difference')

    def test_same_day_swaps_still_require_vendor_amount_and_currency_agreement(self):
        for changes in [dict(vendor='Another Vendor'), dict(amount=129980), dict(currency='CAD')]:
            self.assertIsNone(self.rules.classify(bill(), changed(bill('271721'), **changes)))

    def test_equal_amounts_and_other_vendors_are_not_duplicate_evidence(self):
        self.assertIsNone(self.rules.classify(bill(), bill('888888')))
        self.assertIsNone(self.rules.classify(bill(), bill('271712X', vendor='Other Foods')))
        self.assertIsNone(self.rules.classify(bill(), bill('271712X', currency='CAD')))

    def test_missing_date_does_not_borrow_payment_date(self):
        right = changed(bill('271712X'), invoiceDate='', paymentDate='2026-10-01')
        self.assertIsNone(self.rules.classify(bill(), right))
        self.assertIsNone(self.rules.classify(bill('271712X'), changed(bill(), invoiceDate='')))

    def test_unknown_currency_does_not_claim_known_currency_or_strong_match(self):
        for currency in ['', 'invalid', 'US1']:
            result = self.rules.classify(bill(), bill('271712X', currency=currency))
            self.assertEqual(result['strength'], 'possible')
            self.assertIn('currency_unknown', result['reasons'])
        self.assertIsNotNone(self.rules.classify(bill(), bill('271712X', currency=' usd ')))

    def test_same_economic_identity_is_export_ambiguity_not_separate_bills(self):
        result = self.rules.classify(bill(), changed(bill('27 1712'), id='another', sourceRows='8'))
        self.assertEqual(result['classification'], 'export_review')
        self.assertIn('indistinguishable_identity', result['reasons'])
        self.assertNotEqual(result['strength'], 'strong')

    def test_same_reference_different_total_is_separate_amount_finding(self):
        result = self.rules.classify(bill(), bill(amount=129980))
        self.assertEqual(result['classification'], 'amount_difference')
        self.assertIn('different_amount', result['reasons'])
        self.assertIsNone(self.rules.classify(bill(), bill(amount=129980, currency='CAD')))

    def test_incomplete_lines_override_possible_duplicate_label(self):
        other = changed(bill('271712X'), sourceIssues='Line-item detail is incomplete or does not agree with the bill total.')
        self.assertEqual(self.rules.classify(bill(), other)['classification'], 'export_review')

    def test_credits_zero_negative_and_invalid_cents_are_ineligible(self):
        for changes in [dict(kind='credit'), dict(amount=0), dict(amount=-1), dict(amount=True), dict(amount=1.2)]:
            with self.subTest(changes=changes):
                self.assertFalse(self.rules.eligible(changed(bill(), **changes)))
                self.assertIsNone(self.rules.classify(bill(), changed(bill('271712X'), **changes)))

    def test_fingerprint_survives_weekly_row_and_payment_changes(self):
        before = bill()
        after = changed(before, id='next:88', sourceRows='99', reportedPaidAmount=129981,
                        reportedAmountDue=0, status='PaidInFull', sourceIssues='Paid Amount is missing or invalid.')
        self.assertEqual(self.rules.bill_fingerprint(before), self.rules.bill_fingerprint(after))
        self.assertEqual(self.rules.classify(before, bill('271712X')),
                         self.rules.classify(after, bill('271712X')))

    def test_identifying_changes_reopen_review(self):
        for changes in [dict(amount=129980), dict(invoiceNumber='271712X'),
                        dict(invoiceDate='2026-10-02'), dict(currency='CAD'), dict(vendor='Other')]:
            self.assertNotEqual(self.rules.bill_fingerprint(bill()), self.rules.bill_fingerprint(changed(bill(), **changes)))
        self.assertNotEqual(self.rules.bill_fingerprint(bill('abc')), self.rules.bill_fingerprint(bill('ABC')))

    def test_finding_identity_preserves_multiplicity_and_rule_version(self):
        key = self.rules.finding_key([('a' * 64, 1), ('b' * 64, 1)], 'possible_duplicate', [])
        self.assertEqual(key, self.rules.finding_key([('b' * 64, 1), ('a' * 64, 1)], 'possible_duplicate', []))
        self.assertNotEqual(key, self.rules.finding_key([('a' * 64, 2), ('b' * 64, 1)], 'possible_duplicate', []))
        self.assertNotEqual(key, self.rules.finding_key([('a' * 64, 1), ('b' * 64, 1)], 'possible_duplicate', [], 'v2'))


class DuplicateContractTests(unittest.TestCase):
    def test_old_rule_manifest_cannot_reuse_completed_results(self):
        from app.ap_shared.bills.duplicates.contracts import validate_manifest
        manifest = dict(format='bill-duplicates-v1', ruleVersion='bill-duplicates-v1', sourceDigest='a' * 64,
                        importId=PIN['importId'], key=PIN['importId'] + '/bill-duplicates/v1/' + PIN['importId'] +
                        '/bill-duplicates-v1/' + 'b' * 64 + '.sqlite.gz', hash='b' * 64, bytes=50,
                        expandedHash='c' * 64, expandedBytes=4096, findingCount=1, recordCount=2)
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_manifest_and_cursor_bind_to_source_and_workspace(self):
        from app.ap_shared.bills.duplicates.contracts import RULE_VERSION, ARTIFACT_FORMAT,STORAGE_VERSION,validate_manifest, encode_cursor, decode_cursor
        manifest = dict(format=ARTIFACT_FORMAT, ruleVersion=RULE_VERSION, sourceDigest='a' * 64,
                        importId=PIN['importId'], key=PIN['importId'] + '/bill-duplicates/'+STORAGE_VERSION+'/' + PIN['importId'] +
                        '/' + RULE_VERSION + '/' + 'b' * 64 + '.sqlite.gz', hash='b' * 64, bytes=50,
                        expandedHash='c' * 64, expandedBytes=4096, findingCount=1, recordCount=2)
        self.assertEqual(validate_manifest(manifest), manifest)
        for changes in [dict(key='../bad'), dict(bytes=33554433), dict(expandedBytes=536870913),
                        dict(findingCount=100001), dict(format='snapshot-v2')]:
            with self.assertRaises(ValueError):
                validate_manifest({**manifest, **changes})
        binding = dict(workspace=PIN['importId'], scan='scan', revision=1, filters={'review': 'all'})
        token = encode_cursor(binding, {'after': 3})
        self.assertEqual(decode_cursor(token, binding), {'after': 3})
        with self.assertRaises(ValueError):
            decode_cursor(token, {**binding, 'revision': 2})

    def test_pin_and_review_payload_reject_unknown_or_forged_values(self):
        from app.ap_shared.bills.duplicates.contracts import validate_pin, validate_review_payload
        self.assertEqual(validate_pin(PIN), PIN)
        for value in [{**PIN, 'sql': 'select 1'}, {**PIN, 'recordCount': True}, {**PIN, 'sourceDigest': '../bad'}]:
            with self.assertRaises(ValueError):
                validate_pin(value)
        payload = dict(scan_id=PIN['importId'], import_id=PIN['importId'], expected_import_version=1,
                       finding_key='b' * 64, expected_review_version=0, decision='not_duplicate', initials='kc', note='')
        self.assertEqual(validate_review_payload(payload)['initials'], 'KC')
        for changes in [dict(initials=''), dict(verified_key='b' * 64), dict(decision='delete')]:
            with self.assertRaises(ValueError):
                validate_review_payload({**payload, **changes})
