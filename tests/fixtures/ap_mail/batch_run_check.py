"""Offline batch acceptance: actual PostgreSQL, parser, matcher and fenced publication."""
import base64
from datetime import datetime,timezone
import os
import time
from unittest.mock import patch
import httpx
from app.ap_mail.contracts import MailConfig,MailError
from app.ap_mail.repository import MailRepository
from app.ap_mail.storage import OriginalStore
from fixtures.ap_mail.burst_check import Database,Client
from fixtures.ap_mail.history import Gmail,message,history_event
from workers.ap_mail.batch import BatchRunner
from workers.ap_mail.github import REPOSITORY,grant_reference
from workers.ap_mail.shared import build_processor


def run_batch_check():
    db=Database();caches=None;objects={};downloads=[0];extractions=[0]
    try:
        db.call({'test':'batch_config','reference':grant_reference(REPOSITORY)})
        w,c=db.ready['workspace_id'],db.ready['connection_id']
        repo=MailRepository(MailConfig('https://synthetic.supabase.co','SYNTHETIC',w,'hwfc-ap-private',c,'processor'),Client(db))
        pdfs=[base64.b64decode(value) for value in db.ready['pdfs'][:3]]
        messages={f'm{n}':message(f'm{n}') for n in range(3)}
        for n,item in enumerate(messages.values()):
            item['payload']={'mimeType':'application/pdf','filename':'synthetic.pdf','body':{'size':len(pdfs[n]),'attachmentId':'a'+str(n)}}
        gmail=Gmail(messages)
        def attachment(mid,aid):downloads[0]+=1;return pdfs[int(aid[1:])]
        gmail.attachment=attachment
        gmail.events[('999',None)]={'historyId':'1001','history':[history_event(mid) for mid in messages]}
        processor,caches=build_processor(repo,lambda:gmail)
        extract=processor.extract;prepare=processor.sources.prepare;fail_extract=[True];fail_compare=[True]
        def interrupted_extract(*args,**kwargs):
            if fail_extract[0]:fail_extract[0]=False;raise MailError('unavailable')
            extractions[0]+=1;return extract(*args,**kwargs)
        def interrupted_compare(*args,**kwargs):
            if fail_compare[0]:fail_compare[0]=False;raise MailError('unavailable')
            return prepare(*args,**kwargs)
        processor.extract=interrupted_extract;processor.sources.prepare=interrupted_compare
        def storage(request):
            key=request.url.path.split('/hwfc-ap-private/',1)[1]
            if request.method=='POST':
                if key in objects:return httpx.Response(409)
                objects[key]=request.content;db.call({'test':'object','key':key,'size':len(request.content)})
                return httpx.Response(201)
            return httpx.Response(200,content=objects[key]) if key in objects else httpx.Response(404)
        original=OriginalStore;transport=httpx.MockTransport(storage)
        browser={'AP_MAIL_BROWSER_BINARY':'C:/Program Files/Google/Chrome/Application/chrome.exe'} if os.name=='nt' else {}
        runner=BatchRunner(repo,lambda:gmail,processor.run)
        with patch('app.ap_mail.storage.OriginalStore',side_effect=lambda config:original(config,transport=transport)),patch.dict(os.environ,**browser):
            # Establish real discovery, then simulate another invocation holding the slot.
            runner.sync.poll(c,queue_stale=False)
            first=repo.batch_pending(1)['items'][0]
            assert repo.mutate('claim',{'job_id':first['job_id'],'dispatch_generation':1})['claim']
            held=runner.run();assert held['attempted']==2 and held['not_claimed']==2,held
            db.call({'test':'expire','job_id':first['job_id']})
            for _ in range(5):
                db.call({'test':'advance'});runner.run()
                counts=db.call({'test':'counts'})
                if counts['awaiting_review']==3:break
        counts=db.call({'test':'counts'})
        assert counts['awaiting_review']==3 and counts['receipts']==3 and counts['statements']==4,counts
        assert counts['human_unchanged'] and counts['completion_events']==1 and counts['running']==0,counts
        assert counts['preliminary_found']==6 and counts['max_attempts']<=3,counts
        assert downloads[0]==3 and extractions[0]==3 and len(objects)==3,(downloads,extractions,len(objects))
        assert db.lost_publish==1
        print('Synthetic mail batch passed: 3 originals, 3 preliminary drafts, recovery, overlap, human history unchanged.')
    finally:
        if caches:caches.close()
        db.close()
