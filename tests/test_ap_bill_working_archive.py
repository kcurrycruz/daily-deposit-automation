from contextlib import closing
import gzip
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
import test_ap_bill_working_builds as fixtures

try:
    from app.ap_shared.bills.working.archive import WorkingCache
except ImportError:
    WorkingCache = None


class LocalWorkingStorage:
    def __init__(self,result):self.result=result;self.reads=[]
    def read_artifact(self,manifest,name,target):
        self.reads.append(name);Path(target).write_bytes(Path(self.result[name+'ArchivePath']).read_bytes())


class WorkingArchiveTests(unittest.TestCase):
    def test_missing_historical_key_is_unavailable_and_auth_denial_releases_files(self):
        self.assertIsNotNone(WorkingCache,'Verified active-only index cache is not implemented')
        rows=[fixtures.bill(invoiceDate='2026-10-01')];source=fixtures.source_db(rows)
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=fixtures.build(source,rows,Path(folder)/'build');mf=fixtures.manifest_for_built(result)
                target=Path(folder)/'context.sqlite'
                with gzip.open(result['contextArchivePath'],'rb') as packed:target.write_bytes(packed.read())
                with closing(sqlite3.connect(target)) as db:
                    db.execute('delete from profiles');db.commit()
                raw=target.read_bytes();packed=gzip.compress(raw,mtime=0)
                Path(result['contextArchivePath']).write_bytes(packed)
                info=mf['contextArchive'];info.update(hash=hashlib.sha256(packed).hexdigest(),bytes=len(packed),expandedHash=hashlib.sha256(raw).hexdigest(),expandedBytes=len(raw))
                info['key']=f'{fixtures.W}/bill-working/v1/{mf["workingDigest"]}/{info["hash"]}.sqlite.gz'
                cache=WorkingCache(LocalWorkingStorage(result))
                try:
                    with self.assertRaises(ValueError):
                        for _ in range(100):
                            if cache.prepare(mf,'auth',lambda a:None,time.monotonic()+5):break
                    self.assertFalse(cache.entries)
                    def denied(auth):raise PermissionError('locked')
                    with self.assertRaises(PermissionError):cache.prepare(mf,'auth',denied,time.monotonic()+5)
                finally:cache.close()
        finally:source.close()

    def test_verified_warm_cache_never_reads_complete_source(self):
        self.assertIsNotNone(WorkingCache,'Verified active-only index cache is not implemented')
        rows=[fixtures.bill(invoiceDate='2026-10-01')];source=fixtures.source_db(rows)
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=fixtures.build(source,rows,Path(folder)/'build');mf=fixtures.manifest_for_built(result)
                storage=LocalWorkingStorage(result);cache=WorkingCache(storage)
                try:
                    for _ in range(100):
                        if cache.prepare(mf,'auth',lambda a:None,time.monotonic()+5):break
                    else:self.fail('Cache preparation did not finish')
                    for _ in range(2):
                        with cache.acquire(mf,'auth',lambda a:None) as (db,context):
                            self.assertEqual(db.execute('select count(*) from working_records').fetchone()[0],1)
                    self.assertEqual(storage.reads,['index','context'])
                finally:cache.close()
        finally:source.close()

    def test_rehashed_wrong_original_mapping_is_rejected_before_ready(self):
        self.assertIsNotNone(WorkingCache,'Verified active-only index cache is not implemented')
        rows=[fixtures.bill(invoiceDate='2026-10-01')];source=fixtures.source_db(rows)
        try:
            with tempfile.TemporaryDirectory() as folder:
                result=fixtures.build(source,rows,Path(folder)/'build');mf=fixtures.manifest_for_built(result)
                target=Path(folder)/'corrupt.sqlite'
                with gzip.open(result['indexArchivePath'],'rb') as packed:target.write_bytes(packed.read())
                with closing(sqlite3.connect(target)) as db:
                    db.execute('update working_records set source_ordinal=4');db.commit()
                raw=target.read_bytes();packed=gzip.compress(raw,mtime=0)
                Path(result['indexArchivePath']).write_bytes(packed)
                info=mf['indexArchive'];info.update(hash=hashlib.sha256(packed).hexdigest(),bytes=len(packed),expandedHash=hashlib.sha256(raw).hexdigest(),expandedBytes=len(raw))
                info['key']=f'{fixtures.W}/bill-working/v1/{mf["workingDigest"]}/{info["hash"]}.sqlite.gz'
                cache=WorkingCache(LocalWorkingStorage(result))
                try:
                    with self.assertRaises(ValueError):
                        for _ in range(100):
                            if cache.prepare(mf,'auth',lambda a:None,time.monotonic()+5):break
                finally:cache.close()
        finally:source.close()


if __name__=='__main__':unittest.main()
