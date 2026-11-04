"""100 real PDF reads, real domain matcher and real SQL behind synthetic cloud boundaries."""
import base64
import copy
from datetime import datetime,timezone
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import threading
import time
from unittest.mock import patch
import httpx
from app.ap_mail.contracts import MailConfig,MailError
from app.ap_mail.repository import MailRepository
from app.ap_mail.processor import MailProcessor
from app.ap_mail.publication import MailPublication
from app.ap_mail.extraction import extract_private_pdf
from app.ap_mail.sources import MailSources,SourceReadRepository,DomainAdapter
from app.ap_mail.storage import OriginalStore
from app.ap_mail.sync import MailSync
from app.ap_shared.bills.reads import BillReadAPI,ReadCaches
from test_ap_mail_dispatch import Tasks
from fixtures.ap_mail.history import Gmail,message,history_event

ROOT=Path(__file__).resolve().parents[3]

class Database:
    def __init__(self):
        self.child=subprocess.Popen([shutil.which('node'),str(ROOT/'tests/fixtures/ap_mail/burst_sql.mjs')],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        self.ready=json.loads(self.child.stdout.readline());self.lock=threading.Lock();self.lost_publish=0;self.fail_publish=True
    def call(self,request):
        with self.lock:
            self.child.stdin.write(json.dumps(request,separators=(',',':'))+'\n');self.child.stdin.flush()
            value=json.loads(self.child.stdout.readline())
            if 'error' in value:raise MailError(value['error'])
            if request.get('name')=='ap_mail_publish' and self.fail_publish:
                self.fail_publish=False;self.lost_publish+=1;raise MailError('unavailable')
            return value['value']
    def close(self):
        self.child.stdin.close()
        try:self.child.wait(timeout=15)
        except subprocess.TimeoutExpired:self.child.kill();self.child.wait()
        self.child.stdout.close()

class Client:
    def __init__(self,db):
        self.db=db;self.storage=type('Storage',(),{'get_bucket':lambda self,bucket:{'public':False}})()
    def rpc(self,name,args):
        database=self.db
        class Reply:
            def execute(self):return type('Data',(),{'data':database.call({'name':name,'args':args})})()
        return Reply()
    def table(self,name):
        db=self.db
        class Query:
            def __init__(self):self.filters=[];self.limit_value=500
            def select(self,*args,**kwargs):return self
            def eq(self,key,value):self.filters.append([key,'=',value]);return self
            def gt(self,key,value):self.filters.append([key,'>',value]);return self
            def order(self,*args,**kwargs):return self
            def limit(self,value):self.limit_value=value;return self
            def execute(self):return type('Data',(),{'data':db.call({'test':'table','table':name,'filters':self.filters,'limit':self.limit_value})})()
        return Query()

def run_burst():
    from app.ap_mail.dispatch import TaskDispatcher,DispatchConfig
    database=Database();caches=None;start=time.perf_counter();parse_times=[];ocr_calls=0;objects={};storage_lost_ack=[True]
    try:
        w,c=database.ready['workspace_id'],database.ready['connection_id'];config=MailConfig('https://synthetic.supabase.co','SYNTHETIC-KEY',w,'hwfc-ap-private',c,'processor')
        repo=MailRepository(config,Client(database));pdfs=[base64.b64decode(raw) for raw in database.ready['pdfs']]
        idle=[]
        for _ in range(10):
            t=time.perf_counter();repo.status();idle.append(time.perf_counter()-t)
        messages={f'm{n}':message(f'm{n}') for n in range(100)}
        for n,msg in enumerate(messages.values()):
            msg['payload']={'mimeType':'application/pdf','filename':'statement.pdf','body':{'size':len(pdfs[n]),'attachmentId':'a'+str(n)}}
        gmail=Gmail(messages);gmail.downloads=0
        def attachment(mid,aid):gmail.downloads+=1;return pdfs[int(aid[1:])]
        gmail.attachment=attachment
        gmail.events[('999',None)]={'historyId':'1001','history':[history_event(key) for key in [*messages,*list(messages)[:10]]]}
        result=MailSync(gmail,repo,lambda:datetime(2026,11,4,12,10,tzinfo=timezone.utc),time.monotonic).poll(c)
        assert result.status=='ok',result.status
        # Replaying discovery does not make additional receipts/jobs.
        gmail.events[('1001',None)]={'historyId':'1002','history':[history_event(key) for key in list(messages)[:10]]}
        MailSync(gmail,repo,lambda:datetime(2026,11,4,12,10,tzinfo=timezone.utc),time.monotonic).poll(c)
        tasks=Tasks();dispatch=TaskDispatcher(repo,tasks,DispatchConfig('projects/synthetic-test/locations/us-east1/queues/ap-mail',
            'https://processor.run.app/process','ap-task@synthetic-test.iam.gserviceaccount.com','https://processor.run.app'))
        tasks.mode='after';dispatch.drain();tasks.mode=None;database.call({'test':'advance'});dispatch.drain()
        receipts=repo.receipts_page({},None,50)['items'];a,b=receipts[:2]
        claim=repo.mutate('claim',{'job_id':a['id'],'dispatch_generation':1})['claim'];assert claim
        assert repo.mutate('claim',{'job_id':b['id'],'dispatch_generation':1})['claim'] is None
        database.call({'test':'expire','job_id':a['id']});recovered=dispatch.reconcile().recovered
        source_repo=SourceReadRepository(repo);caches=ReadCaches(source_repo)
        parse_fail=[True];compare_fail=[True]
        def extract(path,name,**kwargs):
            nonlocal ocr_calls
            if parse_fail[0]:parse_fail[0]=False;raise MailError('unavailable') # original already copied
            before=time.perf_counter();doc=extract_private_pdf(path,name,**kwargs);parse_times.append(time.perf_counter()-before);ocr_calls+=1;return doc
        processor=MailProcessor(repo,gmail,extract,None,None,time.monotonic)
        reads=BillReadAPI(source_repo,lambda:processor.authorize(processor.lease.claim),caches,preliminary=True)
        sources=MailSources(reads,DomainAdapter(),processor.authorize,lambda:datetime.now(timezone.utc));prepare=sources.prepare
        def prepare_once(doc,claim):
            if compare_fail[0]:compare_fail[0]=False;raise MailError('unavailable') # saved extraction exists
            return prepare(doc,claim)
        sources.prepare=prepare_once;processor.sources=sources;processor.publication=MailPublication(repo,DomainAdapter(),processor.authorize)
        def storage(req):
            key=req.url.path.split('/hwfc-ap-private/',1)[1]
            if req.method=='POST':
                if key in objects:return httpx.Response(409)
                objects[key]=req.content;database.call({'test':'object','key':key,'size':len(req.content)})
                if storage_lost_ack[0]:storage_lost_ack[0]=False;raise httpx.ReadTimeout('synthetic lost acknowledgement')
                return httpx.Response(201)
            return httpx.Response(200,content=objects[key]) if key in objects else httpx.Response(404)
        original_class=OriginalStore;transport=httpx.MockTransport(storage);busy_latencies=[]
        browser_env={'AP_MAIL_BROWSER_BINARY':'C:/Program Files/Google/Chrome/Application/chrome.exe'} if os.name=='nt' else {}
        with patch('app.ap_mail.storage.OriginalStore',side_effect=lambda cfg:original_class(cfg,transport=transport)),patch.dict(os.environ,**browser_env):
            for cycle in range(6):
                database.call({'test':'advance'});recovered+=dispatch.reconcile().recovered;dispatch.drain()
                for name,task in list(tasks.tasks.items()):
                    tasks.tasks.pop(name,None);payload=json.loads(task['http_request']['body']);processor.run(**payload)
                    t=time.perf_counter();repo.status();busy_latencies.append(time.perf_counter()-t)
                counts=database.call({'test':'counts'})
                if counts['awaiting_review']==100:break
            assert counts['awaiting_review']==100,counts
            attempts=counts['max_attempts']
            # Source refresh is paginated at 50 and reuses all 100 saved extractions.
            for _ in range(3):
                queued=repo.queue_stale(50)['queued']
                if not queued:break
                dispatch.drain()
                for name,task in list(tasks.tasks.items()):
                    tasks.tasks.pop(name,None);processor.run(**json.loads(task['http_request']['body']))
        counts=database.call({'test':'counts'});counts['max_attempts']=max(attempts,counts['max_attempts'])
        report={**counts,'ocr_calls':ocr_calls,'objects':len(objects),'downloads':gmail.downloads,'lost_publish_ack':database.lost_publish,'recovered':recovered,
            'wall_seconds':round(time.perf_counter()-start,3),'cold_read_seconds':round(parse_times[0],3),'warm_read_median_seconds':round(statistics.median(parse_times[1:]),3),
            'idle_sql_rpc_median_ms':round(statistics.median(idle)*1000,3),'burst_sql_rpc_median_ms':round(statistics.median(busy_latencies)*1000,3),
            'scope':'Local digital fixtures and embedded SQL only; excludes cloud latency and total browser-tree memory.'}
        print('SYNTHETIC_MAIL_BURST '+json.dumps(report,sort_keys=True),flush=True)
        return report
    finally:
        if caches:caches.close()
        database.close()
