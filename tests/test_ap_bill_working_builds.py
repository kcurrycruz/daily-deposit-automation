import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from datetime import datetime, timezone
from test_ap_bill_working_policy import bill, I, S, W
from app.ap_shared.bills.working.policy import make_policy
from app.ap_shared.bills.working.protections import ProtectionSet

try:
    from app.ap_shared.bills.working.builds import WorkingBuilder
except ImportError:
    WorkingBuilder = None


def source_db(rows):
    from app.ap_shared.bills.normalization import vendor_key,invoice_key
    db = sqlite3.connect(':memory:')
    db.execute('create table bill_records(ordinal integer primary key,record text,vendor_key text,reference_key text,kind text,amount integer)')
    db.executemany('insert into bill_records values(?,?,?,?,?,?)', [(n,json.dumps(r),vendor_key(r['vendor']),invoice_key(r['invoiceNumber']),r.get('kind','invoice'),r['amount']) for n,r in enumerate(rows)])
    db.commit()
    return db


def build(db, rows, folder, *, mode='last_12_months', protections=None):
    source=dict(importId=I,sourceDigest='a'*64,recordCount=len(rows))
    policy=make_policy(mode,datetime(2026,10,30,16,tzinfo=timezone.utc))
    builder=WorkingBuilder(db,folder,source,policy,protections or ProtectionSet(),time.monotonic)
    try:
        for _ in range(10000):
            if builder.step(time.monotonic()+5)['done']:return builder.artifacts()
        raise AssertionError('Working-set preparation did not finish')
    finally:builder.close()


def manifest_for_built(result):
    manifest={**result['summary'], 'workingSetId':S}
    for name in ('index','context'):
        info=result[name+'Archive']
        manifest[name+'Archive']={**info,'key':f'{W}/bill-working/v1/{manifest["workingDigest"]}/{info["hash"]}.sqlite.gz'}
    return manifest


class WorkingBuildTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(WorkingBuilder,'Bounded active index preparation is not implemented')

    def test_subset_mapping_counts_source_immutable_and_repeatable(self):
        rows=[bill(invoiceNumber='OLD'),bill(invoiceNumber='RECENT',invoiceDate='2026-10-01'),
              bill(invoiceNumber='OPEN',status='Open'),bill(invoiceNumber='PROTECTED')]
        p=ProtectionSet();p.add_duplicate({'decision':'unreviewed','memberCount':2},
            [dict(ordinal=0,bill=rows[3]),dict(ordinal=1,bill=rows[1])])
        db=source_db(rows);before=db.execute('select * from bill_records').fetchall()
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=build(db,rows,Path(folder)/'first',protections=p)
                self.assertEqual(result['summary']['activeCount'],3)
                self.assertEqual(result['summary']['archivedCount'],1)
                self.assertEqual(result['summary']['retainedReasonCounts'],dict(recent=1,unsettled=1,follow_up=2))
                with gzip.open(result['indexArchivePath'],'rb') as packed:
                    target=Path(folder)/'read.sqlite';target.write_bytes(packed.read())
                with closing(sqlite3.connect(target)) as index:
                    found=index.execute('select ordinal,source_ordinal,record from working_records order by ordinal').fetchall()
                    self.assertEqual([(n,o) for n,o,_ in found],[(0,1),(1,2),(2,3)])
                    self.assertEqual([json.loads(r)['id'] for _,_,r in found],[f'{I}:1',f'{I}:2',f'{I}:3'])
                    self.assertEqual(index.execute('select max(ordinal) from archive_vendors').fetchone()[0],3)
                repeated=build(db,rows,Path(folder)/'repeat',protections=p)
                self.assertEqual(result['indexArchive'],repeated['indexArchive'])
                self.assertEqual(result['contextArchive'],repeated['contextArchive'])
                self.assertEqual(db.execute('select * from bill_records').fetchall(),before)
        finally:db.close()

    def test_empty_and_all_sets_valid_without_a_fake_bill(self):
        rows=[bill(invoiceNumber='OLD')];db=source_db(rows)
        try:
            with tempfile.TemporaryDirectory() as folder:
                for mode,count in [('last_12_months',0),('all',1)]:
                    with self.subTest(mode=mode):
                        result=build(db,rows,Path(folder)/mode,mode=mode)
                        self.assertEqual(result['summary']['activeCount'],count)
                        from app.ap_shared.bills.working.contracts import validate_working_manifest
                        validate_working_manifest(manifest_for_built(result))
        finally:db.close()

    def test_missing_original_rows_and_deadline_never_publish_partial_set(self):
        rows=[bill(),bill(invoiceNumber='SECOND')];db=source_db(rows)
        db.execute('delete from bill_records where ordinal=0');db.commit()
        try:
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):build(db,rows,folder)
        finally:db.close()

    def test_expired_step_does_no_work_and_keeps_artifacts_unavailable(self):
        rows=[bill(invoiceDate='2026-10-01')];db=source_db(rows)
        try:
            with tempfile.TemporaryDirectory() as folder:
                builder=WorkingBuilder(db,folder,dict(importId=I,sourceDigest='a'*64,recordCount=1),
                    make_policy('last_12_months',datetime(2026,10,30,16,tzinfo=timezone.utc)),ProtectionSet(),time.monotonic)
                try:
                    progress=builder.step(time.monotonic()-1)
                    self.assertEqual(progress['recordsRead'],0)
                    self.assertFalse(progress['done'])
                    with self.assertRaises(ValueError):builder.artifacts()
                finally:builder.close()
        finally:db.close()


if __name__=='__main__':unittest.main()
