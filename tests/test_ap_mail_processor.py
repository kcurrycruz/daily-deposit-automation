import copy
from dataclasses import asdict
import hashlib
from pathlib import Path
import unittest
from app.ap_mail.contracts import MailError,payload_digest
from test_ap_mail_sources import CLAIM,DOC

PDF=b'%PDF-synthetic'

class Store:
    def __init__(self):
        self.events=[];self.claim=asdict(CLAIM);self.lost=False;self.error=None;self.published=0
        self.row=dict(id=CLAIM.receipt_id,message_id='msg',part_path='0',filename='synthetic.pdf',declared_size=len(PDF),extraction=None)
    def mutate(self,op,data,request_id=None):
        self.events.append(op)
        if op=='claim':return {'claim':self.claim}
        if op=='heartbeat' and self.lost:raise MailError('stale_claim')
        if op=='save_extraction':self.row['extraction']=data['doc']
        return {'saved':True}
    def receipt(self,rid):return copy.deepcopy(self.row)
    def reserve_original(self,claim,size):self.events.append('reserve_original')
    def original_bytes(self,receipt):return PDF
    def copy_original(self,claim,raw):
        self.events.append('copy_original')
        if self.error:raise MailError(self.error)
        self.row.update(sha256=hashlib.sha256(raw).hexdigest());return self.row['sha256']

class Gmail:
    label_id='Label_1'
    def __init__(self):self.downloads=0;self.error=None
    def profile(self):
        if self.error:raise MailError(self.error)
    def message(self,ident):return {'labelIds':['Label_1'],'payload':{'mimeType':'application/pdf','filename':'synthetic.pdf','body':{'size':len(PDF),'attachmentId':'att'}}}
    def attachment(self,*args):self.downloads+=1;return PDF

class Sources:
    def __init__(self):self.calls=0;self.error=None
    def prepare(self,doc,claim):
        self.calls+=1
        if self.error:raise MailError(self.error)
        return dict(evidence={'preliminary':True,'rows':[]},pin=None)
    def assert_current(self,*args):pass

class Publication:
    def __init__(self):self.doc=None
    def assess(self,*args):return {'kind':'new'}
    def publish(self,doc,*args):self.doc=doc;return {'status':'awaiting_review'}

class ProcessorTests(unittest.TestCase):
    def make(self):
        from app.ap_mail.processor import MailProcessor
        repo=Store();gmail=Gmail();sources=Sources();pub=Publication();extractions=[]
        def extract(path,name,**kwargs):
            self.assertEqual(Path(path).read_bytes(),PDF);self.assertTrue(kwargs['heartbeat']())
            extractions.append(name);return copy.deepcopy(DOC)
        p=MailProcessor(repo,gmail,extract,sources,pub,lambda:0)
        return p,repo,gmail,sources,pub,extractions

    def test_full_pipeline_and_waiting_bill(self):
        p,r,g,s,pub,e=self.make();result=p.run(CLAIM.job_id,1)
        self.assertEqual(result['status'],'awaiting_review');self.assertEqual(len(e),1)
        self.assertLess(r.events.index('claim'),r.events.index('copy_original'))
        self.assertLess(r.events.index('reserve_original'),r.events.index('copy_original'))
        self.assertLess(r.events.index('save_extraction'),r.events.index('finish') if 'finish' in r.events else len(r.events))
        self.assertFalse(pub.doc['confirmed']);self.assertEqual(pub.doc,r.row['extraction'])
        r.claim=None;self.assertEqual(p.run(CLAIM.job_id,1)['status'],'not_claimed');self.assertEqual(g.downloads,1)

    def test_source_update_recompare_no_ocr(self):
        p,r,g,s,pub,e=self.make();r.row.update(extraction=copy.deepcopy(DOC),sha256='a'*64);r.claim['mode']='recompare'
        self.assertEqual(p.run(CLAIM.job_id,1)['status'],'awaiting_review')
        self.assertEqual((len(e),g.downloads),(0,0));self.assertNotIn('copy_original',r.events)

    def test_retry_cap_classification(self):
        for code,expected in [('storage','needs_attention'),('unreadable','needs_attention'),('unavailable','release_retry'),('stale_source','release_retry'),('wrong_account','needs_attention')]:
            p,r,g,s,pub,e=self.make();s.error=code
            result=p.run(CLAIM.job_id,1)
            self.assertIn(expected,r.events);self.assertIsNone(pub.doc);self.assertEqual(result['code'],code)

    def test_pause_and_connection_change(self):
        p,r,g,s,pub,e=self.make();r.claim=None
        self.assertEqual(p.run(CLAIM.job_id,1)['status'],'not_claimed');self.assertEqual(g.downloads,0)
        p,r,g,s,pub,e=self.make();g.error='wrong_account'
        self.assertEqual(p.run(CLAIM.job_id,1)['code'],'wrong_account');self.assertIsNone(pub.doc)

    def test_heartbeat_loss_never_publishes(self):
        p,r,g,s,pub,e=self.make();r.lost=True
        self.assertEqual(p.run(CLAIM.job_id,1)['code'],'stale_claim');self.assertEqual(g.downloads,0);self.assertIsNone(pub.doc)

    def test_private_copy_budget_and_changed_part(self):
        p,r,g,s,pub,e=self.make();r.error='storage'
        self.assertEqual(p.run(CLAIM.job_id,1)['code'],'storage');self.assertEqual(e,[])
        p,r,g,s,pub,e=self.make();r.row['declared_size']+=1
        self.assertEqual(p.run(CLAIM.job_id,1)['code'],'withdrawn');self.assertEqual(g.downloads,0)

    def test_stale_source_retry_reuses_persisted_extraction(self):
        p,r,g,s,pub,e=self.make();s.error='stale_source'
        p.run(CLAIM.job_id,1);self.assertIsNotNone(r.row['extraction']);self.assertEqual(len(e),1)
        s.error=None
        p.run(CLAIM.job_id,1);self.assertEqual(len(e),1);self.assertEqual(g.downloads,1)

    def test_saved_original_survives_message_withdrawal_before_extraction(self):
        p,r,g,s,pub,e=self.make();r.row['sha256']=hashlib.sha256(PDF).hexdigest();g.error='wrong_account'
        self.assertEqual(p.run(CLAIM.job_id,1)['status'],'awaiting_review');self.assertEqual(g.downloads,0)

    def test_other_invalid_mime_part_does_not_block_a_verified_receipt(self):
        p,r,g,s,pub,e=self.make();message=g.message('msg');valid=message['payload']
        message['payload']={'mimeType':'multipart/mixed','parts':[valid,{'mimeType':'application/pdf','filename':'bad.pdf','body':{'size':0}}]}
        g.message=lambda ident:message;r.row['part_path']='0.0'
        self.assertEqual(p.run(CLAIM.job_id,1)['status'],'awaiting_review')

    def test_deadline_and_generation_takeover_stop_old_worker(self):
        from app.ap_mail.processor import LeaseGuard
        now=[0];guard=LeaseGuard(Store(),CLAIM,lambda:now[0]);self.assertTrue(guard.check())
        now[0]=591
        with self.assertRaises(MailError):guard.check()
        now[0]=0;guard.failure='stale_claim'
        with self.assertRaises(MailError):guard.check()
