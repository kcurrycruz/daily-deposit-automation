import copy
import unittest
from uuid import uuid4
from test_ap_shared_models import valid_doc
from test_ap_shared_service import fixture
from app.ap_shared.models import ApValidationError, RULE_VERSION, validate_resolution


def payload():
    doc = valid_doc()
    row_id = doc['rows'][0]['id']
    candidate = {'id': 'bill-2', 'vendor': doc['vendor'], 'invoiceNumber': '00042X', 'amount': 18400, 'kind': 'invoice'}
    proof = {'statementReference': '00042', 'statementAmount': 18400, 'candidate': copy.deepcopy(candidate)}
    return {'statement_id': doc['id'], 'expected_version': 2, 'doc': doc,
            'resolutions': {row_id: {'decision': 'Reviewed — no action needed', 'note': '', 'confirmedMatch': proof}},
            'results': [{'id': row_id, 'invoiceNumber': '00042', 'kind': 'invoice', 'originalAmount': 18400,
                         'status': 'ambiguous', 'matchMethod': 'amount', 'candidates': [candidate,
                          {**candidate, 'id': 'bill-1', 'invoiceNumber': '00042Y'}]}],
            'import_id': None, 'mapping_snapshot': {}, 'rule_version': RULE_VERSION}


class ConfirmedMatchTests(unittest.TestCase):
    def test_structured_confirmation_keeps_selected_record_and_rejects_unknown_fields(self):
        resolution = next(iter(payload()['resolutions'].values()))
        self.assertEqual(validate_resolution(resolution)['confirmedMatch']['candidate']['id'], 'bill-2')
        bad = copy.deepcopy(resolution)
        bad['confirmedMatch']['candidate']['password'] = 'invalid'
        with self.assertRaises(ApValidationError):
            validate_resolution(bad)

    def test_confirmation_is_accepted_in_existing_revision_json_without_changing_results(self):
        service, repo, auth, _, _ = fixture()
        value = payload()
        self.assertEqual(service.handle('save_revision', value, str(uuid4()), auth)['version'], 3)
        self.assertEqual(value['results'][0]['status'], 'ambiguous')
        self.assertEqual(len(value['results'][0]['candidates']), 2)

    def test_unconfirmed_or_unrelated_evidence_is_rejected_before_storage(self):
        for mutation in ('unconfirmed', 'reference', 'amount', 'candidate', 'vendor', 'unsafe', 'unrelated-row'):
            service, repo, auth, _, _ = fixture()
            value = payload()
            row = value['results'][0]
            proof = next(iter(value['resolutions'].values()))['confirmedMatch']
            if mutation == 'unconfirmed': value['doc']['confirmed'] = False
            if mutation == 'reference': proof['statementReference'] = 'different'
            if mutation == 'amount': proof['statementAmount'] = 123
            if mutation == 'candidate': proof['candidate']['id'] = 'not-in-results'
            if mutation == 'vendor': row['status'] = 'vendor'
            if mutation == 'unsafe': proof['candidate']['sourceIssues'] = 'Unreadable'
            if mutation == 'unrelated-row': value['results'] = []
            with self.subTest(mutation=mutation), self.assertRaises(ApValidationError):
                service.handle('save_revision', value, str(uuid4()), auth)
            self.assertEqual(repo.version, 2)
