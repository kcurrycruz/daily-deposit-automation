from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from fixtures.ap_mail.sources import ReadStore,I
from app.ap_mail.contracts import Claim,MailError

DOC=dict(id='00000000-0000-4000-8000-000000000010',vendor='Synthetic & Co.',filename='synthetic.pdf',
         layout='generic',confirmed=False,pageCount=1,statementDate='2026-11-04',warnings=[],rows=[dict(
         id='00000000-0000-4000-8000-000000000011',type='invoice',invoiceNumber='RECENT',amount=13800,
         date='2026-10-01',page=1,confidence=99)])
CLAIM=Claim('00000000-0000-4000-8000-000000000012','00000000-0000-4000-8000-000000000013',1,1,1,1,'2026-11-04T12:10:00Z','extract')


class MailSourceTests(unittest.TestCase):
    def test_source_metadata_wrong_workspace_is_denied(self):
        from app.ap_mail.sources import SourceReadRepository
        class Mail:
            config=type('Config',(),{'workspace_id':'00000000-0000-4000-8000-000000000001'})()
            storage=type('Storage',(),{'config':config})()
            def _read(self,action,payload):return {'home':{'id':'00000000-0000-4000-8000-000000000099'}}
        with self.assertRaises(MailError) as error:SourceReadRepository(Mail()).read_context()
        self.assertEqual(error.exception.code,'denied')

    def make(self):
        from app.ap_shared.bills.reads import BillReadAPI,ReadCaches
        from app.ap_mail.sources import MailSources,DomainAdapter
        repo=ReadStore();self.addCleanup(repo.close);caches=ReadCaches(repo);self.addCleanup(caches.close)
        reads=BillReadAPI(repo,lambda:True,caches)
        sources=MailSources(reads,DomainAdapter(),lambda claim:True,lambda:datetime(2026,11,4,12,tzinfo=timezone.utc))
        return sources,repo,reads

    def test_preliminary_source_preparation_never_marks_reviewed(self):
        sources,repo,reads=self.make()
        result=sources.prepare(DOC,CLAIM)
        self.assertTrue(result['evidence']['preliminary'])
        self.assertEqual(result['evidence']['rows'][0]['status'],'presence')
        self.assertFalse(DOC['confirmed'])
        self.assertEqual(result['pin'].import_id,I)
        self.assertEqual(result['freshness']['daysOld'],1)
        self.assertFalse(result['freshness']['stale'])

    def test_incomplete_directory_or_source_change_never_becomes_missing(self):
        sources,repo,reads=self.make();original=reads.vendors_page
        def partial(*args,**kwargs):
            page=original(*args,**kwargs);page['total']+=1;return page
        reads.vendors_page=partial
        with self.assertRaises(MailError):sources.prepare(DOC,CLAIM)
        reads.vendors_page=original;candidate=reads.candidates_page
        def changed(*args,**kwargs):
            page=candidate(*args,**kwargs);repo._home['import_version']+=1;return page
        reads.candidates_page=changed
        with self.assertRaises(MailError) as error:sources.prepare(DOC,CLAIM)
        self.assertEqual(error.exception.code,'stale_source')

    def test_waiting_for_bill_and_actual_upload_freshness(self):
        sources,repo,_=self.make();repo.info['created_at']='2026-10-01T12:00:00+00:00';repo.info['metadata']['asOf']='2027-01-01'
        self.assertTrue(sources.prepare(DOC,CLAIM)['freshness']['stale'])
        repo._home['active_import_id']=None;repo.info=None
        result=sources.prepare(DOC,CLAIM)
        self.assertIsNone(result['pin'].import_id)
        self.assertEqual(result['evidence']['rows'][0]['status'],'unverified')

    def test_working_range_exclusion_stays_archived_review(self):
        import copy
        sources,repo,_=self.make();repo.enable_working()
        doc=copy.deepcopy(DOC);doc['rows'][0].update(invoiceNumber='OLD',date='2024-10-01')
        result=sources.prepare(doc,CLAIM)
        self.assertEqual(result['evidence']['rows'][0]['status'],'range')

    def test_read_handler_has_no_write_dispatch(self):
        sources,repo,reads=self.make()
        with self.assertRaises(MailError) as error:sources._page(reads.pin(),CLAIM,'complete_revision',{})
        self.assertEqual(error.exception.code,'denied')

    def test_duplex_child_protocol_calls_only_the_supplied_read_handler(self):
        from app.ap_mail.process import run_json
        with tempfile.TemporaryDirectory() as folder:
            child=Path(folder)/'rpc.py'
            child.write_text("import json,sys\njson.loads(sys.stdin.readline())\n"
                "print(json.dumps({'type':'read','request_id':1,'action':'vendors','payload':{}}),flush=True)\n"
                "reply=json.loads(sys.stdin.readline())\nprint(json.dumps({'type':'result','value':reply['value']}),flush=True)\n",encoding='utf-8')
            def read(action,payload):
                self.assertEqual(action,'vendors');self.assertEqual(payload,{})
                return {'count':7}
            self.assertEqual(run_json([sys.executable,str(child)],{},timeout_seconds=5,heartbeat=lambda:True,on_request=read),{'count':7})
