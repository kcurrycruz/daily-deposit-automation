"""Local-only release check. No network client or production credentials."""
import argparse
from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from app.ap_shared.bills.parser import CsvStage
from app.ap_shared.bills.index import SnapshotIndex
from app.ap_shared.bills.archive import IndexArchiveWriter
from app.ap_shared.bills.duplicates.operations import DuplicateScanRegistry
from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
from app.ap_shared.bills.duplicates.source import DuplicateSource,SourcePreparationCache
from app.ap_shared.bills.duplicates.projection import ReviewProjection
from app.ap_shared.bills.duplicates.contracts import RULE_VERSION
from bill_scale_check import peak_rss


def letters(number):
    chars=[]
    for _ in range(5):
        chars.append(chr(65+number%26)); number//=26
    return ''.join(reversed(chars))


def source_index(source, path):
    with closing(sqlite3.connect(path)) as db:
        db.execute('pragma cache_size=-8192'); db.execute('pragma temp_store=FILE')
        db.execute('pragma journal_mode=MEMORY');db.execute('pragma synchronous=OFF')
        stage=CsvStage(db,source)
        try:
            while not stage.read_step(deadline=time.monotonic()+5)['done']: pass
        finally: stage.close()
        index=SnapshotIndex(db)
        while not index.consolidate_step(deadline=time.monotonic()+5)['done']: pass
        return index.finish()['counts']


def run_scan(index_path, packed_index, source_counts, pin, *, weekly=False):
    maximum_records=maximum_probes=0;max_seconds=0
    workspace='00000000-0000-4000-8000-000000000099';config=SimpleNamespace(workspace_id=workspace)
    with closing(sqlite3.connect(index_path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        vendor_digest=json.loads(db.execute("select value from bill_meta where key='vendorDigest'").fetchone()[0])
    raw=packed_index.read_bytes();archive_hash=hashlib.sha256(raw).hexdigest()
    expanded_hash=hashlib.sha256()
    with index_path.open('rb') as incoming:
        while chunk:=incoming.read(262144):expanded_hash.update(chunk)
    prefix=workspace+'/bills/v2/'+pin['sourceDigest']+'/'
    manifest=dict(format='snapshot-v2',parserVersion='bill-csv-v1',indexVersion=1,
        originalHash=pin['sourceDigest'],originalBytes=1,**source_counts,vendorDigest=vendor_digest,
        originalArchive=dict(key=prefix+'a'*64+'.csv.gz',hash='a'*64,bytes=1),
        indexArchive=dict(key=prefix+archive_hash+'.sqlite.gz',hash=archive_hash,bytes=len(raw),expandedHash=expanded_hash.hexdigest(),expandedBytes=index_path.stat().st_size))
    del raw
    def copy_index(_manifest,name,target):
        if name!='index':raise AssertionError('only local index reads are expected')
        data=packed_index.read_bytes()
        if hashlib.sha256(data).hexdigest()!=archive_hash:raise AssertionError('index changed')
        Path(target).write_bytes(data)
    bills=SimpleNamespace(config=config,current=lambda:dict(active_import_id=pin['importId'],import_version=pin['importVersion']),
        source=lambda _:dict(id=pin['importId'],state='ready',file_hash=pin['sourceDigest'],storage_format='snapshot-v2',
            record_count=pin['recordCount'],snapshot_manifest=manifest),read_artifact=copy_index)
    ops=SimpleNamespace(repository=bills,_check=lambda _:None)
    source_cache=SourcePreparationCache(bills)
    class LocalSource(DuplicateSource):
        def read_page(self,*args,**kwargs):
            page=super().read_page(*args,**kwargs)
            if weekly:
                for row in page['records']:
                    bill=row['bill'];bill.update(reportedPaidAmount=bill['amount'],status='PaidInFull',reportedFullPaymentDate='2026-10-22')
            return page
    source=LocalSource(SimpleNamespace(config=config),ops,source_cache)
    registry=DuplicateScanRegistry();auth=SimpleNamespace(workspace_id=workspace,session_nonce=str(uuid4()))
    scan=dict(id=str(uuid4()),workspace_id=workspace,session_nonce=auth.session_nonce,generation=str(uuid4()),
        source_pin=pin,source_reader=source,fresh=True,checkpoint=0)
    cache=projection=None
    try:
        registry.claim(scan,auth);engine=registry.handles[scan['id']]['engine']
        while True:
            started=time.monotonic();before_read,before_probe=engine.read,engine.probes
            reply=registry.step(scan,auth,lambda _:None);scan['checkpoint']=reply['checkpoint']
            max_seconds=max(max_seconds,time.monotonic()-started)
            maximum_records=max(maximum_records,engine.read-before_read);maximum_probes=max(maximum_probes,engine.probes-before_probe)
            if reply['artifact']:break
        counts=engine.finish();db=registry.handles[scan['id']]['db'];keys=hashlib.sha256()
        for key, in db.execute('select key from findings order by key'):keys.update(key.encode())
        patterns=dict(db.execute('select classification,count(*) from findings group by classification'))
        artifact=reply['artifact'];result_manifest={**artifact,'key':workspace+'/bill-duplicates/v1/'+pin['importId']+'/'+RULE_VERSION+'/'+artifact['hash']+'.sqlite.gz'}
        def read_result(expected,target):
            data=reply['path'].read_bytes()
            if hashlib.sha256(data).hexdigest()!=expected['hash']:raise AssertionError('result changed')
            Path(target).write_bytes(data)
        repo=SimpleNamespace(config=config,current=lambda:pin,review_revision=lambda:0,
            reviews_page=lambda *_:dict(reviews=[],nextCursor=None),read_result=read_result)
        cache=DuplicateArtifactCache(repo);projection=ReviewProjection(repo,cache,source,time.monotonic)
        ready_scan=dict(id=scan['id'],workspace_id=workspace,import_id=pin['importId'],source_digest=pin['sourceDigest'],rule_version=RULE_VERSION,manifest=result_manifest)
        while True:
            started=time.monotonic();deadline=started+5
            ready=cache.prepare(workspace,scan['id'],result_manifest,auth,lambda _:None,deadline)
            if ready:ready=projection.prepare(ready_scan,auth,deadline)['ready']
            max_seconds=max(max_seconds,time.monotonic()-started)
            if ready:break
        return counts,keys.hexdigest(),patterns,maximum_records,maximum_probes,max_seconds,artifact
    finally:
        if projection:projection.close()
        if cache:cache.close()
        registry.close();source_cache.close()


def check(records, source=None):
    started=time.monotonic();baseline=peak_rss()
    with tempfile.TemporaryDirectory(prefix='hwfc-duplicate-release-') as folder:
        root=Path(folder);source=Path(source) if source else root/'synthetic.csv'
        if source.parent==root:
            with source.open('w',encoding='utf8',newline='') as out:
                writer=csv.writer(out);writer.writerow(['vendor','invoiceNumber','amount'])
                for n in range(records):
                    ref='SYN-'+letters(n);amount='138.00'
                    if n>=records-10000: ref='AMBIGUOUS'
                    if n in (records-10002,records-10001): ref='AMOUNTDIFF';amount='138.00' if n==records-10002 else '139.00'
                    writer.writerow(['Synthetic Supply',ref,amount])
        hasher=hashlib.sha256()
        with source.open('rb') as incoming:
            while chunk:=incoming.read(262144): hasher.update(chunk)
        before_stat=source.stat();index=root/'source.sqlite';source_counts=source_index(source,index)
        packed_index=root/'source.gz';packer=IndexArchiveWriter(index,packed_index)
        try:
            while not packer.step()['done']:pass
        finally:packer.close()
        pin=dict(importId='00000000-0000-4000-8000-000000000001',importVersion=1,sourceDigest=hasher.hexdigest(),storageFormat='snapshot-v2',recordCount=source_counts['recordCount'])
        counts,keys,patterns,max_records,max_probes,max_seconds,artifact=run_scan(index,packed_index,source_counts,pin)
        repeat,repeat_keys,_,more_records,more_probes,more_seconds,_=run_scan(index,packed_index,source_counts,
            {**pin,'importId':'00000000-0000-4000-8000-000000000002','importVersion':2,'sourceDigest':'b'*64},weekly=True)
        after_stat=source.stat()
        if before_stat.st_size!=after_stat.st_size or before_stat.st_mtime_ns!=after_stat.st_mtime_ns:
            raise RuntimeError('Source was modified')
        return dict(recordCount=counts['recordCount'],findingCount=counts['findingCount'],
            peakRssIncreaseBytes=max(0,peak_rss()-baseline),maxRecordsPerStep=max(max_records,more_records),
            maxProbesPerStep=max(max_probes,more_probes),expandedBytes=artifact['expandedBytes'],compressedBytes=artifact['bytes'],
            elapsedSeconds=round(time.monotonic()-started,3),maxStepSeconds=round(max(max_seconds,more_seconds),3),
            repeatKeysStable=keys==repeat_keys and counts['findingCount']==repeat['findingCount'],
            sourceBytes=source.stat().st_size,sourceRows=source_counts['sourceRowCount'],eligibleRecords=counts['eligibleRecords'],
            excludedRecords=counts['excludedRecords'],patterns=patterns)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--records',type=int,choices=(223425,500000),default=223425)
    parser.add_argument('--source');args=parser.parse_args()
    print(json.dumps(check(args.records,args.source),sort_keys=True))
