"""Local-only, sanitized scale check. Never imports a network storage client."""
import argparse
from contextlib import closing
import csv
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from app.ap_shared.bills.builds import BuildRegistry
from app.ap_shared.bills.archive import verify_csv_archive
from app.ap_shared.bills.index import SnapshotIndex


def peak_rss():
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
                ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
                 'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        counter=Counters();counter.cb=ctypes.sizeof(counter)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counter),counter.cb):raise ctypes.WinError(ctypes.get_last_error())
        return counter.PeakWorkingSetSize
    import resource
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform=='darwin' else value*1024


def check(source=None, synthetic_records=223425):
    started=time.monotonic();baseline=peak_rss()
    with tempfile.TemporaryDirectory(prefix='hwfc-scale-') as folder:
        root=Path(folder);source=Path(source) if source else root/'synthetic.csv'
        if source.parent==root:
            with source.open('w',newline='',encoding='utf-8') as output:
                writer=csv.writer(output);writer.writerow(['vendor','invoiceNumber','amount'])
                for i in range(synthetic_records):writer.writerow(['Synthetic Supplier',f'QA-{i:08d}','138.00'])
        archive=root/'original.gz';raw_hash=hashlib.sha256()
        with source.open('rb') as original,archive.open('wb') as output,gzip.GzipFile(filename='',fileobj=output,mode='wb',mtime=0) as packed:
            while chunk:=original.read(262144):raw_hash.update(chunk);packed.write(chunk)
        original_hash=raw_hash.hexdigest()
        with _registry(root) as registry:
            job=dict(id=str(uuid4()),generation=str(uuid4()),workspace_id=str(uuid4()),session_nonce=str(uuid4()))
            paths=registry.paths(job['id'])
            with archive.open('rb') as packed:verified=verify_csv_archive(packed,paths['csv'])
            registry.start(job)
            auth=SimpleNamespace(workspace_id=job['workspace_id'],session_nonce=job['session_nonce'])
            progress={'checkpoint':0,'state':'reading'};previous=0;max_rows=0;max_seconds=0;steps=0
            while progress['state']!='prepared':
                step_start=time.monotonic()
                progress=registry.step(job['id'],job['generation'],progress['checkpoint'],auth,lambda _:None)
                max_seconds=max(max_seconds,time.monotonic()-step_start)
                max_rows=max(max_rows,progress['sourceRowCount']-previous);previous=progress['sourceRowCount'];steps+=1
            artifact=registry.artifacts(job['id']);counts=artifact['summary']['counts']
            with closing(sqlite3.connect(f'file:{paths["index"].as_posix()}?mode=ro',uri=True)) as db:
                index=SnapshotIndex(db,build=False)
                # Page every same-vendor/equal-amount candidate in the synthetic stress case.
                query=dict(importId=str(uuid4()),references=[],amounts=[])
                if source.parent==root:query['amounts']=[dict(vendorKey='synthetic supplier',kind='invoice',amount=13800)]
                else:
                    sample=db.execute('select reference_key,kind from bill_records order by ordinal limit 1').fetchone()
                    query['references']=[dict(invoiceKey=sample[0],kind=sample[1])]
                after=-1;queried=0
                while True:
                    page=index.candidates_page(query,after=after);queried+=len(page['records'])
                    if page['nextCursor'] is None:break
                    after=page['nextCursor']
                freelist=db.execute('pragma freelist_count').fetchone()[0]
                expanded=paths['index'].stat().st_size
            result={**counts,'originalHash':original_hash,'decompressedArchiveHash':verified['originalHash'],
                    'originalBytes':source.stat().st_size,'originalArchiveBytes':archive.stat().st_size,
                    'indexArchiveBytes':artifact['indexArchive']['bytes'],'expandedIndexBytes':expanded,
                    'freeIndexPages':freelist,'maxSourceRowsPerStep':max_rows,'maxStepSeconds':round(max_seconds,3),
                    'buildSteps':steps,'deepQueryCandidateCount':queried}
        if source.parent==root:
            result['activeRecordCountAfterRepeat']=check_replacement(source,synthetic_records)
        result.update(peakRssIncreaseBytes=max(0,peak_rss()-baseline),elapsedSeconds=round(time.monotonic()-started,3))
        return result


class _registry:
    def __init__(self,root):self.value=BuildRegistry(root)
    def __enter__(self):return self.value
    def __exit__(self,*args):self.value.close()


def check_replacement(source,count):
    # Exercise actual orchestration and immutable source reuse against an in-memory
    # external boundary; its transaction rules also have real PostgreSQL tests.
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from test_ap_bill_operations import BillOperationsTests
    case=BillOperationsTests();case.setUp()
    try:
        contents=source.read_text(encoding='utf-8')
        job,progress=case.upload(contents);first=case.finish(job,progress)
        duplicate,same=case.upload(contents,filename='renamed-weekly.csv',mtime=42)
        assert same['alreadyCurrent'] and same['importId']==first['importId']
        assert len(case.repo.sources)==1
        return case.repo.source(case.repo.active_id)['record_count']
    finally:case.doCleanups()


if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group()
    group.add_argument('--source',type=Path);group.add_argument('--synthetic-records',type=int,default=223425)
    args=parser.parse_args();print(json.dumps(check(args.source,args.synthetic_records),sort_keys=True))
