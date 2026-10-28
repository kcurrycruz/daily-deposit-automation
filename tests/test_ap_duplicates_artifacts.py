import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4
from fixtures.ap_shared.duplicate_cases import PIN, bill
from test_ap_duplicates_repository import DuplicateTransport
from test_ap_shared_repository import make_repository
from test_ap_shared_access import CONFIG
from app.ap_shared.bills.duplicates.contracts import RULE_VERSION


class DuplicateArtifactTests(unittest.TestCase):
    def test_packaging_rejects_unbound_evidence_before_compressed_output(self):
        from test_ap_duplicates_vendor_scan import history
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter
        rows=history()+[bill('INV451234',amount=88888),bill('INV45124',amount=88888)]
        folder,source,*_=self.fixture(rows)
        with sqlite3.connect(source) as db:
            value=json.loads(db.execute('select evidence from findings').fetchone()[0])
            for p in value['profiles']:p['vendor']='Unrelated'
            db.execute('update findings set evidence=?',(json.dumps(value),))
        db.close()
        target=folder/'corrupt.gz';writer=DuplicateArtifactWriter(source,target);self.addCleanup(writer.close)
        with self.assertRaises(ValueError):
            while not writer.step()['done']:pass
        self.assertFalse(target.exists())

    def test_packaging_resumes_on_a_different_request_thread(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter
        folder, source, _, _, _, _, _ = self.fixture()
        writer = DuplicateArtifactWriter(source, folder / 'cross-thread.gz')
        self.addCleanup(writer.close)
        report = writer.step()
        for _ in range(30):
            if report['done']:
                break
            # Streamlit reruns do not retain the creating script thread.
            with ThreadPoolExecutor(max_workers=1) as request:
                report = request.submit(writer.step).result()
        self.assertTrue(report['done'])
        self.assertEqual(report['artifact']['findingCount'], 1)
        self.assertEqual(report['artifact']['recordCount'], 3)
        raw = gzip.decompress((folder / 'cross-thread.gz').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), report['artifact']['expandedHash'])

    def test_semantically_corrupt_profiles_fail_both_cache_loading_paths(self):
        from test_ap_duplicates_vendor_scan import history
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        rows=history()+[bill('INV451234',amount=88888),bill('INV45124',amount=88888)]
        folder,_,packed,_,repo,scan,transport=self.fixture(rows)
        original=gzip.decompress(packed.read_bytes())
        for corruption in ('vendor','future','member'):
            target=folder/'invalid-profile.sqlite';target.write_bytes(original)
            db=sqlite3.connect(target)
            try:
                value=json.loads(db.execute('select evidence from findings').fetchone()[0])
                if corruption=='vendor':
                    for p in value['profiles']:p['vendor']='Unrelated'
                elif corruption=='future':
                    for p in value['profiles']:p.update(periodStart='2026-10-01',periodEnd='2027-09-30')
                else:db.execute('update members set ordinal=0 where ordinal=24')
                db.execute('update findings set evidence=?',(json.dumps(value),));db.commit()
            finally:db.close()
            payload=target.read_bytes();archive=gzip.compress(payload,mtime=0)
            corrupt=folder/'invalid-profile.gz';corrupt.write_bytes(archive)
            info=dict(**{**scan['result_info'],'hash':hashlib.sha256(archive).hexdigest(),'bytes':len(archive),
                  'expandedHash':hashlib.sha256(payload).hexdigest(),'expandedBytes':len(payload)})
            manifest=repo.put_result({**scan,'result_info':info},corrupt,str(uuid4()))
            for cooperative in (False,True):
                cache=DuplicateArtifactCache(repo);self.addCleanup(cache.close)
                with self.subTest(corruption=corruption,cooperative=cooperative),self.assertRaises(ValueError):
                    if cooperative:
                        for _ in range(20):
                            if cache.prepare(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None,time.monotonic()+5):
                                self.fail('corrupt pair became ready')
                    else:
                        with cache.acquire(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None):
                            self.fail('corrupt pair became readable')

    def test_warm_verified_cache_does_not_repeat_full_validation(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        _,_,packed,_,repo,scan,_=self.fixture()
        manifest=repo.put_result(scan,packed,str(uuid4()))
        cache=DuplicateArtifactCache(repo);self.addCleanup(cache.close)
        with patch.object(cache,'_open',wraps=cache._open) as opening:
            for _ in range(2):
                with cache.acquire(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None) as db:
                    self.assertEqual(db.execute('select count(*) from findings').fetchone()[0],1)
            self.assertEqual(opening.call_count,1)

    def test_preparation_yields_before_decompression_and_resumes(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        _,_,packed,_,repo,scan,_=self.fixture()
        manifest=repo.put_result(scan,packed,str(uuid4()))
        cache=DuplicateArtifactCache(repo);self.addCleanup(cache.close)
        self.assertFalse(cache.prepare(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None,deadline=0))
        for _ in range(30):
            if cache.prepare(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None,deadline=time.monotonic()+5):break
        else:self.fail('preparation never completed')
        with cache.acquire(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None,prepared_only=True) as db:
            self.assertEqual(db.execute('select count(*) from findings').fetchone()[0],1)

    def test_new_current_scan_releases_obsolete_partial_preparation(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        _,_,packed,_,repo,scan,_=self.fixture()
        manifest=repo.put_result(scan,packed,str(uuid4()))
        cache=DuplicateArtifactCache(repo);self.addCleanup(cache.close)
        self.assertFalse(cache.prepare(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None,time.monotonic()+5))
        old=next(iter(cache.pending.values()))['unpack'].path.parent
        cache.prepare(CONFIG.workspace_id,str(uuid4()),manifest,None,lambda _:None,time.monotonic()+5)
        self.assertEqual(len(cache.pending),1)
        self.assertFalse(old.exists())
    def fixture(self,bills=None):
        from app.ap_shared.bills.duplicates.scan import DuplicateScan
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter
        from app.ap_shared.bills.duplicates.repository import DuplicateRepository
        temp = tempfile.TemporaryDirectory(prefix='duplicate-artifact-'); self.addCleanup(temp.cleanup)
        folder = Path(temp.name); source = folder / 'working.sqlite'
        db = sqlite3.connect(source)
        bills=bills or [bill(),bill('271712X'),bill('WORKING-ONLY-SECRET',vendor='Unrelated')]
        pin = {**PIN, 'recordCount': len(bills)}
        engine = DuplicateScan(db, pin, time.monotonic)
        engine.ingest([dict(ordinal=n,bill=value) for n,value in enumerate(bills)])
        engine.finish_input()
        while not engine.step(time.monotonic() + 5)['done']:
            pass
        engine.finish(); db.close()
        packed = folder / 'result.gz'; writer = DuplicateArtifactWriter(source, packed)
        self.addCleanup(writer.close)
        report = writer.step()
        while not report['done']:
            report = writer.step()
        transport = DuplicateTransport(); repo = DuplicateRepository(make_repository(transport))
        scan = dict(id=str(uuid4()), workspace_id=CONFIG.workspace_id, import_id=PIN['importId'],
                    source_digest=PIN['sourceDigest'], rule_version=RULE_VERSION, result_info=report['artifact'])
        return folder, source, packed, report, repo, scan, transport

    def test_recorded_vendor_profiles_survive_private_artifact_round_trip(self):
        from test_ap_duplicates_vendor_scan import history
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        rows=history()+[bill('INV451234',amount=88888),bill('INV45124',amount=88888)]
        _,_,packed,_,repo,scan,_=self.fixture(rows)
        manifest=repo.put_result(scan,packed,str(uuid4()))
        self.assertEqual(manifest['format'],'bill-duplicates-v2')
        cache=DuplicateArtifactCache(repo);self.addCleanup(cache.close)
        with cache.acquire(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None) as db:
            self.assertEqual(db.execute('pragma user_version').fetchone()[0],2)
            kind,raw=db.execute('select classification,evidence from findings').fetchone()
            self.assertEqual(kind,'reference_entry_issue')
            self.assertEqual(len(json.loads(raw)['profiles']),2)

    def test_result_round_trip_has_only_final_evidence_and_reuses_objects(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        _, source, packed, report, repo, scan, transport = self.fixture()
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        raw = gzip.decompress(packed.read_bytes())
        self.assertNotIn(b'WORKING-ONLY-SECRET', raw)
        first = repo.put_result(scan, packed, str(uuid4()))
        self.assertEqual(first, repo.put_result(scan, packed, str(uuid4())))
        self.assertEqual(len(transport.files), 1)
        cache = DuplicateArtifactCache(repo); self.addCleanup(cache.close)
        with cache.acquire(CONFIG.workspace_id, scan['id'], first, None, lambda _: None) as db:
            self.assertEqual({r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")},
                             {'findings', 'members', 'scan_meta'})
            self.assertEqual(db.execute('select count(*) from findings').fetchone()[0], 1)
            self.assertEqual(db.execute('select count(*) from members').fetchone()[0], 2)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('delete from findings')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original)

    def test_manifest_source_workspace_hash_and_size_are_verified(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        _, _, packed, _, repo, scan, _ = self.fixture()
        manifest = repo.put_result(scan, packed, str(uuid4()))
        cache = DuplicateArtifactCache(repo); self.addCleanup(cache.close)
        for changes in [dict(hash='0' * 64), dict(expandedHash='0' * 64), dict(findingCount=99)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                with cache.acquire(CONFIG.workspace_id, scan['id'], {**manifest, **changes}, None, lambda _: None):
                    pass
        with self.assertRaises(PermissionError):
            with cache.acquire(str(uuid4()), scan['id'], manifest, None, lambda _: None):
                pass

    def test_access_expiry_and_active_reader_cleanup_do_not_leak_or_remove_source(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        _, source, packed, _, repo, scan, _ = self.fixture()
        manifest = repo.put_result(scan, packed, str(uuid4()))
        cache = DuplicateArtifactCache(repo); self.addCleanup(cache.close)
        calls = [0]
        def authorize(_):
            calls[0] += 1
            if calls[0] >= 2:
                raise PermissionError('locked')
        with self.assertRaises(PermissionError):
            with cache.acquire(CONFIG.workspace_id, scan['id'], manifest, None, authorize):
                pass
        with cache.acquire(CONFIG.workspace_id, scan['id'], manifest, None, lambda _: None) as db:
            cache.close()
            self.assertEqual(db.execute('select count(*) from findings').fetchone()[0], 1)
        self.assertTrue(source.exists())

    def test_compressed_limit_and_expansion_limit_are_not_silent_truncation(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter, DuplicateArtifactCache
        folder, source, packed, _, repo, scan, _ = self.fixture()
        with patch('app.ap_shared.bills.duplicates.artifacts.MAX_ARCHIVE_BYTES', 1):
            writer = DuplicateArtifactWriter(source, folder / 'too-small.gz')
            try:
                with self.assertRaises(ValueError):
                    while not writer.step()['done']:
                        pass
            finally:
                writer.close()
        manifest = repo.put_result(scan, packed, str(uuid4()))
        with patch('app.ap_shared.bills.duplicates.artifacts.MAX_BYTES', 1):
            cache = DuplicateArtifactCache(repo); self.addCleanup(cache.close)
            with self.assertRaises(ValueError):
                with cache.acquire(CONFIG.workspace_id, scan['id'], manifest, None, lambda _: None):
                    pass

    def test_corrupt_sqlite_extra_schema_and_invalid_locators_are_rejected(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        folder, _, packed, _, repo, scan, _ = self.fixture()
        manifest = repo.put_result(scan, packed, str(uuid4()))
        original = gzip.decompress(packed.read_bytes())
        cache = DuplicateArtifactCache(repo); self.addCleanup(cache.close)
        for sql in ('alter table findings add column secret text',
                    'create view unexpected as select * from findings',
                    'update members set ordinal=ordinal+1000',
                    'update findings set member_count=99',
                    "update findings set evidence='{}'"):
            with self.subTest(sql=sql):
                target = folder / 'invalid.sqlite'; target.write_bytes(original)
                db = sqlite3.connect(target)
                try:
                    db.execute(sql); db.commit()
                finally:
                    db.close()
                with self.assertRaises(ValueError):
                    checked = cache._open(target, manifest)
                    checked.close()
        target.write_bytes(b'not sqlite')
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            cache._open(target, manifest)

    def test_exact_compressed_limit_and_access_after_validation(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter, DuplicateArtifactCache
        folder, source, packed, _, repo, scan, _ = self.fixture()
        size = packed.stat().st_size
        with patch('app.ap_shared.bills.duplicates.artifacts.MAX_ARCHIVE_BYTES', size):
            writer = DuplicateArtifactWriter(source, folder / 'exact.gz')
            try:
                while not writer.step()['done']:
                    pass
            finally:
                writer.close()
        with patch('app.ap_shared.bills.duplicates.artifacts.MAX_ARCHIVE_BYTES', size - 1):
            writer = DuplicateArtifactWriter(source, folder / 'over.gz')
            try:
                with self.assertRaises(ValueError):
                    while not writer.step()['done']:
                        pass
            finally:
                writer.close()
        manifest = repo.put_result(scan, packed, str(uuid4()))
        cache = DuplicateArtifactCache(repo); self.addCleanup(cache.close)
        calls = [0]
        def authorize(_):
            calls[0] += 1
            if calls[0] == 3:
                raise PermissionError('expired after decompression')
        with self.assertRaises(PermissionError):
            with cache.acquire(CONFIG.workspace_id, scan['id'], manifest, None, authorize):
                self.fail('expired access must not yield evidence')
        self.assertFalse(cache.entries)

    def test_active_entry_is_not_evicted_and_expired_idle_entries_are(self):
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
        _, _, packed, _, repo, scan, _ = self.fixture()
        manifest=repo.put_result(scan,packed,str(uuid4())); now=[0]
        cache=DuplicateArtifactCache(repo,clock=lambda:now[0]); self.addCleanup(cache.close)
        with patch('app.ap_shared.bills.duplicates.artifacts.MAX_BYTES',manifest['expandedBytes']):
            with cache.acquire(CONFIG.workspace_id,scan['id'],manifest,None,lambda _:None) as db:
                with self.assertRaises(ValueError):
                    with cache.acquire(CONFIG.workspace_id,str(uuid4()),manifest,None,lambda _:None): pass
                self.assertEqual(db.execute('select count(*) from findings').fetchone()[0],1)
            now[0]=3601
            with cache.acquire(CONFIG.workspace_id,str(uuid4()),manifest,None,lambda _:None): pass
            self.assertEqual(len(cache.entries),1)
