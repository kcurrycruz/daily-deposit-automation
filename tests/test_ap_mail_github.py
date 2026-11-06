import contextlib
import io
import importlib.util
import inspect
import json
import subprocess
import unittest
from unittest.mock import patch
from app.ap_mail.contracts import MailError

REPOSITORY='kcurrycruz/daily-deposit-automation'
REFERENCE='github:'+REPOSITORY+':AP_MAIL_GMAIL_GRANT'


def grant():
    from workers.ap_mail.authorize import SCOPES
    return dict(refresh_token='PRIVATE-REFRESH',client_id='client',client_secret='PRIVATE-CLIENT',
                token_uri='https://oauth2.googleapis.com/token',account_id='123',
                email='owner@example.test',label_id='Label_1',scopes=list(SCOPES))


class GithubGrantTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('workers.ap_mail.github'), 'GitHub grant adapter is missing')
        from workers.ap_mail import github
        return github

    def test_fixed_reference_and_strict_environment_grant(self):
        api=self.api()
        self.assertEqual(api.grant_reference(REPOSITORY),REFERENCE)
        with self.assertRaises(MailError):api.grant_reference('other/repository')
        store=api.EnvironmentGrantStore(REFERENCE,json.dumps(grant()))
        self.assertEqual(store.read(REFERENCE),grant())
        with self.assertRaises(MailError):store.read('github:other/repo:AP_MAIL_GMAIL_GRANT')
        for raw in ['not json','{}','x'*16385,json.dumps({**grant(),'access_token':'PRIVATE'}),
                    json.dumps({**grant(),'scopes':['openid']}),json.dumps({**grant(),'token_uri':'https://wrong.example'})]:
            with self.assertRaises(MailError):api.EnvironmentGrantStore(REFERENCE,raw).read(REFERENCE)
        duplicate=json.dumps(grant())[:-1]+',"email":"attacker@example.test"}'
        with self.assertRaises(MailError):api.EnvironmentGrantStore(REFERENCE,duplicate).read(REFERENCE)

    def test_owner_secret_write_uses_stdin_and_no_shell_or_output(self):
        api=self.api();calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs))
            data={'nameWithOwner':REPOSITORY,'isPrivate':False,'viewerPermission':'WRITE'}
            return subprocess.CompletedProcess(args,0,json.dumps(data).encode(),b'')
        store=api.GitHubSecretStore(REPOSITORY,run=run)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            store.validate();result=store.add(REFERENCE,json.dumps(grant()).encode())
        self.assertEqual(output.getvalue(),'');self.assertEqual(result,REFERENCE)
        args,kwargs=calls[-1]
        self.assertEqual(args[1:],['secret','set','AP_MAIL_GMAIL_GRANT','--repo',REPOSITORY])
        self.assertEqual(kwargs['input'],json.dumps(grant()).encode())
        self.assertFalse(kwargs.get('shell',False));self.assertTrue(kwargs['capture_output'])
        self.assertLessEqual(kwargs['timeout'],30)
        self.assertNotIn('PRIVATE',str(args));self.assertNotIn('PRIVATE',result)
        self.assertEqual(calls[0][0][1:],['auth','status','--active','--hostname','github.com'])
        self.assertEqual(calls[1][0][1:4],['repo','view',REPOSITORY])

    def test_wrong_repo_permissions_cli_errors_and_sensitive_output_are_safe(self):
        api=self.api()
        for data in [{'nameWithOwner':'other/repository','isPrivate':False,'viewerPermission':'ADMIN'},
                     {'nameWithOwner':REPOSITORY,'isPrivate':True,'viewerPermission':'ADMIN'},
                     {'nameWithOwner':REPOSITORY,'isPrivate':False,'viewerPermission':'READ'}]:
            def run(args,**kwargs):return subprocess.CompletedProcess(args,0,json.dumps(data).encode(),b'')
            with self.assertRaises(MailError):api.GitHubSecretStore(REPOSITORY,run=run).validate()
        for failure in [FileNotFoundError('PRIVATE'),subprocess.TimeoutExpired('gh',30,output=b'PRIVATE')]:
            def run(*args,**kwargs):raise failure
            with self.assertRaises(MailError) as caught:api.GitHubSecretStore(REPOSITORY,run=run).validate()
            self.assertNotIn('PRIVATE',str(caught.exception))
        def failed(*args,**kwargs):return subprocess.CompletedProcess([],1,b'PRIVATE',b'PRIVATE')
        with self.assertRaises(MailError) as caught:api.GitHubSecretStore(REPOSITORY,run=failed).validate()
        self.assertNotIn('PRIVATE',str(caught.exception))

    def test_destination_is_validated_before_opening_oauth(self):
        from workers.ap_mail.authorize import authorize
        self.assertIn('store',inspect.signature(authorize).parameters,'injectable grant destination is missing')
        class Store:
            def validate(self):raise MailError('denied')
        with patch('webbrowser.open') as opened:
            with self.assertRaises(MailError) as caught:
                authorize('does-not-exist.json','owner@example.test','AP Statements',REFERENCE,store=Store())
        self.assertEqual(caught.exception.code,'denied');opened.assert_not_called()

    def test_github_cli_destination_and_cloud_destination_are_exclusive(self):
        from workers.ap_mail.authorize import main
        with patch('sys.argv',['authorize','--client-json','client.json','--expected-email','owner@example.test',
                              '--secret','projects/test/secrets/gmail','--github-repo',REPOSITORY]),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:main()
        self.assertEqual(caught.exception.code,2)

    def test_github_cli_selects_private_direct_destination(self):
        api=self.api()
        from workers.ap_mail.authorize import main
        with patch('sys.argv',['authorize','--client-json','client.json','--expected-email','owner@example.test','--github-repo',REPOSITORY]), \
             patch('workers.ap_mail.authorize.authorize',return_value={'secret_ref':REFERENCE}) as authorize,contextlib.redirect_stdout(io.StringIO()) as output:
            main()
        self.assertIsInstance(authorize.call_args.kwargs['store'],api.GitHubSecretStore)
        self.assertNotIn('PRIVATE',output.getvalue())

    def test_shared_processor_does_not_construct_a_cloud_dispatcher(self):
        self.assertIsNotNone(importlib.util.find_spec('workers.ap_mail.shared'),'shared processor construction is missing')
        from workers.ap_mail.shared import build_processor
        from test_ap_mail_repository import MailRepositoryTests
        calls=[]
        repository,_=MailRepositoryTests().repo()
        processor,caches=build_processor(repository,lambda:calls.append('gmail'))
        self.assertIsNotNone(processor.sources);self.assertIsNotNone(processor.publication)
        self.assertIsNotNone(caches);self.assertEqual(calls,[])
