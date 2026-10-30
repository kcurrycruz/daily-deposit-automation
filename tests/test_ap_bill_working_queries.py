import unittest
from uuid import uuid4
import test_ap_bill_working_operations as operation_fixtures
from test_ap_bill_working_policy import I

try:
    from app.ap_shared.bills.working.queries import WorkingQueries
except ImportError:
    WorkingQueries=None


class WorkingQueryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(WorkingQueries,'Scoped statement queries are not implemented')
        self.f=operation_fixtures.WorkingOperationsTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        job=self.f.begin();self.f.prepare(job);result=self.f.activate(job)
        self.manifest=result['workingSet'];self.ident=self.manifest['workingSetId']
        self.queries=WorkingQueries(self.f.ops)

    def query(self,**changes):
        return dict(importId=I,workingSetId=self.ident,references=[],
                    amounts=[dict(vendorKey='synthetic vendor',kind='invoice',amount=10000)],**changes)

    def test_only_active_records_return_with_original_ids_and_original_ordinals(self):
        page=self.queries.candidates_page(self.ident,self.query(),None,self.f.auth)
        self.assertEqual(page['total'],1)
        self.assertEqual(page['records'][0]['id'],f'{I}:1')
        self.assertEqual(page['afterOrdinal'],-1)
        self.assertEqual(page['workingSetId'],self.ident)
        self.assertIsNone(page['nextCursor'])
        vendors=self.queries.vendors_page(self.ident,None,self.f.auth)
        self.assertEqual(vendors['total'],1)
        self.assertEqual(vendors['vendorDigest'],self.manifest['vendorDigest'])

    def test_archive_lookup_is_explicit_exact_reference_and_labels_archived_members(self):
        page=self.queries.archived_references_page(I,[dict(invoiceKey='OLD',kind='invoice')],None,self.f.auth)
        self.assertEqual(page['total'],1)
        self.assertEqual(page['records'][0]['id'],f'{I}:0')
        self.assertEqual(page['archivedIds'],[f'{I}:0'])
        with self.assertRaises(ValueError):
            self.queries.archived_references_page(I,[dict(vendorKey='synthetic vendor',kind='invoice',amount=10000)],None,self.f.auth)

    def test_stale_scope_or_protection_epoch_never_returns_misleading_absence(self):
        self.f.repo._home['bill_protection_epoch']+=1
        with self.assertRaises(ValueError):self.queries.candidates_page(self.ident,self.query(),None,self.f.auth)
        self.f.repo._home['bill_protection_epoch']-=1
        self.f.repo._home['active_working_set_id']=None
        with self.assertRaises(ValueError):self.queries.vendors_page(self.ident,None,self.f.auth)

    def test_gateway_routes_scoped_reads_and_rejects_cursor_from_other_query(self):
        self.f.service.working_operations=self.f.ops
        page=self.f.service.handle('bill_candidates_page',{'query':self.query()},str(uuid4()),self.f.auth)
        self.assertEqual(page['total'],1)
        from app.ap_shared.bills.contracts import encode_cursor,canonical_hash
        cursor=encode_cursor(I,canonical_hash({'wrong':'scope'}),0)
        with self.assertRaises(ValueError):self.queries.candidates_page(self.ident,self.query(),cursor,self.f.auth)


if __name__=='__main__':unittest.main()
