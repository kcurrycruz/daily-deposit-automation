"""Retention coverage is independent from accounting/payment verification."""
import copy
from datetime import datetime, timezone
import unittest

try:
    from app.ap_shared.bills.working.policy import make_policy, retention_reasons
    from app.ap_shared.bills.working.contracts import working_digest, validate_working_manifest
except ImportError:
    make_policy = retention_reasons = working_digest = validate_working_manifest = None

W = '00000000-0000-4000-8000-000000000001'
I = '00000000-0000-4000-8000-000000000002'
S = '00000000-0000-4000-8000-000000000003'
NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)


def bill(**changes):
    return dict(dict(vendor='Synthetic vendor', invoiceNumber='INV-1001', kind='invoice',
                     invoiceDate='2025-10-29', amount=10000, status='PaidInFull',
                     reportedAmountDue=0, reportedPaidAmount=10000,
                     reportedCreditAmount=None, sourceIssues=''), **changes)


class WorkingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(make_policy, 'The active BILL retention policy is not implemented')
        self.policy = make_policy('last_12_months', NOW)

    def test_calendar_boundary_future_and_all(self):
        self.assertEqual(self.policy, dict(version='ap-active-range-v1', mode='last_12_months',
                                          asOfDate='2026-10-30', cutoffDate='2025-10-30'))
        self.assertEqual(retention_reasons(bill(), self.policy), [])
        for day in ['2025-10-30', '2026-11-13']:
            self.assertIn('recent', retention_reasons(bill(invoiceDate=day), self.policy))
        self.assertEqual(retention_reasons(bill(), make_policy('all', NOW)), ['all'])

    def test_timezone_leap_day_and_reject_naive_clock(self):
        self.assertEqual(make_policy('last_12_months', datetime(2028, 2, 29, 16, tzinfo=timezone.utc))['cutoffDate'], '2027-02-28')
        self.assertEqual(make_policy('last_12_months', datetime(2026, 10, 30, 1, tzinfo=timezone.utc))['asOfDate'], '2026-10-29')
        self.assertEqual(make_policy('all', NOW)['cutoffDate'], '')
        for mode, now in [('year', NOW), ('all', datetime(2026, 10, 30))]:
            with self.assertRaises(ValueError):
                make_policy(mode, now)

    def test_dates_unknown_or_malformed_are_retained(self):
        for day in ['', None, '2025-02-29', '2025-1-01', 'invalid']:
            with self.subTest(day=day):
                self.assertIn('date_unknown', retention_reasons(bill(invoiceDate=day), self.policy))

    def test_unsettled_unknown_and_source_issues_are_retained(self):
        cases = [dict(status=s) for s in ['Open', 'Scheduled', '', 'unknown']]
        cases += [dict(reportedAmountDue=v) for v in [1, -1, '0', False, 0.0]]
        cases += [dict(amount=v) for v in [None, 0, -1, True, 10000.0]]
        cases += [dict(sourceIssues='Repeated source rows require review.')]
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertIn('unsettled', retention_reasons(bill(**changes), self.policy))

    def test_missing_due_requires_exact_reported_payment_coverage(self):
        for changes in [dict(reportedPaidAmount=10000, reportedCreditAmount=None),
                        dict(reportedPaidAmount=9000, reportedCreditAmount=1000),
                        dict(reportedPaidAmount=10000, reportedCreditAmount=0)]:
            self.assertEqual(retention_reasons(bill(reportedAmountDue=None, **changes), self.policy), [])
        cases = [dict(reportedPaidAmount=v) for v in [None, True, 9999, 10001, -1, '10000']]
        cases += [dict(reportedCreditAmount=v) for v in [-1, True, '0', 1]]
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertIn('unsettled', retention_reasons(bill(reportedAmountDue=None, **changes), self.policy))

    def test_protection_non_invoice_and_overlapping_reasons(self):
        self.assertEqual(retention_reasons(bill(), self.policy, protected=True), ['follow_up'])
        self.assertIn('non_invoice', retention_reasons(bill(kind='credit', amount=-100), self.policy))
        reasons = retention_reasons(bill(invoiceDate='', status='Open'), self.policy, protected=True)
        self.assertEqual(reasons, ['date_unknown', 'unsettled', 'follow_up'])


class WorkingManifestTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(working_digest, 'Versioned working-set identities are not implemented')
        self.source = dict(importId=I, sourceDigest='a' * 64, recordCount=2)
        self.policy = make_policy('last_12_months', NOW)
        self.identity = working_digest(self.source, self.policy, 'b' * 64)
        def archive(ch):
            return dict(key=f'{W}/bill-working/v1/{self.identity}/{ch*64}.sqlite.gz',
                        hash=ch*64, bytes=100, expandedHash='e'*64, expandedBytes=1000)
        self.manifest = dict(format='ap-bill-working-v1', workingSetId=S,
                             workingDigest=self.identity, source=self.source, policy=self.policy,
                             protectionDigest='b'*64, trainingVersion='vendor-history-v1',
                             fullRecordCount=2, activeCount=1, archivedCount=1,
                             retainedReasonCounts={'recent': 1}, vendorDigest='f'*64,
                             indexArchive=archive('c'), contextArchive=archive('d'))

    def test_identity_changes_with_each_scope_input(self):
        self.assertEqual(self.identity, working_digest(copy.deepcopy(self.source), copy.deepcopy(self.policy), 'b'*64))
        variations = [(dict(self.source, importId=S), self.policy, 'b'*64),
                      (dict(self.source, sourceDigest='c'*64), self.policy, 'b'*64),
                      (self.source, make_policy('all', NOW), 'b'*64),
                      (self.source, make_policy('last_12_months', datetime(2026, 10, 31, 16, tzinfo=timezone.utc)), 'b'*64),
                      (self.source, self.policy, 'c'*64)]
        for args in variations:
            self.assertNotEqual(self.identity, working_digest(*args))

    def test_valid_nonempty_and_empty_sets(self):
        self.assertEqual(validate_working_manifest(self.manifest), self.manifest)
        empty = dict(self.manifest, activeCount=0, archivedCount=2, retainedReasonCounts={})
        self.assertEqual(validate_working_manifest(empty)['activeCount'], 0)

    def test_reject_inconsistent_identity_counts_namespace_and_bounds(self):
        invalid = [dict(self.manifest, workingDigest='f'*64),
                   dict(self.manifest, activeCount=2), dict(self.manifest, fullRecordCount=3),
                   dict(self.manifest, activeCount=True), dict(self.manifest, archivedCount=-1),
                   dict(self.manifest, retainedReasonCounts={'recent': 2}),
                   dict(self.manifest, retainedReasonCounts={'mystery': 1}),
                   dict(self.manifest, trainingVersion='unknown')]
        for field, change in [('hash', 'a'*64), ('bytes', 32*1024*1024+1),
                              ('expandedBytes', 512*1024*1024+1),
                              ('key', f'{S}/bill-working/v1/{self.identity}/{"d"*64}.sqlite.gz')]:
            bad = copy.deepcopy(self.manifest)
            bad['contextArchive'][field] = change
            invalid.append(bad)
        bad = copy.deepcopy(self.manifest)
        bad['policy']['cutoffDate'] = '2024-01-01'
        invalid.append(bad)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_working_manifest(value)


if __name__ == '__main__':
    unittest.main()
