import json
import unittest
from uuid import uuid4
import httpx
from supabase import create_client
from supabase.client import ClientOptions
from test_ap_shared_access import CONFIG, NOW

IMPORT='00000000-0000-4000-8000-000000000011'
STATEMENT='00000000-0000-4000-8000-000000000012'
REVISION='00000000-0000-4000-8000-000000000013'

class BackendTransport:
    """External HTTP boundary only; production SDK, queries and repository remain real."""
    def __init__(self,count=1001): self.count=count; self.requests=[]; self.failure=False; self.gap=False; self.public=False; self.files={}
    def respond(self,request):
        self.requests.append(request)
        if self.failure: return httpx.Response(403,json={'message':'SYNTHETIC-SERVER-KEY must never leak','code':'42501','details':'','hint':''})
        path=request.url.path; params=request.url.params
        if '/storage/v1/bucket/' in path:
            return httpx.Response(200,json={'id':'hwfc-ap-private','name':'hwfc-ap-private','owner':'synthetic','public':self.public,
                'created_at':'2026-10-13T12:00:00Z','updated_at':'2026-10-13T12:00:00Z',
                'file_size_limit':20971520,'allowed_mime_types':['application/pdf','text/csv','application/octet-stream']})
        if '/rpc/' in path:
            body=json.loads(request.content)
            assert body.get('p_workspace')==CONFIG.workspace_id
            if path.endswith('ap_begin_access_attempt'): return httpx.Response(200,json=str(uuid4()))
            if path.endswith('ap_finish_access_attempt'): return httpx.Response(200,json=None)
            assert set(body)=={'p_workspace','p_request_id','p_payload_hash','p_data'}
            return httpx.Response(200,json={'statement_id':STATEMENT,'version':2})
        if path.startswith('/rest/v1/'):
            table=path.rsplit('/',1)[-1]
            expected='id' if table=='ap_workspaces' else 'workspace_id'
            assert params.get(expected)=='eq.'+CONFIG.workspace_id
            if table=='ap_workspaces': rows=[{'id':CONFIG.workspace_id,'active_import_id':IMPORT}]
            elif table=='ap_bill_imports': rows=[{'id':IMPORT,'workspace_id':CONFIG.workspace_id,'state':'ready','record_count':self.count,'metadata':{'label':'synthetic.csv','loaded':True,'simulated':False,'sourceFormat':'bill-native'},'created_at':'2026-10-13T12:00:00+00:00'}]
            elif table=='ap_bill_records':
                assert params.get('import_id')=='eq.'+IMPORT
                after=int(params.get('ordinal','gt.-1').split('.')[-1]); limit=int(params['limit'])
                rows=[{'ordinal':i,'record':{'vendor':'Synthetic','invoiceNumber':f'{i:06}','amount':18400}} for i in range(after+1,min(self.count,after+1+limit))]
                if self.gap: rows=rows[1:]
            elif table=='ap_statements': rows=[{'id':STATEMENT,'workspace_id':CONFIG.workspace_id,'current_revision_id':REVISION,'version':1,'filename':'synthetic.pdf','completed':False,'archived':False,'original_object_key':CONFIG.workspace_id+'/pdf/'+'a'*64+'.pdf'}]
            elif table=='ap_statement_revisions': rows=[{'id':REVISION,'statement_id':STATEMENT,'version':1,'doc':{'id':STATEMENT,'vendor':'Synthetic','filename':'synthetic.pdf','confirmed':False,'rows':[],'warnings':[],'pageCount':1},'resolutions':{},'results':[],'import_id':IMPORT,'mapping_snapshot':{},'rule_version':'ap-match-v2'}]
            elif table=='ap_vendor_mappings': rows=[]
            elif table=='ap_completion_events': rows=[]
            else: raise AssertionError('Unexpected table '+table)
            return httpx.Response(200,json=rows)
        if '/storage/v1/object/sign/' in path:
            assert int(json.loads(request.content)['expiresIn'])==300
            return httpx.Response(200,json={'signedURL':'/object/sign/hwfc-ap-private/'+CONFIG.workspace_id+'/pdf/'+'a'*64+'.pdf?token=synthetic'})
        if '/storage/v1/object/' in path:
            key=path.split('/hwfc-ap-private/',1)[1]
            if request.method=='POST':
                if key in self.files:return httpx.Response(409,json={'statusCode':'409','error':'Duplicate','message':'Exists'})
                from email.parser import BytesParser
                from email import policy
                message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+request.headers['content-type']+'\r\n\r\n').encode()+request.content)
                self.files[key]=next(part.get_payload(decode=True) for part in message.iter_parts() if part.get_param('name',header='content-disposition')=='file')
                return httpx.Response(200,json={'Key':'hwfc-ap-private/'+key,'Id':str(uuid4())})
            return httpx.Response(200,content=self.files[key])
        raise AssertionError('Unexpected HTTP operation '+path)

def make_repository(transport):
    from app.ap_shared.repository import ApRepository
    client=create_client(CONFIG.supabase_url,CONFIG.supabase_secret_key,ClientOptions(
        auto_refresh_token=False,persist_session=False,httpx_client=httpx.Client(transport=httpx.MockTransport(transport.respond))))
    return ApRepository(client,CONFIG)

class RepositoryTests(unittest.TestCase):
    def test_sdk_diagnostics_do_not_log_financial_query_values(self):
        import logging
        logger=logging.getLogger('httpx');previous=logger.level;logger.setLevel(logging.INFO)
        try:
            repo=make_repository(BackendTransport())
            with self.assertNoLogs('httpx',level='INFO'):
                repo.history_page(CONFIG.workspace_id,{'vendor':'Synthetic Sensitive Vendor'})
        finally:logger.setLevel(previous)
    def test_pagination_restores_all_records_with_stable_ids(self):
        for count in (1001,5610):
            with self.subTest(count=count):
                repo=make_repository(BackendTransport(count)); rows=[]; cursor=-1
                while True:
                    page=repo.records_page(CONFIG.workspace_id,IMPORT,cursor)
                    rows.extend(page['records'])
                    if page['nextCursor'] is None: break
                    cursor=page['nextCursor']
                self.assertEqual(len(rows),count); self.assertEqual(len({r['id'] for r in rows}),count)
                self.assertEqual(rows[0]['invoiceNumber'],'000000'); self.assertEqual(rows[-1]['invoiceNumber'],f'{count-1:06}')

    def test_missing_page_rows_fail_before_becoming_missing_invoices(self):
        transport=BackendTransport(); transport.gap=True; repo=make_repository(transport)
        from app.ap_shared.repository import ApStoreError
        with self.assertRaises(ApStoreError): repo.records_page(CONFIG.workspace_id,IMPORT,-1)

    def test_wrong_workspace_never_reaches_backend(self):
        transport=BackendTransport(); repo=make_repository(transport)
        with self.assertRaises(PermissionError): repo.statement(str(uuid4()),STATEMENT)
        self.assertEqual(len(transport.requests),0)

    def test_backend_error_does_not_echo_secret_or_payload(self):
        transport=BackendTransport(); transport.failure=True; repo=make_repository(transport)
        from app.ap_shared.repository import ApStoreError
        with self.assertRaises(ApStoreError) as error: repo.bootstrap(CONFIG.workspace_id)
        self.assertNotIn(CONFIG.supabase_secret_key,str(error.exception)); self.assertNotIn('must never leak',str(error.exception))

    def test_bootstrap_excludes_pdf_paths_and_secrets(self):
        repo=make_repository(BackendTransport()); snapshot=repo.bootstrap(CONFIG.workspace_id)
        self.assertEqual(snapshot['activeImport']['record_count'],1001)
        self.assertEqual(snapshot['statements'][0]['id'],STATEMENT)
        self.assertNotIn('original_object_key',json.dumps(snapshot)); self.assertNotIn(CONFIG.supabase_secret_key,json.dumps(snapshot))

    def test_signed_preview_only_for_owned_statement_and_short_expiry(self):
        repo=make_repository(BackendTransport())
        preview=repo.signed_pdf(CONFIG.workspace_id,STATEMENT)
        self.assertTrue(preview['url'].startswith(CONFIG.supabase_url+'/storage/v1/object/sign/'))
        self.assertEqual(preview['expiresIn'],300)
        with self.assertRaises(PermissionError): repo.signed_pdf(str(uuid4()),STATEMENT)

    def test_transaction_uses_named_restricted_rpc_contract(self):
        transport=BackendTransport(); repo=make_repository(transport)
        reply=repo.transact('save_revision',CONFIG.workspace_id,str(uuid4()),'a'*64,{'statement_id':STATEMENT,'expected_version':1})
        self.assertEqual(reply['version'],2)
        self.assertTrue(transport.requests[-1].url.path.endswith('/rpc/ap_save_revision'))

    def test_durable_limiter_uses_nonfinancial_rpc(self):
        transport=BackendTransport(); repo=make_repository(transport)
        ticket=repo.begin_attempt(str(uuid4()),NOW); self.assertTrue(ticket)
        repo.finish_attempt(ticket,False,NOW)
        self.assertTrue(all('/rpc/ap_' in req.url.path for req in transport.requests))

    def test_public_bucket_fails_closed_before_loading_financial_records(self):
        transport=BackendTransport(); transport.public=True; repo=make_repository(transport)
        from app.ap_shared.repository import ApStoreError
        with self.assertRaises(ApStoreError):repo.bootstrap(CONFIG.workspace_id)
        self.assertFalse(any('/rest/v1/' in str(req.url) for req in transport.requests))

    def test_private_originals_are_not_overwritten_on_retries(self):
        transport=BackendTransport(); repo=make_repository(transport)
        key=CONFIG.workspace_id+'/pdf/'+'b'*64+'.pdf'
        repo.write_bytes(CONFIG.workspace_id,key,b'%PDF-synthetic','application/pdf')
        repo.write_bytes(CONFIG.workspace_id,key,b'%PDF-synthetic','application/pdf')
        from app.ap_shared.repository import ApStoreError
        with self.assertRaises(ApStoreError):repo.write_bytes(CONFIG.workspace_id,key,b'different','application/pdf')
        self.assertEqual(repo.read_bytes(CONFIG.workspace_id,key),b'%PDF-synthetic')

    def test_private_duplicate_artifacts_allow_supported_rule_versions_only(self):
        from app.ap_shared.repository import ApStoreError
        transport=BackendTransport(); repo=make_repository(transport)
        for version in ['bill-duplicates-v1','bill-duplicates-v2']:
            key=CONFIG.workspace_id+'/bill-duplicates/v1/'+IMPORT+'/'+version+'/'+'b'*64+'.sqlite.gz'
            repo.write_bytes(CONFIG.workspace_id,key,b'synthetic-archive','application/gzip')
            self.assertEqual(repo.read_bytes(CONFIG.workspace_id,key),b'synthetic-archive')
        key=CONFIG.workspace_id+'/bill-duplicates/v2/'+IMPORT+'/bill-duplicates-v3/'+'b'*64+'.sqlite.gz'
        repo.write_bytes(CONFIG.workspace_id,key,b'synthetic-archive','application/gzip')
        self.assertEqual(repo.read_bytes(CONFIG.workspace_id,key),b'synthetic-archive')
        for key in [
            CONFIG.workspace_id+'/bill-duplicates/v1/'+IMPORT+'/bill-duplicates-v3/'+'b'*64+'.sqlite.gz',
            CONFIG.workspace_id+'/bill-duplicates/v2/'+IMPORT+'/bill-duplicates-v2/'+'b'*64+'.sqlite.gz',
            CONFIG.workspace_id+'/bill-duplicates/v1/'+IMPORT+'/bill-duplicates-v2/../'+'b'*64+'.sqlite.gz',
            str(uuid4())+'/bill-duplicates/v1/'+IMPORT+'/bill-duplicates-v2/'+'b'*64+'.sqlite.gz',
        ]:
            before=len(transport.requests)
            with self.assertRaises(ApStoreError):
                repo.write_bytes(CONFIG.workspace_id,key,b'synthetic-archive','application/gzip')
            self.assertEqual(len(transport.requests),before)

if __name__=='__main__': unittest.main()
