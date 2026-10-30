from contextlib import contextmanager
from types import SimpleNamespace
import time
import unittest
from app.ap_shared.bills.working.effective_protections import EffectiveProtections
from app.ap_shared.bills.working.protections import ProtectionSet
from app.ap_shared.bills.working.policy import make_policy
from app.ap_shared.bills.contracts import SnapshotError
from test_ap_bill_working_policy import bill,NOW,I
from test_ap_bill_working_builds import source_db

class EffectiveProtectionTests(unittest.TestCase):
    def fixture(self,rows):
        db=source_db(rows);self.addCleanup(db.close)
        @contextmanager
        def index(*args):yield SimpleNamespace(db=db),{}
        ops=SimpleNamespace(_check=lambda _:None,_index=index)
        source=dict(id=I,file_hash='a'*64,record_count=len(rows),storage_format='snapshot-v2',snapshot_manifest={})
        return db,ops,source
    def derive(self,p,rows,mode='last_12_months'):
        db,ops,source=self.fixture(rows);trace=[];db.set_trace_callback(trace.append)
        result=EffectiveProtections().derive(dict(epoch=2,digest=p.digest(),protections=p),source,make_policy(mode,NOW),ops,None,time.monotonic()+5)
        self.assertTrue(all('where reference_key=' in q.lower() for q in trace if 'from bill_records' in q.lower()))
        return result['protections']
    def test_unknown_vendor_protects_all_matching_old_namespaces_without_amount_filter(self):
        rows=[bill(vendor='One',invoiceNumber='REF',amount=10000),bill(vendor='Two',invoiceNumber='REF',amount=20000),bill(vendor='One',invoiceNumber='REF',invoiceDate='2026-10-01')]
        p=ProtectionSet();p._add(None,'REF','invoice');effective=self.derive(p,rows)
        self.assertTrue(effective.protects(rows[0]));self.assertTrue(effective.protects(rows[1]))
        self.assertEqual(len(effective.keys),2)
    def test_adventure_alias_retains_the_actual_old_reference_with_different_amount(self):
        vendor='Adventure in Food Trading Company';rows=[bill(vendor=vendor,invoiceNumber='00271712X',amount=20000),bill(vendor=vendor,invoiceNumber='00271712',invoiceDate='2026-10-01')]
        p=ProtectionSet();p._add(vendor,'00271712','invoice',adventure=True);effective=self.derive(p,rows)
        self.assertTrue(effective.protects(rows[0]));self.assertFalse(effective.protects(rows[1]));self.assertEqual(len(effective.keys),1)
    def test_all_mode_has_no_exclusion_effect_and_needs_no_source_read(self):
        p=ProtectionSet();p._candidate(bill());effective=self.derive(p,[bill()],mode='all');self.assertEqual(effective.keys,set())
    def test_cold_exact_lookup_yields_instead_of_assuming_no_archived_match(self):
        p=ProtectionSet();p._candidate(bill());db,ops,source=self.fixture([bill()])
        prepared=SimpleNamespace(prepare=lambda *args:False)
        with self.assertRaises(SnapshotError) as error:EffectiveProtections(prepared).derive(dict(epoch=1,digest=p.digest(),protections=p),source,make_policy('last_12_months',NOW),ops,None,time.monotonic()+5)
        self.assertEqual(error.exception.code,'bill_range_loading')
