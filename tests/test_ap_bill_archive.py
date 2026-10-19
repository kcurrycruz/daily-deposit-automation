from contextlib import contextmanager
import gzip
import hashlib
import importlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from app.ap_shared.bills.index import SnapshotIndex
from app.ap_shared.bills.parser import CsvStage
from fixtures.ap_shared.bill_exports import export
from test_ap_bill_contracts import manifest, WORKSPACE


class BillArchiveTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module('app.ap_shared.bills.archive')
        except ModuleNotFoundError:
            self.fail('Verified BILL archives and private cache are not implemented')
        self.tmp = tempfile.TemporaryDirectory(prefix='ap-bill-archive-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_compression_variants_preserve_original_identity(self):
        source = export([{}]).encode()
        first = self.api.verify_csv_archive(io.BytesIO(gzip.compress(source, mtime=0)), self.root / 'one.csv')
        second = self.api.verify_csv_archive(io.BytesIO(gzip.compress(source, mtime=10)), self.root / 'two.csv')
        self.assertEqual(first['originalHash'], hashlib.sha256(source).hexdigest())
        self.assertEqual(first['originalHash'], second['originalHash'])
        self.assertNotEqual(first['archiveHash'], second['archiveHash'])
        self.assertEqual((self.root / 'one.csv').read_bytes(), source)

    def test_corrupt_and_oversized_expansion_fail_before_success(self):
        for payload in [b'not gzip', gzip.compress(b'A' * 101)[:-4]]:
            with self.assertRaises(ValueError):
                self.api.verify_csv_archive(io.BytesIO(payload), self.root / 'bad.csv')
        with patch.object(self.api, 'MAX_SOURCE_BYTES', 100), self.assertRaises(ValueError):
            self.api.verify_csv_archive(io.BytesIO(gzip.compress(b'A' * 101)), self.root / 'too-big.csv')

    def make_index(self):
        path = self.root / 'index.sqlite'
        db = sqlite3.connect(path)
        parser = CsvStage(db, io.StringIO(export([{}])))
        while not parser.read_step()['done']: pass
        index = SnapshotIndex(db)
        while not index.consolidate_step()['done']: pass
        info = index.finish(); db.close()
        writer = self.api.IndexArchiveWriter(path, self.root / 'index.gz')
        self.addCleanup(writer.close)
        step = writer.step(max_bytes=10, deadline=float('inf'))
        self.assertFalse(step['done'])
        while not step['done']:
            step = writer.step(max_bytes=4096, deadline=float('inf'))
        return path, info, step['artifact']

    def test_index_pack_is_bounded_and_hash_verified(self):
        path, _, artifact = self.make_index()
        compressed = (self.root / 'index.gz').read_bytes()
        self.assertEqual(hashlib.sha256(compressed).hexdigest(), artifact['hash'])
        self.assertEqual(hashlib.sha256(gzip.decompress(compressed)).hexdigest(), artifact['expandedHash'])
        self.assertEqual(gzip.decompress(compressed), path.read_bytes())

    def cache_fixture(self):
        _, info, artifact = self.make_index()
        mf = manifest(); mf.update(info['counts']); mf['vendorDigest'] = info['vendorDigest']
        mf['indexArchive'] = {**artifact, 'key': f'{WORKSPACE}/bills/v2/' + mf['originalHash'] + '/' + artifact['hash'] + '.sqlite.gz'}
        data = (self.root / 'index.gz').read_bytes()
        source = type('Source', (), {})()
        source.reads = 0
        def read_artifact(manifest, name, target):
            source.reads += 1
            Path(target).write_bytes(data)
        source.read_artifact = read_artifact
        clock = [0.0]
        cache = self.api.SnapshotCache(source, lambda: clock[0])
        self.addCleanup(cache.close)
        return mf, cache, source, clock

    def test_cache_requires_current_request_authorization_and_opens_readonly(self):
        mf, cache, source, _ = self.cache_fixture()
        def deny(auth): raise PermissionError('locked')
        with self.assertRaises(PermissionError), cache.acquire(WORKSPACE, WORKSPACE, mf, 'locked', deny): pass
        self.assertEqual(source.reads, 0)
        for auth in ['session-one', 'session-two']:
            checks = []
            with cache.acquire(WORKSPACE, WORKSPACE, mf, auth, lambda a: checks.append(a)) as db:
                self.assertEqual(db.execute('select count(*) from bill_records').fetchone()[0], 1)
                with self.assertRaises(sqlite3.DatabaseError): db.execute('delete from bill_records')
                with self.assertRaises(sqlite3.DatabaseError): db.execute("select load_extension('bad')")
            self.assertGreaterEqual(len(checks), 3)
            self.assertEqual(set(checks), {auth})
        self.assertEqual(source.reads, 1)

    def test_cache_digest_tampering_and_expiry_never_return_stale_data(self):
        mf, cache, source, clock = self.cache_fixture()
        wrong = {**mf, 'indexArchive': {**mf['indexArchive'], 'expandedHash': 'f' * 64}}
        with self.assertRaises(ValueError), cache.acquire(WORKSPACE, WORKSPACE, wrong, 'a', lambda a: None): pass
        with cache.acquire(WORKSPACE, WORKSPACE, mf, 'a', lambda a: None): pass
        reads = source.reads
        clock[0] = 3601
        with cache.acquire(WORKSPACE, WORKSPACE, mf, 'b', lambda a: None): pass
        self.assertEqual(source.reads, reads + 1)

    def test_pinned_cache_entry_is_not_evicted_to_admit_another(self):
        mf, cache, source, _ = self.cache_fixture()
        cache.budget = mf['indexArchive']['expandedBytes']
        with cache.acquire(WORKSPACE, WORKSPACE, mf, 'a', lambda a: None) as db:
            with self.assertRaises(ValueError), cache.acquire(WORKSPACE, '00000000-0000-4000-8000-000000000002', mf, 'b', lambda a: None): pass
            self.assertEqual(db.execute('select count(*) from bill_records').fetchone()[0], 1)
