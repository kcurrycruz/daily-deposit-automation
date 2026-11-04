from datetime import timedelta
from uuid import uuid4
import unittest
from app.ap_mail.contracts import MailError
from app.ap_shared.models import ApValidationError
from test_ap_shared_service import fixture

class ControlsStore:
    def __init__(self):self.calls=[];self.is_enabled=True;self.callback=lambda:None
    def enabled(self):return self.is_enabled
    def read(self,action,payload):
        self.callback();return {'connection':None,'counts':{},'secret_ref':'must-not-return','items':[],'nextCursor':None}
    def control(self,action,payload,request):self.calls.append((action,payload,request));return {'saved':True}
    def preview(self,receipt):return {'url':'https://synthetic.supabase.co/storage/v1/object/sign/hwfc-ap-private/test','expiresIn':300}

class MailControlsTests(unittest.TestCase):
    def make(self):
        from app.ap_shared.mail.service import MailService
        service,repo,auth,state,clock=fixture();store=ControlsStore()
        service.mail_operations=MailService(store,service.config,service.clock,service._check)
        return service,store,auth,state,clock
    def test_controls_locked_expired_and_mid_request(self):
        service,store,auth,state,clock=self.make()
        store.callback=lambda:state.clear()
        with self.assertRaises(PermissionError):service.handle('mail_status',{},str(uuid4()),auth)
        self.assertEqual(store.calls,[])

    def test_pause_retry_history_bounds_and_replay(self):
        service,store,auth,state,clock=self.make();request=str(uuid4());rid=str(uuid4())
        service.handle('mail_pause',{'connection_id':rid,'expected_version':1,'paused':True},request,auth)
        self.assertEqual(store.calls[-1][0],'pause')
        for payload in [dict(after='2026-10-01T00:00:00Z',before='2026-10-02T00:00:00Z',max_messages=1001),
                        dict(after='2026-10-02T00:00:00Z',before='2026-10-01T00:00:00Z',max_messages=10)]:
            with self.assertRaises((ApValidationError,MailError)):service.handle('mail_history',{'connection_id':rid,'expected_version':1,**payload},request,auth)
        with self.assertRaises(ApValidationError):service.handle('mail_retry',{'receipt_id':rid,'expected_version':1,'workspace_id':rid},request,auth)

    def test_no_secrets_and_absent_capability(self):
        service,store,auth,_,_=self.make();result=service.handle('mail_status',{},str(uuid4()),auth)
        self.assertNotIn('secret_ref',result)
        store.is_enabled=False
        with self.assertRaises(MailError):service.handle('mail_status',{},str(uuid4()),auth)

    def test_receipt_preview_only_accepts_id_and_revalidates_url(self):
        service,store,auth,_,_=self.make();rid=str(uuid4())
        self.assertEqual(service.handle('mail_preview',{'receipt_id':rid},str(uuid4()),auth)['expiresIn'],300)
        store.preview=lambda rid:{'url':'https://attacker.example/test','expiresIn':300}
        with self.assertRaises(MailError):service.handle('mail_preview',{'receipt_id':rid},str(uuid4()),auth)
        with self.assertRaises(ApValidationError):service.handle('mail_preview',{'receipt_id':rid,'path':'elsewhere'},str(uuid4()),auth)

    def test_all_control_actions_require_current_auth(self):
        from app.ap_shared.models import MAIL_ACTIONS,validate_request
        service,store,auth,state,clock=self.make();state.clear()
        for action in MAIL_ACTIONS:
            envelope=dict(version=1,action=action,payload={},request_id=str(uuid4()),attempt=0)
            self.assertEqual(validate_request(envelope)['action'],action)
            with self.assertRaises(PermissionError):service.handle(action,{},envelope['request_id'],auth)

    def test_private_preview_repository_checks_exact_hash_path_and_signed_host(self):
        from app.ap_shared.mail.repository import MailControlsRepository
        from test_ap_mail_repository import RpcClient
        from test_ap_shared_access import CONFIG
        client=RpcClient();rid=str(uuid4());sha='a'*64;key=CONFIG.workspace_id+'/pdf/'+sha+'.pdf'
        url=CONFIG.supabase_url+'/storage/v1/object/sign/'+CONFIG.bucket+'/'+key+'?token=synthetic'
        bucket=type('Bucket',(),{'create_signed_url':lambda self,key,expires:{'signedURL':url}})()
        client.storage=type('Storage',(),{'from_':lambda self,name:bucket})()
        base=type('Base',(),{'config':CONFIG,'client':client,'_private_bucket':lambda self:None})()
        repo=MailControlsRepository(base)
        client.reply={'id':rid,'workspace_id':CONFIG.workspace_id,'sha256':sha,'original_object_key':key}
        self.assertEqual(repo.preview(rid)['url'],url)
        for change in [{'original_object_key':key.replace('/pdf/','/csv/')},{'workspace_id':str(uuid4())}]:
            old=client.reply.copy();client.reply.update(change)
            with self.assertRaises(MailError):repo.preview(rid)
            client.reply=old
        url='https://attacker.example/storage/v1/object/sign/'+CONFIG.bucket+'/'+key
        with self.assertRaises(MailError):repo.preview(rid)
