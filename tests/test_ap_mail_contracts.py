"""Mail boundaries use synthetic values; no account credentials or financial files."""
import copy
import unittest
from uuid import UUID

W = '00000000-0000-4000-8000-000000000001'
C = '00000000-0000-4000-8000-000000000002'


class MailContractsTests(unittest.TestCase):
    def test_same_receipt_stable_across_delivery_and_thread_change(self):
        from app.ap_mail.contracts import ReceiptKey, receipt_id
        key = ReceiptKey(W, 'account-1', 'msg-1', '0.1')
        actual = receipt_id(key)
        self.assertEqual(str(UUID(actual)), actual)
        self.assertEqual(receipt_id(ReceiptKey(W, 'account-1', 'msg-1', '0.1')), actual)
        for changed in [ReceiptKey(W, 'account-1', 'msg-2', '0.1'),
                        ReceiptKey(W, 'account-1', 'msg-1', '0.2'),
                        ReceiptKey(C, 'account-1', 'msg-1', '0.1')]:
            self.assertNotEqual(receipt_id(changed), actual)

    def test_secret_redaction_and_fixed_workspace(self):
        from app.ap_mail.contracts import MailConfig, MailError
        config = MailConfig('https://synthetic.supabase.co', 'TEST-SECRET', W,
                            'hwfc-ap-private', C, 'processor')
        self.assertNotIn('TEST-SECRET', repr(config))
        self.assertFalse(hasattr(config, 'password'))
        for kw in [dict(workspace_id='bad'), dict(role='interactive'),
                   dict(supabase_url='https://user:secret@synthetic.supabase.co'),
                   dict(bucket='../public'), dict(max_file_bytes=50*1024*1024)]:
            with self.subTest(kw=kw), self.assertRaises(MailError):
                MailConfig(**{**config.__dict__, **kw})
        error = MailError('auth')
        self.assertEqual(str(error), 'auth')
        with self.assertRaises(ValueError): MailError('secret provider response')

    def test_normalize_preserves_evidence_and_never_human_confirmation(self):
        from app.ap_mail.contracts import normalize_extraction
        doc = dict(id=C, vendor='Synthetic', filename='x.pdf', confirmed=True,
                   pageCount=1, warnings=[], rows=[dict(id=C, invoiceNumber='00042X',
                   type='invoice', date='2026-10-01', amount=13800, balance=None,
                   confidence=99, page=1)], notes='')
        prior = copy.deepcopy(doc)
        result = normalize_extraction(doc, C, 'a'*64)
        self.assertEqual(doc, prior)
        self.assertFalse(result['confirmed'])
        self.assertEqual(result['rows'][0]['invoiceNumber'], '00042X')
        self.assertEqual(result['rows'][0]['amount'], 13800)
        self.assertEqual(result['rows'][0]['page'], 1)
        self.assertNotEqual(result['rows'][0]['id'], C)
        self.assertEqual(normalize_extraction(doc, C, 'a'*64), result)
        doc['rows'][0]['id'] = W
        self.assertEqual(normalize_extraction(doc, C, 'a'*64), result)
        doc['rows'] = []
        from app.ap_mail.contracts import MailError
        with self.assertRaises(MailError): normalize_extraction(doc, C, 'a'*64)

    def test_claim_and_pin_validate_before_use(self):
        from app.ap_mail.contracts import Claim, SourcePin, MailError
        claim = Claim(C, W, 1, 1, 1, 1, '2026-11-04T12:00:00+00:00', 'extract')
        self.assertEqual(claim.mode, 'extract')
        for kw in [dict(lease_generation=0), dict(mode='complete'), dict(lease_until='bad')]:
            with self.subTest(kw=kw), self.assertRaises(MailError):
                Claim(**{**claim.__dict__, **kw})
        pin = SourcePin(None, 0, None, None, 0, 0, None, 'a'*64, {}, 'ap-match-v4')
        self.assertIsNone(pin.import_id)
        with self.assertRaises(MailError): SourcePin(C, 1, 'bad', None, 0, 0, None, 'a'*64, {}, 'ap-match-v4')

