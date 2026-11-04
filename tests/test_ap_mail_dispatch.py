import copy
import json
import unittest
from app.ap_mail.contracts import MailError
from fixtures.ap_mail.store_double import W,C

JOB='00000000-0000-4000-8000-000000000003'


class Store:
    config=type('Config',(),{'workspace_id':W})()
    def __init__(self):
        self.home=dict(id=C,active=True,paused=False,generation=1,dispatch_cursor=None)
        self.row=dict(workspace_id=W,job_id=JOB,dispatch_generation=1,state='pending',task_name=None)
        self.events=[];self.active_lease=False
    def connection(self):return dict(self.home)
    def outbox_page(self,cursor=None,limit=100,*,state='pending'):
        return {'items':[dict(self.row)] if cursor is None and self.row['state']==state else [],'nextCursor':None}
    def mutate(self,operation,payload,request_id=None):
        self.events.append((operation,copy.deepcopy(payload)))
        if operation=='outbox_sent':self.row.update(state='sent',task_name=payload['task_name'])
        elif operation=='dispatch_missing':
            if not self.active_lease:
                self.row.update(state='pending',task_name=None,dispatch_generation=self.row['dispatch_generation']+1)
                return {'requeued':True}
            return {'requeued':False}
        elif operation=='dispatch_checkpoint':self.home['dispatch_cursor']=payload['cursor']
        return {'saved':True}


class Tasks:
    def __init__(self):self.tasks={};self.creates=[];self.mode=None
    def create_task(self,request):
        self.creates.append(copy.deepcopy(request))
        task=request['task'];name=task['name']
        if name in self.tasks:raise MailError('conflict')
        if self.mode=='before':raise MailError('unavailable')
        if self.mode=='quota':raise MailError('quota')
        self.tasks[name]=copy.deepcopy(task)
        if self.mode=='after':raise MailError('unavailable')
        return {'name':name}
    def get_task(self,request):
        if request['name'] not in self.tasks:raise MailError('not_found')
        return dict(self.tasks[request['name']])


class DispatchTests(unittest.TestCase):
    def make(self):
        from app.ap_mail.dispatch import TaskDispatcher,DispatchConfig
        store,tasks=Store(),Tasks()
        cfg=DispatchConfig('projects/synthetic-test/locations/us-east1/queues/ap-mail',
            'https://ap-worker-synthetic.us-east1.run.app/process',
            'ap-task@synthetic-test.iam.gserviceaccount.com','https://ap-worker-synthetic.us-east1.run.app')
        return TaskDispatcher(store,tasks,cfg),store,tasks

    def test_enqueue_ack_lost(self):
        runner,store,tasks=self.make();tasks.mode='after'
        result=runner.drain();self.assertEqual(result.failed,1);self.assertEqual(store.row['state'],'pending')
        tasks.mode=None;runner.drain()
        self.assertEqual(len(tasks.tasks),1);self.assertEqual(store.row['state'],'sent')
        self.assertEqual(tasks.creates[0]['task']['name'],tasks.creates[1]['task']['name'])

    def test_outbox_commit_precedes_task_and_payload_has_no_document(self):
        runner,store,tasks=self.make();runner.drain()
        task=tasks.creates[0]['task'];http=task['http_request']
        self.assertEqual(json.loads(http['body']),{'job_id':JOB,'dispatch_generation':1})
        self.assertEqual(http['oidc_token']['audience'],'https://ap-worker-synthetic.us-east1.run.app')
        self.assertEqual(task['dispatch_deadline']['seconds'],600)
        self.assertEqual(store.events[-1][0],'outbox_sent')
        store.row['workspace_id']=C;store.row['state']='pending'
        with self.assertRaises(MailError):runner.drain()

    def test_task_missing_lease_expired_repair(self):
        runner,store,tasks=self.make();runner.drain();first=store.row['task_name']
        tasks.tasks.clear();runner.reconcile();self.assertEqual(store.row['dispatch_generation'],2)
        runner.drain();self.assertNotEqual(store.row['task_name'],first)
        self.assertEqual(len(tasks.tasks),1)

    def test_active_lease_not_replaced(self):
        runner,store,tasks=self.make();runner.drain();tasks.tasks.clear();store.active_lease=True
        runner.reconcile();self.assertEqual(store.row['dispatch_generation'],1)

    def test_backoff_and_pause(self):
        for mode in ['before','quota']:
            runner,store,tasks=self.make();tasks.mode=mode;runner.drain()
            event=next(e for e in store.events if e[0]=='outbox_delay')
            self.assertGreaterEqual(event[1]['delay_seconds'],30);self.assertLessEqual(event[1]['delay_seconds'],3600)
            self.assertEqual(store.row['state'],'pending')
        runner,store,tasks=self.make();store.home['paused']=True
        self.assertEqual(runner.drain().sent,0);self.assertEqual(tasks.tasks,{})

    def test_dispatch_targets_cannot_be_redirected(self):
        from app.ap_mail.dispatch import DispatchConfig
        with self.assertRaises(MailError):DispatchConfig('projects/test/locations/us-east1/queues/q','https://evil.test/process','test@example.test','https://evil.test')

    def test_reconciliation_advances_beyond_first_page(self):
        runner,store,tasks=self.make()
        first={**store.row,'state':'sent'};first['task_name']=runner._name(first)
        late={**first,'job_id':'00000000-0000-4000-8000-000000000004'};late['task_name']=runner._name(late)
        tasks.tasks[first['task_name']]={'name':first['task_name']}
        store.row=late
        def pages(cursor=None,limit=100,*,state='pending'):
            if cursor is None:return {'items':[first],'nextCursor':{'job_id':first['job_id'],'dispatch_generation':1}}
            return {'items':[dict(late)],'nextCursor':None}
        store.outbox_page=pages
        runner.reconcile(limit=1);runner.reconcile(limit=1)
        self.assertEqual(store.row['dispatch_generation'],2)

