import contextlib
import io
import json
import unittest
from app.ap_mail.contracts import MailError

class AuthorizeTests(unittest.TestCase):
    def test_oauth_state_identity_and_missing_refresh(self):
        from workers.ap_mail.authorize import validate_callback,accept_grant,SCOPES
        self.assertEqual(validate_callback('/oauth2/callback?code=code&state=expected','expected'),'code')
        for path in ['/oauth2/callback?code=code&state=wrong','/oauth2/callback?code=code&state=expected&state=expected','/other?code=c&state=expected']:
            with self.assertRaises(MailError):validate_callback(path,'expected')
        token={'refresh_token':'SECRET','scope':' '.join(SCOPES),'access_token':'ACCESS'}
        identity={'email':'owner@example.test','email_verified':True,'sub':'123','nonce':'nonce'}
        for changes in [{'email':'other@example.test'},{'email_verified':False},{'nonce':'wrong'}]:
            with self.assertRaises(MailError):accept_grant(token,{**identity,**changes},'owner@example.test','nonce')
        with self.assertRaises(MailError):accept_grant({**token,'refresh_token':None},identity,'owner@example.test','nonce')
        with self.assertRaises(MailError):accept_grant({**token,'scope':'openid https://www.googleapis.com/auth/gmail.readonly'},identity,'owner@example.test','nonce')
        self.assertEqual(accept_grant(token,identity,'owner@example.test','nonce')['sub'],'123')
    def test_no_token_disk_or_stdout_and_secret_failure_is_safe(self):
        from workers.ap_mail.authorize import persist_grant,SCOPES
        class Secrets:
            def add(self,name,payload):
                self.value=json.loads(payload);return name+'/versions/1'
        secrets=Secrets();token={'refresh_token':'PRIVATE-REFRESH','access_token':'PRIVATE-ACCESS','scope':' '.join(SCOPES)}
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            result=persist_grant(secrets,'projects/synthetic-project/secrets/ap-mail',token,{'client_id':'id','client_secret':'CLIENT-SECRET'},
                {'sub':'123','email':'owner@example.test'}, {'id':'Label_1','name':'AP Statements'})
        self.assertEqual(output.getvalue(),'');self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('access_token',secrets.value)
        secrets.add=lambda *args:(_ for _ in ()).throw(RuntimeError('PRIVATE-REFRESH'))
        with self.assertRaises(MailError) as error:persist_grant(secrets,'projects/synthetic-project/secrets/ap-mail',token,{'client_id':'id','client_secret':'secret'}, {'sub':'123','email':'owner@example.test'}, {'id':'Label_1','name':'AP Statements'})
        self.assertNotIn('PRIVATE',str(error.exception))
