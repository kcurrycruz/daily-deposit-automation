import unittest
from uuid import uuid4

WORKSPACE = '00000000-0000-4000-8000-000000000001'
def valid_doc():
    return {'id':str(uuid4()), 'vendor':'Synthetic vendor','filename':'synthetic.pdf',
            'layout':'generic','statementDate':'2026-10-01','declaredTotal':18400,
            'confirmed':True,'pageCount':1,'warnings':[],'notes':'','rows':[
                {'id':str(uuid4()),'invoiceNumber':'00042','type':'invoice','date':'2026-09-01',
                 'amount':18400,'balance':None,'confidence':99,'page':1}]}

class SharedModelsTests(unittest.TestCase):
    def test_initials_required_notes_optional(self):
        from app.ap_shared.models import normalize_initials, validate_statement, ApValidationError
        self.assertEqual(normalize_initials(' kc '),'KC')
        for value in ['', ' ', '123', 'A'*11]:
            with self.subTest(value=value), self.assertRaises(ApValidationError): normalize_initials(value)
        self.assertEqual(validate_statement(valid_doc())['notes'],'')

    def test_integer_money_reference_text_and_nullable_balance(self):
        from app.ap_shared.models import validate_statement, ApValidationError
        good=valid_doc(); self.assertEqual(validate_statement(good)['rows'][0]['invoiceNumber'],'00042')
        self.assertIsNone(validate_statement(good)['rows'][0]['balance'])
        for value in [True, 18400.0, '18400', float('nan'), 9007199254740992]:
            bad=valid_doc(); bad['rows'][0]['amount']=value
            with self.subTest(value=repr(value)), self.assertRaises(ApValidationError): validate_statement(bad)

    def test_unknown_fields_dates_and_file_paths_rejected(self):
        from app.ap_shared.models import validate_statement, ApValidationError
        for field,value in [('password','synthetic'),('originalPath','../../private'),('statementDate','2026-02-30')]:
            bad=valid_doc(); bad[field]=value
            with self.subTest(field=field), self.assertRaises(ApValidationError): validate_statement(bad)
        bad=valid_doc(); bad['rows'][0]['invoiceNumber']=42
        with self.assertRaises(ApValidationError): validate_statement(bad)

    def test_config_requires_private_backend_and_hides_credentials(self):
        from app.ap_shared.models import read_config, ApValidationError
        config={'password':'SYNTHETIC-PASSWORD','supabase_url':'https://synthetic.supabase.co',
                'supabase_secret_key':'SYNTHETIC-SERVER-KEY','workspace_id':WORKSPACE,'bucket':'hwfc-ap-private'}
        actual=read_config({'ap':config}); self.assertEqual(actual.workspace_id,WORKSPACE)
        self.assertNotIn('SYNTHETIC-PASSWORD',repr(actual)); self.assertNotIn('SYNTHETIC-SERVER-KEY',repr(actual))
        for field in config:
            bad=config.copy(); bad.pop(field)
            with self.subTest(field=field), self.assertRaises(ApValidationError): read_config({'ap':bad})
        with self.assertRaises(ApValidationError): read_config({'ap':{**config,'supabase_url':'http://public.example'}})

    def test_request_envelope_has_no_client_workspace_or_credentials(self):
        from app.ap_shared.models import validate_request, ApValidationError
        request={'version':1,'request_id':str(uuid4()),'action':'bootstrap','payload':{}}
        self.assertEqual(validate_request(request)['action'],'bootstrap')
        for bad in [{**request,'request_id':'bad'},{**request,'version':True}, {**request,'workspace_id':WORKSPACE},
                    {**request,'action':'delete_all'}, {**request,'payload':{'password':'synthetic'}},
                    {**request,'payload':{'data':'X'*(1024*1024)}}]:
            with self.subTest(action=bad['action']), self.assertRaises(ApValidationError): validate_request(bad)

    def test_provider_keeps_source_limitations_and_optional_amounts(self):
        from app.ap_shared.models import validate_provider, ApValidationError
        provider={'loaded':True,'simulated':False,'label':'synthetic.csv','sourceFormat':'bill-native',
                  'records':[{'vendor':'Synthetic','invoiceNumber':'00042','amount':18400,
                              'comparisonScope':'invoice-only','reportedAmountDue':None}]}
        self.assertEqual(validate_provider(provider)['records'][0]['comparisonScope'],'invoice-only')
        with self.assertRaises(ApValidationError): validate_provider({**provider,'simulated':True})
        with self.assertRaises(ApValidationError): validate_provider({**provider,'records':[{**provider['records'][0],'amount':True}]})

    def test_limits_reject_not_truncate(self):
        from app.ap_shared.models import validate_statement, ApValidationError
        bad=valid_doc(); bad['rawText']='X'*(512*1024+1)
        with self.assertRaises(ApValidationError): validate_statement(bad)
        bad=valid_doc(); bad['rows']=bad['rows']*10001
        with self.assertRaises(ApValidationError): validate_statement(bad)

    def test_review_decision_notes_are_optional(self):
        from app.ap_shared.models import validate_resolution, ApValidationError
        self.assertEqual(validate_resolution({'decision':'Reviewed — no action needed','note':''})['note'],'')
        with self.assertRaises(ApValidationError): validate_resolution({'decision':'arbitrary','note':''})

    def test_ocr_confidence_accepts_finite_fractional_scores(self):
        from app.ap_shared.models import validate_statement, ApValidationError
        doc=valid_doc(); doc['rows'][0]['confidence']=87.25
        self.assertEqual(validate_statement(doc)['rows'][0]['confidence'],87.25)
        doc['rows'][0]['confidence']=float('nan')
        with self.assertRaises(ApValidationError): validate_statement(doc)

    def test_flagged_native_source_rows_retain_unreadable_amounts(self):
        from app.ap_shared.models import validate_record, ApValidationError
        record={'vendor':'Synthetic','invoiceNumber':'A','amount':None,'sourceIssues':'Unreadable numeric amount'}
        self.assertIsNone(validate_record(record)['amount'])
        with self.assertRaises(ApValidationError): validate_record({**record,'sourceIssues':''})

    def test_non_string_action_is_validation_error(self):
        from app.ap_shared.models import validate_request, ApValidationError
        with self.assertRaises(ApValidationError):
            validate_request({'version':1,'request_id':str(uuid4()),'action':[],'payload':{}})

    def test_review_note_may_be_omitted(self):
        from app.ap_shared.models import validate_resolution
        self.assertEqual(validate_resolution({'decision':'Reviewed — no action needed'})['note'],'')

    def test_import_metadata_can_be_validated_before_record_batches(self):
        from app.ap_shared.models import validate_provider_metadata,ApValidationError
        meta={'loaded':True,'simulated':False,'label':'synthetic.csv','sourceFormat':'bill-native'}
        self.assertEqual(validate_provider_metadata(meta)['label'],'synthetic.csv')
        with self.assertRaises(ApValidationError):validate_provider_metadata({**meta,'password':'Synthetic'})

if __name__ == '__main__': unittest.main()
