import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from fixtures.ap_shared.duplicate_cases import PIN, bill
from test_ap_duplicates_repository import DuplicateTransport
from test_ap_shared_repository import make_repository
from test_ap_shared_access import CONFIG


class DuplicateArtifactTests(unittest.TestCase):
    def fixture(self):
        from app.ap_shared.bills.duplicates.scan import DuplicateScan
        from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactWriter
        from app.ap_shared.bills.duplicates.repository import DuplicateRepository
        temp = tempfile.TemporaryDirectory(prefix='duplicate-artifact-'); self.addCleanup(temp.cleanup)
        folder = Path(temp.name); source = folder / 'working.sqlite'
        db = sqlite3.connect(source)
        pin = {**PIN, 'recordCount': 3}
        engine = DuplicateScan(db, pin, time.monotonic)
        engine.ingest([dict(ordinal=0, bill=bill()), dict(ordinal=1, bill=bill('271712X')),
                       dict(ordinal=2, bill=bill('WORKING-ONLY-SECRET', vendor='Unrelated'))])
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
                    source_digest=PIN['sourceDigest'], rule_version='bill-duplicates-v1', result_info=report['artifact'])
        return folder, source, packed, report, repo, scan, transport

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
                    'update findings set member_count=99'):
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
