from contextlib import closing
from datetime import date
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
import test_ap_bill_working_builds as fixtures
from app.ap_shared.bills.duplicates.scan import DuplicateScan
from app.ap_shared.bills.duplicates.contracts import validate_pin
from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter
from app.ap_shared.bills.working.context import HistoryContext


def pin_for(manifest):
    return dict(importId=fixtures.I,importVersion=1,sourceDigest=manifest['workingDigest'],storageFormat='working-v1',
                recordCount=manifest['activeCount'],workingSetId=manifest['workingSetId'],workingDigest=manifest['workingDigest'],
                workingVersion=1,fullSourceDigest=manifest['source']['sourceDigest'],fullRecordCount=manifest['fullRecordCount'],
                mappingDigest=manifest.get('mappingDigest','a'*64))


class WorkingDuplicateTests(unittest.TestCase):
    def test_source_reads_active_records_and_resolves_original_members(self):
        import test_ap_bill_working_operations as operations
        from app.ap_shared.bills.duplicates.source import DuplicateSource
        from types import SimpleNamespace
        f=operations.WorkingOperationsTests();f.setUp();self.addCleanup(f.doCleanups)
        job=f.begin();f.prepare(job);current=f.activate(job)
        source=DuplicateSource(SimpleNamespace(config=f.repo.config),f.bill_ops,working=f.ops)
        pin=source.pin(f.auth)
        self.assertEqual(pin['recordCount'],1);self.assertEqual(pin['fullRecordCount'],2)
        self.assertTrue(source.prepare(pin,f.auth,time.monotonic()+5))
        page=source.read_page(pin,-1,5000,f.auth)
        self.assertEqual(page['records'][0]['ordinal'],0)
        self.assertEqual(page['records'][0]['sourceOrdinal'],1)
        members=source.members(pin,[0],f.auth)
        self.assertEqual(members[0]['bill']['id'],f'{fixtures.I}:1')
        self.assertEqual(members[0]['sourceOrdinal'],1)

    def test_scoped_operations_complete_and_reject_previous_range(self):
        import test_ap_bill_working_operations as operations
        from app.ap_shared.bills.duplicates.source import DuplicateSource
        from app.ap_shared.bills.duplicates.operations import DuplicateOperations,DuplicateScanRegistry
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        from app.ap_shared.bills.duplicates.projection import ReviewProjection
        from fixtures.ap_shared.duplicate_store_double import DuplicateStoreDouble
        from types import SimpleNamespace
        from uuid import uuid4
        f=operations.WorkingOperationsTests();f.setUp();self.addCleanup(f.doCleanups)
        job=f.begin();f.prepare(job);current=f.activate(job)
        source=DuplicateSource(SimpleNamespace(config=f.repo.config),f.bill_ops,working=f.ops)
        f.service.repository.config=f.repo.config
        repo=DuplicateStoreDouble(f.service.repository,None)
        repo.current=lambda:source.pin(f.auth)
        registry=DuplicateScanRegistry();self.addCleanup(registry.close)
        cache=DuplicateArtifactCache(repo);self.addCleanup(cache.close)
        projection=ReviewProjection(repo,cache,source,time.monotonic);self.addCleanup(projection.close)
        api=DuplicateOperations(repo,source,registry,cache,projection,f.repo.config,lambda:__import__("test_ap_shared_access").NOW,f.service.revalidate)
        call=lambda action,payload:api.handle(action,payload,str(uuid4()),f.auth)
        payload=dict(import_id=fixtures.I,expected_import_version=1,working_set_id=current['workingSet']['workingSetId'],expected_working_version=current['workingVersion'])
        progress=call('duplicate_ensure',payload)
        for _ in range(100):
            if progress['state']=='ready' and progress['projectionReady']:break
            progress=call('duplicate_status',dict(scan_id=progress['scanId'])) if progress['state']=='ready' else call('duplicate_step',dict(scan_id=progress['scanId'],generation=progress['generation'],expected_checkpoint=progress['checkpoint'],restart=False))
        else:self.fail('Scoped operations did not finish')
        self.assertEqual(progress['ruleVersion'],'bill-duplicates-v4')
        self.assertEqual(progress['workingSetId'],payload['working_set_id'])
        self.assertEqual(progress['totalRecords'],1);self.assertEqual(progress['fullRecordCount'],2)
        self.assertEqual(progress['counts']['all'],0)
        with self.assertRaises(ValueError):call('duplicate_ensure',{**payload,'expected_working_version':0})
        all_job=f.call('bill_range_begin',dict(source_import_id=fixtures.I,mode='all',expected_import_version=1,expected_working_version=1))
        f.prepare(all_job);new=f.activate(all_job)
        with self.assertRaises(ValueError):call('duplicate_status',dict(scan_id=progress['scanId']))
        another=call('duplicate_ensure',{**payload,'working_set_id':new['workingSet']['workingSetId'],'expected_working_version':new['workingVersion']})
        self.assertNotEqual(another['scanId'],progress['scanId'])

    def test_empty_active_set_completes_and_corrupt_mapping_never_publishes(self):
        from app.ap_shared.bills.working.contracts import MappingDigest
        rows=[fixtures.bill(invoiceDate='2025-01-01')]
        source=fixtures.source_db(rows)
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=fixtures.build(source,rows,Path(folder)/'build');manifest=fixtures.manifest_for_built(result)
                self.assertEqual(manifest['activeCount'],0)
                for name in ('index','context'):
                    with gzip.open(result[name+'ArchivePath'],'rb') as incoming:(Path(folder)/(name+'.sqlite')).write_bytes(incoming.read())
                with closing(sqlite3.connect(Path(folder)/'context.sqlite')) as context,closing(sqlite3.connect(Path(folder)/'scan.sqlite')) as db:
                    engine=DuplicateScan(db,pin_for(manifest),time.monotonic);engine.vendor_candidates.patterns.context=HistoryContext(context)
                    engine.finish_input()
                    while not engine.step(time.monotonic()+5)['done']:pass
                    self.assertEqual(engine.finish()['findingCount'],0)
                    writer=DuplicateArtifactWriter(Path(folder)/'scan.sqlite',Path(folder)/'empty.gz')
                    try:
                        while not (packed:=writer.step())['done']:pass
                        self.assertEqual(packed['artifact']['recordCount'],0)
                    finally:writer.close()
                # Even rehashed compressed bytes cannot change the committed original mapping.
                from types import SimpleNamespace
                import hashlib
                from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
                db=sqlite3.connect(Path(folder)/'scan.sqlite')
                db.execute('insert into source_map values(0,0,?)',('a'*64,));db.commit();db.close()
                raw=(Path(folder)/'scan.sqlite').read_bytes();archive=gzip.compress(raw,mtime=0)
                digest=hashlib.sha256(archive).hexdigest()
                from test_ap_shared_access import CONFIG
                mf={**packed['artifact'],'hash':digest,'bytes':len(archive),'expandedHash':hashlib.sha256(raw).hexdigest(),'expandedBytes':len(raw),
                    'key':f'{CONFIG.workspace_id}/bill-duplicates/v3/{fixtures.I}/bill-duplicates-v4/{digest}.sqlite.gz'}
                fake=SimpleNamespace(config=CONFIG,read_result=lambda manifest,target:target.write_bytes(archive))
                for cooperative in (False,True):
                    cache=DuplicateArtifactCache(fake)
                    try:
                        with self.assertRaises(ValueError):
                            if cooperative:
                                for _ in range(100):
                                    if cache.prepare(CONFIG.workspace_id,fixtures.S,mf,None,lambda _:None,time.monotonic()+5):self.fail('Corrupt mapping became ready')
                            else:
                                with cache.acquire(CONFIG.workspace_id,fixtures.S,mf,None,lambda _:None):self.fail('Corrupt mapping became readable')
                    finally:cache.close()

                writer=DuplicateArtifactWriter(Path(folder)/'scan.sqlite',Path(folder)/'bad.gz')
                try:
                    with self.assertRaises(ValueError):
                        while not writer.step()['done']:pass
                finally:writer.close()
        finally:source.close()

    def test_scoped_pin_explicit_zero_count_and_provenance(self):
        value=dict(importId=fixtures.I,importVersion=1,sourceDigest='a'*64,storageFormat='working-v1',recordCount=0,
                   workingSetId=fixtures.S,workingDigest='a'*64,workingVersion=2,fullSourceDigest='b'*64,fullRecordCount=1,mappingDigest='c'*64)
        self.assertEqual(validate_pin(value),value)
        for field in ['workingSetId','mappingDigest','fullSourceDigest']:
            bad=dict(value);bad.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError):validate_pin(bad)

    def test_only_active_pair_scanned_with_full_historical_format_context(self):
        rows=[fixtures.bill(vendor='Synthetic',invoiceNumber=f'INV{1000+n:06}',amount=1000+n,invoiceDate='2025-10-20') for n in range(24)]
        rows += [fixtures.bill(vendor='Synthetic',invoiceNumber='INV451234',amount=88888,invoiceDate='2025-11-01'),
                 fixtures.bill(vendor='Synthetic',invoiceNumber='INV45124',amount=88888,invoiceDate='2025-11-02')]
        source=fixtures.source_db(rows)
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=fixtures.build(source,rows,Path(folder)/'build');manifest=fixtures.manifest_for_built(result)
                self.assertEqual(manifest['activeCount'],2)
                for name in ('index','context'):
                    with gzip.open(result[name+'ArchivePath'],'rb') as packed:(Path(folder)/(name+'.sqlite')).write_bytes(packed.read())
                with closing(sqlite3.connect(Path(folder)/'index.sqlite')) as index,closing(sqlite3.connect(Path(folder)/'context.sqlite')) as context:
                    working=Path(folder)/'scan.sqlite';db=sqlite3.connect(working)
                    try:
                        engine=DuplicateScan(db,pin_for(manifest),time.monotonic)
                        engine.vendor_candidates.patterns.context=HistoryContext(context)
                        items=[dict(ordinal=n,sourceOrdinal=original,bill=json.loads(raw)) for n,original,raw in index.execute('select ordinal,source_ordinal,record from working_records order by ordinal')]
                        engine.ingest(items);engine.finish_input()
                        for _ in range(10000):
                            if engine.step(time.monotonic()+5,max_probes=25)['done']:break
                        else:self.fail('Scoped scan did not finish')
                        self.assertEqual(engine.finish()['recordCount'],2)
                        self.assertEqual(db.execute('select classification from findings').fetchall(),[('reference_entry_issue',)])
                        self.assertEqual(db.execute('select ordinal,source_ordinal from source_map order by ordinal').fetchall(),[(0,24),(1,25)])
                        detail=json.loads(db.execute('select evidence from findings').fetchone()[0])
                        self.assertTrue(all(p['distinctReferences']==24 for p in detail['profiles']))
                        writer=DuplicateArtifactWriter(working,Path(folder)/'result.gz')
                        try:
                            for _ in range(1000):
                                packed=writer.step(deadline=time.monotonic()+5)
                                if packed['done']:break
                            else:self.fail('Scoped artifact did not finish')
                            self.assertEqual(packed['artifact']['format'],'bill-duplicates-v3')
                            self.assertEqual(packed['artifact']['ruleVersion'],'bill-duplicates-v4')
                            self.assertEqual(packed['artifact']['workingSetId'],manifest['workingSetId'])
                        finally:writer.close()
                    finally:db.close()
        finally:source.close()


if __name__=='__main__':unittest.main()

