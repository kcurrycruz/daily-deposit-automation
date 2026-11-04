import copy
import unittest
from fixtures.ap_mail.sources import ReadStore,I,S
from app.ap_mail.contracts import MailError


class BillReadTests(unittest.TestCase):
    def make(self,format='snapshot-v2',working=False):
        from app.ap_shared.bills.reads import BillReadAPI,ReadCaches
        repo=ReadStore(format);self.addCleanup(repo.close)
        if working:repo.enable_working()
        checks=[]
        caches=ReadCaches(repo);self.addCleanup(caches.close)
        api=BillReadAPI(repo,lambda:checks.append('checked'),caches)
        return api,repo,checks

    def query(self,pin,reference='RECENT'):
        return dict(importId=pin.import_id,**({'workingSetId':pin.working_set_id} if pin.working_set_id else {}),
                    references=[{'invoiceKey':reference,'kind':'invoice'}],amounts=[])

    def test_rows_snapshot_working_parity(self):
        for format,working in [('rows-v1',False),('snapshot-v2',False),('snapshot-v2',True)]:
            with self.subTest(format=format,working=working):
                api,repo,checks=self.make(format,working);pin=api.pin()
                page=api.candidates_page(pin,self.query(pin),None)
                self.assertEqual([(r['id'],r['invoiceNumber'],r['amount']) for r in page['records']],[(I+':1','RECENT',13800)])
                self.assertEqual(api.vendors_page(pin,None)['vendors'],[{'vendor':'Synthetic & Co.'}])
                self.assertGreater(len(checks),3)
                self.assertFalse(hasattr(api,'handle'))
                self.assertFalse(hasattr(api,'complete_revision'))
                if working:
                    archived=api.archived_references_page(pin,[{'invoiceKey':'OLD','kind':'invoice'}],None)
                    self.assertEqual(archived['archivedIds'],[I+':0'])

    def test_stale_source_mapping_versions_and_auth(self):
        api,repo,_=self.make(working=True);pin=api.pin()
        for field in ['import_version','working_set_version','bill_protection_epoch']:
            repo._home[field]+=1
            with self.subTest(field=field),self.assertRaises(MailError):api.assert_current(pin)
            repo._home[field]-=1
        repo.mappings={'Alias':'Synthetic & Co.'};repo.versions={'Alias':1}
        with self.assertRaises(MailError):api.assert_current(pin)
        def deny():raise PermissionError('locked')
        api.authorize=deny
        with self.assertRaises(PermissionError):api.candidates_page(pin,self.query(pin),None)

    def test_incomplete_legacy_and_corrupt_archive_cannot_return_missing(self):
        api,repo,_=self.make('rows-v1');pin=api.pin();repo.gap=True
        with self.assertRaises(MailError):api.candidates_page(pin,self.query(pin),None)
        api,repo,_=self.make();pin=api.pin()
        repo.files[repo.info['snapshot_manifest']['indexArchive']['key']].write_bytes(b'corrupt gzip')
        with self.assertRaises(MailError):api.candidates_page(pin,self.query(pin),None)

    def test_source_cache_reuse_and_bounded_eviction(self):
        api,repo,_=self.make();pin=api.pin()
        api.candidates_page(pin,self.query(pin),None);reads=repo.reads
        api.candidates_page(pin,self.query(pin),None)
        self.assertEqual(repo.reads,reads)
        repo._home['active_import_id']=S;repo.info['id']=S
        changed=api.pin();api.candidates_page(changed,self.query(changed),None)
        self.assertEqual(len(api.caches.snapshot.entries),1)
        self.assertEqual(repo.reads,reads+1)

    def test_source_manifest_cannot_claim_another_original(self):
        for working in [False,True]:
            api,repo,_=self.make(working=working)
            repo.info['file_hash']='f'*64
            with self.assertRaises(MailError):
                pin=api.pin();api.candidates_page(pin,self.query(pin),None)
