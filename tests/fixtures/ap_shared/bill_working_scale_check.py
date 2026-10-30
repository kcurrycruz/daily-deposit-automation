"""Offline active-range release measurement; never opens a network connection."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import date,datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from app.ap_shared.bills.working.builds import WorkingBuilder
from app.ap_shared.bills.working.archive import WorkingCache
from app.ap_shared.bills.working.policy import make_policy
from app.ap_shared.bills.working.protections import ProtectionSet
from app.ap_shared.bills.working.contracts import validate_working_manifest
from app.ap_shared.bills.duplicates.scan import DuplicateScan
from app.ap_shared.bills.working.context import HistoryContext
from bill_scale_check import peak_rss

I='00000000-0000-4000-8000-000000000002'
W='00000000-0000-4000-8000-000000000001'
S='00000000-0000-4000-8000-000000000003'

def file_hash(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as incoming:
        while part:=incoming.read(262144):value.update(part)
    return value.hexdigest()

def synthetic(path,records):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('pragma journal_mode=MEMORY;pragma synchronous=OFF;create table bill_records(ordinal integer primary key,record text);')
        for at in range(0,records,5000):
            rows=[]
            for n in range(at,min(at+5000,records)):
                bill=dict(vendor=f'Synthetic {n%64:02}',invoiceNumber=f'INV{n:08}',kind='invoice',invoiceDate='2025-11-01' if n%10==0 else f'2025-09-{1+n%28:02}',amount=10000+n%17,status='Open' if n%1000==1 else 'PaidInFull',reportedAmountDue=100 if n%1000==1 else 0,sourceIssues='')
                if n in (0,10):bill.update(vendor='Synthetic 00',invoiceNumber='999999' if n==0 else '999999X',amount=10000)
                rows.append((n,json.dumps(bill,separators=(',',':'))))
            db.executemany('insert into bill_records values(?,?)',rows);db.commit()

def independent_context_parity(builder):
    # Compare each required compact key with direct full-history aggregates,
    # independently of VendorPatterns caches and HistoryContext lookups.
    nodes=builder.history_db;context=builder.context_db;profiles=recurrences=0
    for vendor,month,raw in context.execute('select vendor,month,value from profiles'):
        rows=nodes.execute('select ref,min(shape) from nodes where vendor=? and day>=? and day<? and warning=0 and n=1 group by ref',(vendor,month-365,month)).fetchall()
        shapes=Counter(shape for _,shape in rows);top=sorted(((shape,n) for shape,n in shapes.items() if n>=3),key=lambda v:(-v[1],v[0]))[:3]
        expected=dict(periodStart=date.fromordinal(month-365).isoformat(),periodEnd=date.fromordinal(month-1).isoformat(),distinctReferences=len(rows),shapes=[dict(shape=s,references=n) for s,n in top],established=len(rows)>=20 and sum(n for _,n in top)*10>=len(rows)*9)
        if json.loads(raw)!=expected:raise AssertionError('Full-source historical profile differs from compact context')
        profiles+=1
    for vendor,amount,day,value in context.execute('select vendor,amount,day,value from recurrences'):
        refs,days=nodes.execute('select count(distinct ref),count(distinct day) from nodes where vendor=? and amount=? and day>=? and day<?',(vendor,amount,day-90,day)).fetchone()
        if bool(value)!=(refs>=10 and days>=6):raise AssertionError('Full-source recurrence differs from compact context')
        recurrences+=1
    return profiles,recurrences

def scan(engine,context=None):
    if context is not None:engine.vendor_candidates.patterns.context=context
    maximum=0;started=time.monotonic()
    while True:
        at=time.monotonic();p=engine.step(at+5);maximum=max(maximum,time.monotonic()-at)
        if p['done']:break
    result=engine.finish()
    return dict(seconds=time.monotonic()-started,maximum=maximum,findingCount=result['findingCount'],probes=engine.probes)

def finding_signatures(db,allowed=None):
    signatures=Counter();outside=0
    for ident,kind in db.execute('select id,classification from findings order by id'):
        members=db.execute('select ordinal,fp from members where finding_id=? order by ordinal',(ident,)).fetchall()
        if allowed is not None and any(n not in allowed for n,_ in members):outside+=1;continue
        signature=hashlib.sha256(json.dumps([kind,sorted(fp for _,fp in members)],separators=(',',':')).encode()).hexdigest()
        signatures[signature]+=1
    return signatures,outside

def check(records,mode,source_index=None,with_scan=False):
    started=time.monotonic();baseline=peak_rss();maximum=0
    with tempfile.TemporaryDirectory(prefix='hwfc-range-release-') as folder:
        root=Path(folder);path=Path(source_index) if source_index else root/'source.sqlite'
        if source_index is None:synthetic(path,records)
        original_hash=file_hash(path)
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as source:
            records=source.execute('select count(*) from bill_records').fetchone()[0]
            protections=ProtectionSet()
            source_info=dict(importId=I,sourceDigest='a'*64,recordCount=records)
            builder=WorkingBuilder(source,root/'working',source_info,make_policy(mode,datetime(2026,10,30,16,tzinfo=timezone.utc)),protections,time.monotonic)
            profile_count=recurrence_count=0;full_scan=None;full_signatures=None;validation_seconds=0;baseline_seconds=0
            try:
                build_start=time.monotonic()
                while True:
                    at=time.monotonic();p=builder.step(at+5);maximum=max(maximum,time.monotonic()-at)
                    if builder.phase=='finalizing':
                        validation_start=time.monotonic();profile_count,recurrence_count=independent_context_parity(builder);validation_seconds+=time.monotonic()-validation_start
                        if with_scan:
                            baseline_start=time.monotonic()
                            with closing(sqlite3.connect(root/'full-scan.sqlite')) as full_db:
                                full_engine=DuplicateScan(full_db,dict(importId=I,importVersion=1,sourceDigest=source_info['sourceDigest'],storageFormat='snapshot-v2',recordCount=records),time.monotonic)
                                cursor=-1
                                while True:
                                    full_rows=source.execute('select ordinal,record from bill_records where ordinal>? order by ordinal limit 5000',(cursor,)).fetchall()
                                    if not full_rows:break
                                    full_engine.ingest([dict(ordinal=n,bill=json.loads(raw)) for n,raw in full_rows]);cursor=full_rows[-1][0]
                                full_engine.finish_input();full_input_seconds=time.monotonic()-baseline_start;full_scan=scan(full_engine)
                                full_scan.update(inputSeconds=round(full_input_seconds,3),totalSeconds=round(time.monotonic()-baseline_start,3))
                                active_ordinals={n for n, in builder.db.execute('select source_ordinal from working_records')}
                                full_signatures,cross_boundary=finding_signatures(full_db,active_ordinals)
                            baseline_seconds=time.monotonic()-baseline_start
                    if p['done']:break
                built=builder.artifacts();build_seconds=time.monotonic()-build_start-validation_seconds-baseline_seconds
            finally:builder.close()
        mf={**built['summary'],'workingSetId':S}
        for name in ('index','context'):
            part=built[name+'Archive'];mf[name+'Archive']={**part,'key':f'{W}/bill-working/v1/{mf["workingDigest"]}/{part["hash"]}.sqlite.gz'}
        validate_working_manifest(mf);reads=[]
        def download(manifest,name,target):reads.append(name);Path(target).write_bytes(built[name+'ArchivePath'].read_bytes())
        cache=WorkingCache(SimpleNamespace(read_artifact=download));cold=time.monotonic()
        try:
            while True:
                at=time.monotonic();ready=cache.prepare(mf,None,lambda _:None,at+5);maximum=max(maximum,time.monotonic()-at)
                if ready:break
            cold_seconds=time.monotonic()-cold;before=len(reads);warm=time.monotonic()
            for _ in range(100):
                with cache.acquire(mf,None,lambda _:None) as (db,context):
                    db.execute('select ordinal from working_records where reference_key=? limit 10',('INV00000001',)).fetchall()
            warm_seconds=time.monotonic()-warm;active_scan=None
            if with_scan:
                pin=dict(importId=I,importVersion=1,sourceDigest=mf['workingDigest'],storageFormat='working-v1',recordCount=mf['activeCount'],workingSetId=S,workingDigest=mf['workingDigest'],workingVersion=1,fullSourceDigest=source_info['sourceDigest'],fullRecordCount=records,mappingDigest=mf['mappingDigest'])
                with closing(sqlite3.connect(root/'active-scan.sqlite')) as db,cache.acquire(mf,None,lambda _:None) as (active,context):
                    active_started=time.monotonic();engine=DuplicateScan(db,pin,time.monotonic);after=-1
                    while True:
                        rows=active.execute('select ordinal,source_ordinal,record from working_records where ordinal>? order by ordinal limit 5000',(after,)).fetchall()
                        if not rows:break
                        engine.ingest([dict(ordinal=n,sourceOrdinal=original,bill=json.loads(raw)) for n,original,raw in rows]);after=rows[-1][0]
                    engine.finish_input();active_input_seconds=time.monotonic()-active_started;active_scan=scan(engine,context)
                    active_scan.update(inputSeconds=round(active_input_seconds,3),totalSeconds=round(time.monotonic()-active_started,3))
                    active_signatures,_=finding_signatures(db)
                    if active_signatures!=full_signatures:raise AssertionError('Active findings differ from fully-active full-source findings: missing='+str(sum((full_signatures-active_signatures).values()))+', additional='+str(sum((active_signatures-full_signatures).values())))
                    active_scan.update(activePairParity=True,fullyActiveBaselineFindings=sum(full_signatures.values()),outsideActiveBaselineFindings=cross_boundary)
            return dict(fullRecordCount=records,activeCount=mf['activeCount'],archivedCount=mf['archivedCount'],retainedReasonCounts=mf['retainedReasonCounts'],mode=mode,cutoffDate=mf['policy']['cutoffDate'],sourceUnchanged=file_hash(path)==original_hash,contextParity=True,independentValidationSeconds=round(validation_seconds,3),indexFileSha256=original_hash,profilesChecked=profile_count,recurrencesChecked=recurrence_count,buildSeconds=round(build_seconds,3),coldCacheSeconds=round(cold_seconds,3),warm100ReadsSeconds=round(warm_seconds,4),warmReadsWithoutDownload=len(reads)==before,indexExpandedBytes=mf['indexArchive']['expandedBytes'],contextExpandedBytes=mf['contextArchive']['expandedBytes'],indexCompressedBytes=mf['indexArchive']['bytes'],contextCompressedBytes=mf['contextArchive']['bytes'],maxStepSeconds=round(maximum,4),peakRssIncreaseBytes=peak_rss()-baseline,totalSeconds=round(time.monotonic()-started,3),fullScan=full_scan,activeScan=active_scan)
        finally:cache.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--records',type=int,default=223425);p.add_argument('--mode',choices=['all','last_12_months'],default='last_12_months');p.add_argument('--source-index');p.add_argument('--scan',action='store_true');args=p.parse_args()
    print(json.dumps(check(args.records,args.mode,args.source_index,args.scan),sort_keys=True))
