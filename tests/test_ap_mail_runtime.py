import io
import json
import unittest
from uuid import uuid4

CALLER='ap-mail-tasks@synthetic-project.iam.gserviceaccount.com';AUD='https://processor-synthetic.run.app'
class RuntimeTests(unittest.TestCase):
    def make(self,role='processor',claims=None):
        from workers.ap_mail.http import Application
        calls=[]
        valid=dict(iss='https://accounts.google.com',aud=AUD,email=CALLER,email_verified=True,sub='123',exp=2000)
        if claims:valid.update(claims)
        app=Application(role,AUD,CALLER,lambda token,aud:valid,lambda:1000,
            {'process':lambda data:calls.append(data) or {'status':'awaiting_review','retry':False},
             'poll':lambda data:{'status':'ok'},'dispatch-reconcile':lambda data:{'status':'ok'}})
        return app,calls
    def test_wrong_oidc_caller_audience_role(self):
        body=json.dumps(dict(job_id=str(uuid4()),dispatch_generation=1)).encode()
        for change in [dict(aud='wrong'),dict(email='other@example.test'),dict(exp=999),dict(email_verified=False),dict(iss='https://attacker.example')]:
            app,calls=self.make(claims=change);self.assertEqual(app.handle('POST','/process',{'Authorization':'Bearer signed'},body)[0],403);self.assertEqual(calls,[])
        app,calls=self.make();self.assertEqual(app.handle('POST','/process',{'X-CloudTasks-TaskName':'forged'},body)[0],403)
        self.assertEqual(app.handle('POST','/poll',{'Authorization':'Bearer signed'},b'{}')[0],404)
        self.assertEqual(app.handle('POST','/process',{'Authorization':'Bearer signed'},body)[0],200)
    def test_bounded_body_and_log_redaction(self):
        app,calls=self.make()
        for body in [b'x'*4097,b'{"url":"https://attacker"}',b'{"job_id":"bad"}',b'{"job_id":"a","job_id":"b"}']:
            self.assertEqual(app.handle('POST','/process',{'Authorization':'Bearer signed'},body)[0],400)
        self.assertEqual(calls,[])
        app.handlers['process']=lambda data:(_ for _ in ()).throw(RuntimeError('TOKEN SECRET PDF TEXT'))
        code,result=app.handle('POST','/process',{'Authorization':'Bearer signed'},json.dumps(dict(job_id=str(uuid4()),dispatch_generation=1)).encode())
        self.assertEqual(code,503);self.assertNotIn('SECRET',json.dumps(result))
        status=[];env={'REQUEST_METHOD':'POST','PATH_INFO':'/process','CONTENT_LENGTH':'99999','wsgi.input':io.BytesIO(b'not read')}
        self.assertNotIn(b'SECRET',b''.join(app(env,lambda s,h:status.append(s))));self.assertTrue(status[0].startswith('400'))

    def test_transport_bounds_response_and_never_follows_redirects(self):
        import httpx
        from workers.ap_mail.runtime import BoundedTransport
        from app.ap_mail.contracts import MailError
        transport=BoundedTransport(httpx.MockTransport(lambda req:httpx.Response(200,content=b'{"large":"'+b'x'*20+b'"}')))
        with self.assertRaises(MailError):transport.request('GET','https://gmail.googleapis.com/test',headers={},params={},timeout=1,max_bytes=8)

    def test_recompare_does_not_initialize_gmail_and_custom_audience_is_pinned(self):
        from workers.ap_mail.runtime import DeferredGmail
        from app.ap_mail.dispatch import DispatchConfig
        calls=[];lazy=DeferredGmail(lambda:calls.append('initialized') or type('Client',(),{'label_id':'Label_1'})())
        self.assertEqual(calls,[]);self.assertEqual(lazy.label_id,'Label_1');self.assertEqual(calls,['initialized'])
        config=DispatchConfig('projects/synthetic-project/locations/us-east1/queues/ap-mail','https://processor.run.app/process',CALLER,'https://ap-mail-processor.synthetic-project.internal')
        self.assertEqual(config.audience,'https://ap-mail-processor.synthetic-project.internal')
