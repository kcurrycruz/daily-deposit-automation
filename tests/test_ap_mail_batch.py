import contextlib
from copy import deepcopy
import importlib.util
import io
import json
import unittest
from unittest.mock import patch
from app.ap_mail.contracts import MailConfig,MailError
from app.ap_mail.sync import PollSummary
from test_ap_mail_github import REPOSITORY,REFERENCE,grant
from test_ap_mail_repository import W,C


def environment():
    return dict(AP_MAIL_BATCH_ENABLED='true',AP_MAIL_SCHEDULE_ENABLED='true',GITHUB_REPOSITORY=REPOSITORY,
        GITHUB_REF='refs/heads/main',GITHUB_EVENT_NAME='schedule',
        GITHUB_WORKFLOW_REF=REPOSITORY+'/.github/workflows/ap-mail-batch.yml@refs/heads/main',
        RUNNER_ENVIRONMENT='github-hosted',RUNNER_OS='Linux',RUNNER_ARCH='X64',
        AP_MAIL_RUNNER='ubuntu-24.04',AP_MAIL_SOURCE_SHA='a'*40,
        AP_MAIL_SUPABASE_URL='https://synthetic.supabase.co',AP_MAIL_SUPABASE_KEY='PRIVATE-DATABASE',
        AP_MAIL_WORKSPACE_ID=W,AP_MAIL_CONNECTION_ID=C,AP_MAIL_BUCKET='hwfc-ap-private',
        AP_MAIL_GMAIL_GRANT=json.dumps(grant()))


def event():
    return {'repository':{'full_name':REPOSITORY,'private':False,'default_branch':'main'}}


def job(n):
    value=f'00000000-0000-4000-8000-{n:012x}'
    return dict(job_id=value,receipt_id=value,dispatch_generation=1,mode='extract')


class Repository:
    def __init__(self,pages=None):
        self.config=MailConfig('https://synthetic.supabase.co','PRIVATE-DATABASE',W,'hwfc-ap-private',C,'processor')
        self.home=dict(id=C,workspace_id=W,account_id='123',email='owner@example.test',label_id='Label_1',
                       secret_ref=REFERENCE,active=True,paused=False,generation=1)
        self.pages=pages or {None:{'items':[],'nextCursor':None}}
        self.calls=[];self.on_page=None
    def connection(self):return deepcopy(self.home)
    def mutate(self,operation,payload):self.calls.append((operation,payload));return {'recovered':0}
    def queue_stale(self,limit):self.calls.append(('stale',limit));return {'queued':0}
    def batch_pending(self,generation,cursor=None,limit=25):
        self.calls.append(('page',generation,cursor,limit))
        if self.on_page:self.on_page()
        return deepcopy(self.pages.get(cursor,self.pages[None]))


class Sync:
    def __init__(self,summary=None):self.summary=summary or PollSummary('ok');self.calls=[]
    def poll(self,*args,**kwargs):self.calls.append((args,kwargs));return self.summary


class BatchTests(unittest.TestCase):
    def test_manual_acceptance_can_run_before_schedule_activation(self):
        api=self.api();env={**environment(),'AP_MAIL_SCHEDULE_ENABLED':'false'}
        with self.assertRaises(MailError) as caught:api.validate_context(env,event())
        self.assertEqual(caught.exception.code,'paused')
        env['GITHUB_EVENT_NAME']='workflow_dispatch'
        self.assertEqual(api.validate_context(env,event()).mail.connection_id,C)

    def test_real_sql_pdf_batch_recovers_and_preserves_human_history(self):
        from fixtures.ap_mail.batch_run_check import run_batch_check
        run_batch_check()

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('workers.ap_mail.batch'),'finite batch runner is missing')
        from workers.ap_mail import batch
        return batch

    def make(self,pages=None,clock=lambda:0,result=None):
        api=self.api();repo=Repository(pages);calls=[]
        def process(ident,generation):calls.append((ident,generation));return result or {'status':'awaiting_review'}
        runner=api.BatchRunner(repo,lambda:(_ for _ in ()).throw(AssertionError('No eager Gmail access')),process,clock=clock)
        runner.sync=Sync()
        return runner,repo,calls

    def test_context_only_allows_enabled_public_reviewed_standard_runner(self):
        api=self.api();config=api.validate_context(environment(),event())
        self.assertEqual((config.budget_seconds,config.max_jobs),(840,10))
        self.assertEqual(config.mail.connection_id,C);self.assertEqual(config.grant_ref,REFERENCE)
        self.assertNotIn('PRIVATE',repr(config))
        changes=[{'AP_MAIL_BATCH_ENABLED':'false'},{'GITHUB_REPOSITORY':'other/repository'},
                 {'GITHUB_REF':'refs/heads/feature'},{'GITHUB_EVENT_NAME':'pull_request'},
                 {'GITHUB_WORKFLOW_REF':'other/workflow@refs/heads/main'},
                 {'RUNNER_ENVIRONMENT':'self-hosted'},{'RUNNER_OS':'Windows'},
                 {'AP_MAIL_RUNNER':'paid-custom-runner'},{'AP_MAIL_SOURCE_SHA':'DD-v2'},
                 {'AP_MAIL_GMAIL_GRANT':''},{'AP_MAIL_SUPABASE_KEY':''},{'AP_MAIL_WORKSPACE_ID':'bad'}]
        for changeset in changes:
            with self.subTest(changes=changeset),self.assertRaises(MailError):api.validate_context({**environment(),**changeset},event())
        for changeset in [{'private':True},{'private':'false'},{'full_name':'other/repo'},{'default_branch':'other'}]:
            with self.assertRaises(MailError):api.validate_context(environment(),{'repository':{**event()['repository'],**changeset}})

    def test_empty_run_separates_discovery_from_processing(self):
        runner,repo,calls=self.make();runner.sync=Sync(PollSummary('ok',3,2,1,True))
        result=runner.run()
        self.assertEqual((result['discovered'],result['queued'],result['attempted']),(3,2,0))
        self.assertEqual(result['discovery_status'],'ok');self.assertEqual(calls,[])
        self.assertEqual([value for value in repo.calls if value[0]=='stale'],[('stale',50)])
        self.assertFalse(runner.sync.calls[0][1]['queue_stale'])

    def test_pause_and_generation_change_never_start_a_new_job(self):
        runner,repo,calls=self.make({None:{'items':[job(10)],'nextCursor':None}})
        repo.home['paused']=True;self.assertEqual(runner.run()['status'],'paused')
        self.assertEqual(calls,[]);self.assertEqual(repo.calls,[('reconcile',{'limit':100})])
        for change in [{'paused':True},{'generation':2},{'account_id':'other'},{'secret_ref':'wrong'}]:
            runner,repo,calls=self.make({None:{'items':[job(10)],'nextCursor':None}})
            repo.on_page=lambda:repo.home.update(change)
            runner.run();self.assertEqual(calls,[])

    def test_pagination_caps_and_deferred_jobs_do_not_spin(self):
        pages={None:{'items':[job(n) for n in range(10,35)],'nextCursor':job(34)['job_id']},
               job(34)['job_id']:{'items':[job(40)],'nextCursor':None}}
        runner,repo,calls=self.make(pages,result={'status':'not_claimed','retry':True})
        result=runner.run();self.assertEqual(len(calls),10);self.assertEqual(result['not_claimed'],10)
        self.assertTrue(result['next_work'])
        runner,repo,calls=self.make({None:{'items':[job(10)],'nextCursor':job(10)['job_id']},
                                   job(10)['job_id']:{'items':[job(20)],'nextCursor':None}})
        self.assertEqual(runner.run()['attempted'],2)
        self.assertEqual([x[2] for x in repo.calls if x[0]=='page'],[None,job(10)['job_id']])
        runner,repo,calls=self.make({None:{'items':[],'nextCursor':job(10)['job_id']},
                                   job(10)['job_id']:{'items':[],'nextCursor':job(10)['job_id']}})
        result=runner.run();self.assertLessEqual(len([x for x in repo.calls if x[0]=='page']),10)
        self.assertEqual(calls,[])

    def test_budget_reserves_a_full_existing_pdf_limit(self):
        now=[0]
        runner,repo,calls=self.make({None:{'items':[job(10),job(20)],'nextCursor':None}},clock=lambda:now[0])
        original=runner.process
        def process(*args):
            result=original(*args);now[0]=241;return result
        runner.process=process
        result=runner.run();self.assertEqual(len(calls),1);self.assertTrue(result['next_work'])
        runner,repo,calls=self.make({None:{'items':[job(10)],'nextCursor':None}})
        self.assertEqual(runner.run(budget_seconds=599)['attempted'],0);self.assertEqual(calls,[])
        for settings in [{'budget_seconds':0},{'budget_seconds':841},{'max_jobs':11},{'max_jobs':True}]:
            with self.assertRaises(MailError):runner.run(**settings)

    def test_discovery_failure_allows_saved_extraction_recompare(self):
        row={**job(10),'mode':'recompare'}
        runner,repo,calls=self.make({None:{'items':[row],'nextCursor':None}})
        runner.sync=Sync(PollSummary('auth',next_work=True))
        result=runner.run();self.assertEqual(result['discovery_status'],'auth')
        self.assertEqual(result['awaiting_review'],1);self.assertEqual(len(calls),1)
        self.assertEqual(result['status'],'partial')

    def test_unknown_result_and_exceptions_cannot_leak_financial_text(self):
        for failure in [RuntimeError('PRIVATE PDF INVOICE'),MailError('unavailable')]:
            runner,repo,calls=self.make({None:{'items':[job(10)],'nextCursor':None}})
            def process(*args):raise failure
            runner.process=process
            result=runner.run();self.assertNotIn('PRIVATE',json.dumps(result))
            self.assertEqual(result['reason'],'unavailable');self.assertEqual(result['status'],'partial')
        runner,repo,calls=self.make(result={'status':'PRIVATE PDF'})
        runner.sync.poll=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('PRIVATE TOKEN'))
        self.assertNotIn('PRIVATE',json.dumps(runner.run()))

    def test_main_redacts_unexpected_errors(self):
        api=self.api()
        with patch.object(api,'load_context',side_effect=RuntimeError('PRIVATE TOKEN')),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(api.main(),1)
        self.assertEqual(json.loads(output.getvalue()),{'status':'error','reason':'unavailable'})
