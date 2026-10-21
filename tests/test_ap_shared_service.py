import base64
import hashlib
import json
import unittest
from datetime import timedelta
from uuid import uuid4
from test_ap_shared_access import CONFIG,NOW,TestLimiter

class StorageDouble:
    """Cloud boundary with strict byte storage and request identity semantics."""
    def __init__(self):
        self.objects={}; self.uploads={}; self.requests={}; self.completion_events=[]; self.version=2
    def upload_info(self,workspace,upload_id): return self.uploads[upload_id]
    def write_bytes(self,workspace,key,data,content_type):
        if key in self.objects and self.objects[key]!=data: raise RuntimeError('immutable')
        self.objects[key]=data
    def read_bytes(self,workspace,key): return self.objects[key]
    def transact(self,operation,workspace,request_id,payload_hash,data):
        from app.ap_shared.repository import ApStoreError
        if request_id in self.requests:
            old_hash,response=self.requests[request_id]
            if old_hash!=payload_hash: raise ApStoreError('conflict')
            return response
        if operation=='begin_upload':
            self.uploads[data['upload_id']]={**data,'state':'staging','chunks':{},'object_key':None}
            response={'upload_id':data['upload_id'],'state':'staging'}
        elif operation=='put_chunk':
            upload=self.uploads[data['upload_id']]
            upload['chunks'][str(data['index'])]={'hash':data['chunk_hash'],'size':data['size']}
            response={'upload_id':data['upload_id'],'index':data['index']}
        elif operation=='finish_upload':
            upload=self.uploads[data['upload_id']]; upload.update(state='ready',object_key=data['object_key'])
            response={'upload_id':data['upload_id'],'state':'ready'}
        elif operation=='register_statement': response={'statement_id':data['statement_id'],'version':1,'duplicate':False}
        elif operation=='complete_revision':
            if data['expected_version']!=self.version: raise ApStoreError('conflict')
            self.completion_events.append(data.copy()); self.version+=1
            response={'statement_id':data['statement_id'],'version':self.version}
        elif operation=='save_revision':
            if data['expected_version']!=self.version: raise ApStoreError('conflict')
            self.version+=1; response={'statement_id':data['statement_id'],'version':self.version}
        else: raise AssertionError('Unexpected write '+operation)
        self.requests[request_id]=(payload_hash,response)
        return response

def fixture():
    from app.ap_shared.access import attempt_unlock,require_access
    from app.ap_shared.service import ApService
    state={}; attempt_unlock(state,CONFIG.password,CONFIG,TestLimiter(),NOW)
    clock=[NOW]; repo=StorageDouble()
    revalidate=lambda:require_access(state,CONFIG,clock[0])
    return ApService(repo,CONFIG,lambda:clock[0],revalidate),repo,revalidate(),state,clock

class ServiceTests(unittest.TestCase):
    def test_adventure_reference_evidence_can_be_saved_without_reinterpreting_legacy_results(self):
        from app.ap_shared.models import ApValidationError
        service,_,_,_,_=fixture()
        row={'id':'row','status':'presence','candidates':[],
             'referenceRule':'adventure-trailing-letter-v1'}
        self.assertEqual(service._results([row])[0]['referenceRule'],'adventure-trailing-letter-v1')
        legacy={key:value for key,value in row.items() if key!='referenceRule'}
        self.assertNotIn('referenceRule',service._results([legacy])[0])
        with self.assertRaises(ApValidationError):
            service._results([{**row,'referenceRule':'ignore-any-invoice-number'}])

    def test_current_frontend_rule_can_save_through_server_validation(self):
        import subprocess
        from pathlib import Path
        from test_ap_shared_models import valid_doc
        module=(Path(__file__).resolve().parents[1]/'app/ap_statements/frontend/core.mjs').as_uri()
        version=subprocess.check_output(['node','--input-type=module','-e',f'import {{MATCH_RULE_VERSION}} from {json.dumps(module)};process.stdout.write(MATCH_RULE_VERSION)'],text=True)
        service,repo,auth,_,_=fixture()
        doc=valid_doc()
        payload={'statement_id':doc['id'],'expected_version':2,'doc':doc,'resolutions':{},
                 'import_id':None,'mapping_snapshot':{},'results':[],'rule_version':version}
        saved=service.handle('save_revision',payload,str(uuid4()),auth)
        self.assertEqual(saved['version'],3)

    def upload(self,service,auth,raw=b'%PDF-synthetic',kind='pdf',declared_hash=None):
        metadata={'kind':kind,'filename':'synthetic.'+kind,'size':len(raw),'file_hash':declared_hash or hashlib.sha256(raw).hexdigest()}
        result=service.handle('upload_begin',metadata,str(uuid4()),auth)
        service.handle('upload_chunk',{'upload_id':result['upload_id'],'index':0,'data':base64.b64encode(raw).decode()},str(uuid4()),auth)
        return result['upload_id']

    def test_upload_finish_preserves_original_and_creates_unconfirmed_draft(self):
        service,repo,auth,_,_=fixture(); upload=self.upload(service,auth)
        result=service.handle('upload_finish',{'upload_id':upload},str(uuid4()),auth)
        self.assertIn('statement_id',result)
        key=CONFIG.workspace_id+'/pdf/'+hashlib.sha256(b'%PDF-synthetic').hexdigest()+'.pdf'
        self.assertEqual(repo.objects[key],b'%PDF-synthetic')
        saved=[entry[1] for entry in repo.requests.values() if 'statement_id' in entry[1]]
        self.assertEqual(len(saved),1)

    def test_upload_hash_mismatch_does_not_publish_original(self):
        service,repo,auth,_,_=fixture(); upload=self.upload(service,auth,declared_hash='a'*64)
        with self.assertRaises(ValueError): service.handle('upload_finish',{'upload_id':upload},str(uuid4()),auth)
        self.assertFalse(any('/pdf/' in key for key in repo.objects))

    def test_wrong_file_kind_does_not_publish(self):
        service,repo,auth,_,_=fixture(); upload=self.upload(service,auth,raw=b'not a PDF')
        with self.assertRaises(ValueError): service.handle('upload_finish',{'upload_id':upload},str(uuid4()),auth)
        self.assertFalse(any('/pdf/' in key for key in repo.objects))

    def test_bad_chunk_order_base64_and_oversize_file_are_rejected(self):
        service,repo,auth,_,_=fixture()
        from app.ap_shared.models import MAX_FILE_BYTES
        with self.assertRaises(ValueError): service.handle('upload_begin',{'kind':'pdf','filename':'x.pdf','size':MAX_FILE_BYTES+1,'file_hash':'a'*64},str(uuid4()),auth)
        upload=self.upload(service,auth)
        with self.assertRaises(ValueError): service.handle('upload_chunk',{'upload_id':upload,'index':1,'data':'bad base64'},str(uuid4()),auth)

    def test_completion_retry_is_idempotent_and_notes_are_optional(self):
        service,repo,auth,_,_=fixture(); request=str(uuid4())
        payload={'statement_id':str(uuid4()),'expected_version':2,'initials':'kc'}
        first=service.handle('complete_revision',payload,request,auth)
        self.assertEqual(first,service.handle('complete_revision',payload,request,auth))
        self.assertEqual(len(repo.completion_events),1); self.assertEqual(repo.completion_events[0]['initials'],'KC')
        self.assertEqual(repo.completion_events[0]['notes'],'')
        with self.assertRaises(ValueError): service.handle('complete_revision',{**payload,'initials':''},str(uuid4()),auth)

    def test_changed_payload_cannot_replay_completion_request(self):
        service,repo,auth,_,_=fixture(); request=str(uuid4())
        payload={'statement_id':str(uuid4()),'expected_version':2,'initials':'KC','notes':''}
        service.handle('complete_revision',payload,request,auth)
        from app.ap_shared.repository import ApStoreError
        with self.assertRaises(ApStoreError): service.handle('complete_revision',{**payload,'notes':'Changed'},request,auth)
        self.assertEqual(len(repo.completion_events),1)

    def test_expired_or_locked_authorization_stops_pending_upload(self):
        service,repo,auth,state,clock=fixture(); upload=self.upload(service,auth)
        clock[0]=NOW+timedelta(hours=8)
        with self.assertRaises(PermissionError): service.handle('upload_finish',{'upload_id':upload},str(uuid4()),auth)
        self.assertFalse(any('/pdf/' in key for key in repo.objects))
        clock[0]=NOW
        from app.ap_shared.access import lock_access
        lock_access(state)
        with self.assertRaises(PermissionError): service.handle('upload_finish',{'upload_id':upload},str(uuid4()),auth)

    def test_upload_from_another_authorized_session_is_not_editable(self):
        service,repo,auth,state,clock=fixture(); upload=self.upload(service,auth)
        from app.ap_shared.access import attempt_unlock,require_access
        attempt_unlock(state,CONFIG.password,CONFIG,TestLimiter(),NOW)
        state['_ap_session_nonce']=str(uuid4())
        with self.assertRaises(PermissionError): service.handle('upload_finish',{'upload_id':upload},str(uuid4()),auth)

    def test_arbitrary_client_storage_targets_are_rejected(self):
        service,repo,auth,_,_=fixture()
        with self.assertRaises(ValueError): service.handle('upload_begin',{'kind':'pdf','filename':'x','size':1,'file_hash':'a'*64,'object_key':'other-workspace/private'},str(uuid4()),auth)
        self.assertEqual(repo.uploads,{})

    def test_pdf_finish_retry_remains_identical_when_server_clock_advances(self):
        service,repo,auth,_,clock=fixture(); upload=self.upload(service,auth); request=str(uuid4())
        first=service.handle('upload_finish',{'upload_id':upload},request,auth)
        clock[0]=NOW+timedelta(seconds=3)
        self.assertEqual(first,service.handle('upload_finish',{'upload_id':upload},request,auth))

    def test_review_save_retry_does_not_change_payload_on_server_clock_tick(self):
        from app.ap_shared.models import RULE_VERSION
        service,repo,auth,_,clock=fixture()
        from test_ap_shared_models import valid_doc
        doc=valid_doc(); request=str(uuid4())
        payload={'statement_id':doc['id'],'expected_version':2,'doc':doc,'resolutions':{'r':{'decision':'Reviewed — no action needed','note':''}},
                 'import_id':None,'mapping_snapshot':{},'results':[{'id':'r','status':'possible','candidates':[]}],'rule_version':RULE_VERSION}
        first=service.handle('save_revision',payload,request,auth)
        clock[0]=NOW+timedelta(seconds=3)
        self.assertEqual(first,service.handle('save_revision',payload,request,auth))

if __name__=='__main__': unittest.main()
