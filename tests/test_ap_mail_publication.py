import copy
from dataclasses import replace
import shutil
import subprocess
from pathlib import Path
import unittest
from app.ap_mail.contracts import MailError,SourcePin,payload_digest
from app.ap_mail.sources import DomainAdapter
from test_ap_mail_sources import DOC,CLAIM


class PublicationStore:
    def __init__(self):self.items=[];self.epoch=3;self.saved=None;self.partial=False
    def candidates_page(self,cursor=None,limit=50):
        return dict(items=copy.deepcopy(self.items),epoch=self.epoch,mappings={},mappingVersions={},nextCursor='again' if self.partial else None)
    def publish(self,payload,request_id=None):self.saved=payload;return {'status':'awaiting_review'}
    def byte_match(self,receipt_id):return None


class MailPublicationTests(unittest.TestCase):
    def test_unrelated_large_history_is_streamed_and_same_vendor_pages_are_complete(self):
        pub,store,pin,doc=self.setup_publication()
        items=[dict(id=str(__import__('uuid').uuid4()),version=1,revision_id=CLAIM.job_id,doc={**copy.deepcopy(doc),'vendor':'Other '+str(n),'notes':'x'*12000}) for n in range(100)]
        match=dict(id=DOC['id'],version=2,revision_id=CLAIM.job_id,doc=copy.deepcopy(doc));items.append(match)
        def page(cursor=None,limit=50):
            at=int(cursor or 0);return dict(items=items[at:at+50],epoch=3,mappings={},mappingVersions={},nextCursor=str(at+50) if at+50<len(items) else None)
        store.candidates_page=page
        self.assertEqual(pub.assess(doc,CLAIM,pin)['kind'],'duplicate')

    def test_same_vendor_history_without_shared_references_does_not_exhaust_inventory(self):
        pub,store,pin,doc=self.setup_publication()
        items=[]
        for n in range(100):
            prior=copy.deepcopy(doc);prior['rows'][0]['invoiceNumber']='OTHER-'+str(n);prior['notes']='x'*12000
            items.append(dict(id=str(__import__('uuid').uuid4()),version=1,revision_id=CLAIM.job_id,doc=prior))
        items.append(dict(id=DOC['id'],version=2,revision_id=CLAIM.job_id,doc=copy.deepcopy(doc)))
        store.candidates_page=lambda cursor=None,limit=50:dict(items=items[int(cursor or 0):int(cursor or 0)+50],epoch=3,mappings={},mappingVersions={},nextCursor=str(int(cursor or 0)+50) if int(cursor or 0)+50<len(items) else None)
        self.assertEqual(pub.assess(doc,CLAIM,pin)['kind'],'duplicate')

    def test_byte_duplicate_does_not_depend_on_semantic_inventory_size(self):
        pub,store,pin,doc=self.setup_publication();proof=dict(id=DOC['id'],version=2,revision_id=CLAIM.job_id)
        store.byte_match=lambda receipt:proof
        store.candidates_page=lambda *args:(_ for _ in ()).throw(AssertionError('No semantic inventory needed'))
        result=pub.assess(doc,CLAIM,pin);self.assertEqual(result['kind'],'duplicate');self.assertEqual(result['match'],proof)
    def setup_publication(self):
        from app.ap_mail.publication import MailPublication
        store=PublicationStore();publication=MailPublication(store,DomainAdapter())
        pin=SourcePin(None,0,None,None,0,3,None,payload_digest({'mappings':{},'versions':{}}),{},'ap-match-v4')
        doc=copy.deepcopy(DOC);doc['declaredTotal']=13800
        return publication,store,pin,doc

    def test_semantic_duplicate_and_overlap(self):
        pub,store,pin,doc=self.setup_publication()
        store.items=[dict(id=DOC['id'],version=2,revision_id=CLAIM.job_id,doc=copy.deepcopy(doc),completed=True,archived=True)]
        result=pub.assess(doc,CLAIM,pin)
        self.assertEqual(result['kind'],'duplicate');self.assertEqual(result['match']['version'],2)
        doc['rows'].append({**doc['rows'][0],'id':CLAIM.receipt_id,'invoiceNumber':'NEW','amount':100})
        doc['declaredTotal']+=100
        result=pub.assess(doc,CLAIM,pin)
        self.assertEqual((result['kind'],result['repeated'],result['added']),('overlap',1,1))
        pub.publish(doc,result,{'preliminary':True,'rows':[]},CLAIM,pin)
        self.assertEqual(len(store.saved['doc']['rows']),2)
        self.assertFalse(store.saved['doc']['confirmed'])

    def test_similarity_requires_human_choice(self):
        pub,store,pin,doc=self.setup_publication()
        prior=copy.deepcopy(doc);prior['statementDate']='2026-10-01'
        store.items=[dict(id=DOC['id'],version=2,revision_id=CLAIM.job_id,doc=prior)]
        self.assertEqual(pub.assess(doc,CLAIM,pin)['kind'],'similar')

    def test_partial_inventory_or_changed_epoch_never_publishes_as_new(self):
        pub,store,pin,doc=self.setup_publication();store.epoch+=1
        with self.assertRaises(MailError):pub.assess(doc,CLAIM,pin)
        store.epoch=3;store.partial=True
        with self.assertRaises(MailError):pub.assess(doc,CLAIM,pin)
        self.assertIsNone(store.saved)

    def test_atomic_publication_sql(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([shutil.which('node'),str(root/'tests/fixtures/ap_mail/publication_checks.mjs')],cwd=root,
            capture_output=True,text=True,encoding='utf-8',timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Mail publication checks passed',result.stdout)
