import copy
import unittest
from test_ap_shared_models import valid_doc
from test_ap_bill_working_policy import bill

try:
    from app.ap_shared.bills.working.protections import ProtectionSet
except ImportError:
    ProtectionSet = None


class WorkingProtectionsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ProtectionSet, 'Authoritative saved-follow-up protection is not implemented')
        self.doc = valid_doc()
        self.doc['rows'][0]['invoiceNumber'] = 'INV-1001'
        self.row = dict(id=self.doc['rows'][0]['id'], vendor=self.doc['vendor'],
                        invoiceNumber='INV-1001', kind='invoice', originalAmount=18400,
                        status='amount', candidates=[bill(amount=10000)])
        self.revision = dict(doc=self.doc, results=[self.row], resolutions={})

    def test_saved_followup_keeps_amount_discrepancy_on_completed_archived_statement(self):
        self.revision['resolutions'] = {self.row['id']: {'decision': 'Investigate amount difference'}}
        p = ProtectionSet()
        p.add_statement(dict(completed=True, archived=True), self.revision,
                        {self.doc['vendor']: self.doc['vendor']})
        self.assertTrue(p.protects(bill(amount=99999)))
        self.assertFalse(p.protects(bill(invoiceNumber='OTHER')))
        self.assertFalse(p.protects(bill(vendor='Different vendor')))

    def test_unresolved_draft_protected_but_resolved_current_revision_releases_it(self):
        for decision, expected in [(None, True), ('Reviewed — no action needed', False)]:
            p = ProtectionSet()
            self.revision['resolutions'] = {} if decision is None else {self.row['id']: {'decision': decision}}
            p.add_statement(dict(completed=False), self.revision, {})
            self.assertEqual(p.protects(bill()), expected)
        p = ProtectionSet()
        p.add_statement(dict(completed=True), self.revision, {})
        self.assertFalse(p.protects(bill()))

    def test_ambiguous_vendor_protects_reference_across_vendors(self):
        p = ProtectionSet()
        p.add_statement(dict(completed=False), self.revision, {})
        self.assertTrue(p.protects(bill(vendor='Other plausible vendor')))
        self.assertFalse(p.protects(bill(vendor='Other', invoiceNumber='INV-2000')))

    def test_adventure_alias_preserves_digits_and_credit_reference_semantics(self):
        vendor = 'Adventure in Food Trading Company'
        self.doc['vendor'] = 'Adventure in Food'
        self.row.update(vendor=vendor, invoiceNumber='00271712X', candidates=[])
        self.doc['rows'][0]['invoiceNumber'] = '00271712X'
        p = ProtectionSet()
        p.add_statement(dict(completed=False), self.revision, {self.doc['vendor']: vendor})
        self.assertTrue(p.protects(bill(vendor=vendor, invoiceNumber='00271712')))
        self.assertTrue(p.protects(bill(vendor=vendor, invoiceNumber='00271712Y')))
        self.assertFalse(p.protects(bill(vendor=vendor, invoiceNumber='271712')))
        self.assertFalse(p.protects(bill(vendor=vendor, invoiceNumber='00271712', kind='credit')))

    def test_explicit_duplicate_decisions_protect_complete_members(self):
        members = [dict(ordinal=0, bill=bill()), dict(ordinal=1, bill=bill(vendor='Other vendor'))]
        for decision, expected in [('confirmed_duplicate', True), ('unreviewed', True), ('not_duplicate', False)]:
            p = ProtectionSet()
            p.add_duplicate({'decision': decision, 'memberCount': 2}, members)
            self.assertEqual(p.protects(bill()), expected)
            self.assertEqual(p.protects(bill(vendor='Other vendor')), expected)
        self.assertFalse(ProtectionSet().protects(bill()))

    def test_malformed_or_incomplete_evidence_fails_closed(self):
        for members in [[], [{'ordinal': 0, 'bill': bill()}], [{'ordinal': 0, 'bill': {}}]]:
            with self.subTest(members=members), self.assertRaises(ValueError):
                ProtectionSet().add_duplicate({'decision': 'unreviewed', 'memberCount': 2}, members)
        bad = copy.deepcopy(self.revision)
        bad['results'][0]['invoiceNumber'] = ''
        bad['results'][0]['candidates'] = []
        bad['doc']['rows'][0]['invoiceNumber'] = ''
        with self.assertRaises(ValueError):
            ProtectionSet().add_statement(dict(completed=False), bad, {})
        bad = copy.deepcopy(self.revision)
        bad['resolutions'] = {'unknown-result': {'decision': 'Follow up with vendor'}}
        with self.assertRaises(ValueError):
            ProtectionSet().add_statement(dict(completed=True), bad, {})

    def test_semantic_digest_ignores_order_and_nonsemantic_notes(self):
        a, b = ProtectionSet(), ProtectionSet()
        a.add_statement(dict(completed=False), self.revision, {})
        other = copy.deepcopy(self.revision)
        other['doc']['notes'] = 'Updated reviewer note'
        other['results'] = list(reversed(other['results']))
        b.add_statement(dict(completed=False), other, {})
        self.assertEqual(a.digest(), b.digest())
        self.assertNotEqual(a.digest(), ProtectionSet().digest())


if __name__ == '__main__':
    unittest.main()
