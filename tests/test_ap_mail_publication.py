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


class MailPublicationTests(unittest.TestCase):
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
