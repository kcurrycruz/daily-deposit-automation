import unittest
from uuid import uuid4
from app.ap_mail.contracts import MailConfig, MailError

W='00000000-0000-4000-8000-000000000001'
C='00000000-0000-4000-8000-000000000002'


class RpcClient:
    def __init__(self): self.calls=[];self.reply={};self.error=None
    def rpc(self,name,args): self.calls.append((name,args));return self
    def execute(self):
        if self.error: raise self.error
        return type('Reply',(),{'data':self.reply})()


class MailRepositoryTests(unittest.TestCase):
    def test_batch_pending_pins_connection_and_validates_bounds(self):
        repo,client=self.repo()
        self.assertTrue(callable(getattr(repo,'batch_pending',None)), 'connection-scoped batch read is missing')
        client.reply={'items':[],'nextCursor':None}
        self.assertEqual(repo.batch_pending(1)['items'],[])
        name,args=client.calls[-1]
        self.assertEqual(name,'ap_mail_batch_pending')
        self.assertEqual(args,dict(p_workspace=W,p_connection=C,p_generation=1,p_cursor=None,p_limit=25))
        for generation,cursor,limit in [(0,None,25),(True,None,25),(1,'bad',25),(1,None,0),(1,None,101)]:
            with self.assertRaises(MailError):repo.batch_pending(generation,cursor,limit)

    def test_mail_capability_is_optional_and_versioned(self):
        import httpx
        from test_ap_shared_repository import BackendTransport, make_repository
        from test_ap_shared_access import CONFIG
        class MailTransport(BackendTransport):
            mail_version=None
            def respond(self,request):
                reply=super().respond(request)
                if request.url.path.endswith('/ap_workspaces') and self.mail_version is not None:
                    rows=reply.json();rows[0]['mail_schema_version']=self.mail_version
                    return httpx.Response(200,json=rows)
                return reply
        for version,enabled in [(None,False),(1,True),(2,False)]:
            transport=MailTransport();transport.mail_version=version
            caps=make_repository(transport).bootstrap(CONFIG.workspace_id)['capabilities']
            self.assertEqual(caps.get('mailIntake')==1,enabled)

    def repo(self):
        from app.ap_mail.repository import MailRepository
        client=RpcClient()
        return MailRepository(MailConfig('https://synthetic.supabase.co','TEST-SECRET',W,'hwfc-ap-private',C,'checker'),client),client

    def test_rpc_pins_workspace_and_idempotency_hash(self):
        repo,client=self.repo();request=str(uuid4())
        repo.mutate('reconcile',{'limit':100},request)
        name,args=client.calls[-1]
        self.assertEqual(name,'ap_mail_mutate')
        self.assertEqual(args['p_workspace'],W)
        self.assertEqual(args['p_request_id'],request)
        prior=args['p_payload_hash']
        repo.mutate('reconcile',{'limit':100},request)
        self.assertEqual(client.calls[-1][1]['p_payload_hash'],prior)
        repo.mutate('reconcile',{'limit':99},request)
        self.assertNotEqual(client.calls[-1][1]['p_payload_hash'],prior)
        with self.assertRaises(MailError): repo.mutate('complete_revision',{},str(uuid4()))
        with self.assertRaises(MailError): repo.mutate('reconcile',{'workspace_id':C},str(uuid4()))
        with self.assertRaises(MailError): repo.mutate('reconcile',{'limit':100,'unexpected':True},str(uuid4()))

    def test_backend_error_does_not_escape(self):
        repo,client=self.repo()
        client.error=RuntimeError('TOKEN AND PDF TEXT')
        with self.assertRaises(MailError) as e: repo.mutate('reconcile',{'limit':100},str(uuid4()))
        self.assertEqual(str(e.exception),'unavailable')

    def test_sync_reads_and_error_status_keep_account_scope(self):
        repo,client=self.repo()
        client.reply={'items':[{'message_id':'m1','eligible':False,'error_code':'historical'}]}
        self.assertEqual(repo.messages_known(['m1'])['m1']['error_code'],'historical')
        self.assertEqual(client.calls[-1][1]['p_data']['connection_id'],C)
        client.reply={'saved':True}
        repo.mutate('sync_error',{'connection_id':C,'expected_generation':1,'reason':'auth'})
        self.assertEqual(client.calls[-1][1]['p_workspace'],W)

    def test_safe_read_and_preview_only_accept_receipt_identity(self):
        repo,client=self.repo();rid=str(uuid4())
        client.reply={'connection':None};self.assertEqual(repo.connection(),None)
        self.assertEqual(client.calls[-1][1]['p_workspace'],W)
        client.reply={'items':[],'nextCursor':None}
        self.assertEqual(repo.receipts_page({},None,50)['items'],[])
        with self.assertRaises(MailError): repo.receipts_page({},None,51)
        with self.assertRaises(MailError): repo.private_original('../other.pdf')
        client.reply={'id':rid,'workspace_id':C,'sha256':'a'*64,'original_object_key':W+'/pdf/'+'a'*64+'.pdf'}
        with self.assertRaises(MailError): repo.private_original(rid)

