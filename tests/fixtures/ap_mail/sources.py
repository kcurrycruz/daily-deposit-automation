"""Real synthetic CSV/index/working artifacts behind a metadata/storage boundary."""
import copy
from datetime import datetime,timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
from app.ap_shared.bills.parser import CsvStage
from app.ap_shared.bills.index import SnapshotIndex
from app.ap_shared.bills.archive import IndexArchiveWriter
from fixtures.ap_shared.bill_exports import export
from fixtures.ap_mail.store_double import W,C

I='00000000-0000-4000-8000-000000000003'
S='00000000-0000-4000-8000-000000000004'


class ReadStore:
    def __init__(self,format='snapshot-v2'):
        self.temp=tempfile.TemporaryDirectory(prefix='ap-mail-source-');self.root=Path(self.temp.name)
        self.config=SimpleNamespace(workspace_id=W,bucket='hwfc-ap-private')
        self.snapshot=self.working=self.base=self;self.reads=0;self.gap=False
        raw=export([{'Invoice #':'OLD','Invoice Date':'10/01/2024','Status':'PaidInFull','Paid Amount':'138.00','Amount Due':'0'},
                    {'Invoice #':'RECENT','Status':'PaidInFull','Paid Amount':'138.00','Amount Due':'0'}]).encode()
        path=self.root/'index.sqlite';self.db=sqlite3.connect(path)
        parser=CsvStage(self.db,io.StringIO(raw.decode()))
        while not parser.read_step()['done']:pass
        index=SnapshotIndex(self.db)
        while not index.consolidate_step()['done']:pass
        summary=index.finish();self.rows=[json.loads(r[0]) for r in self.db.execute('select record from bill_records order by ordinal')]
        sha=hashlib.sha256(raw).hexdigest();packed=gzip.compress(raw,mtime=0);csvsha=hashlib.sha256(packed).hexdigest()
        writer=IndexArchiveWriter(path,self.root/'index.gz')
        try:
            while not (step:=writer.step())['done']:pass
        finally:writer.close()
        archive={**step['artifact'],'key':f'{W}/bills/v2/{sha}/{step["artifact"]["hash"]}.sqlite.gz'}
        mf=dict(format='snapshot-v2',parserVersion='bill-csv-v1',indexVersion=1,originalHash=sha,originalBytes=len(raw),
                originalArchive=dict(key=f'{W}/bills/v2/{sha}/{csvsha}.csv.gz',hash=csvsha,bytes=len(packed)),
                indexArchive=archive,vendorDigest=summary['vendorDigest'],**summary['counts'])
        self.files={archive['key']:self.root/'index.gz'}
        self.info=dict(id=I,file_hash=sha,record_count=2,state='ready',metadata={'label':'synthetic.csv','sourceFormat':'bill-native'},
                       created_at='2026-11-03T12:00:00+00:00',storage_format=format,snapshot_manifest=mf)
        self._home=dict(active_import_id=I,import_version=1,active_working_set_id=None,working_set_version=0,
                        bill_protection_epoch=0,working_protection_epoch=0)
        self.manifest=None;self.mappings={};self.versions={}

    def close(self):self.db.close();self.temp.cleanup()
    def read_context(self):
        return copy.deepcopy(dict(home=self._home,source=self.info,working=self.manifest,mappings=self.mappings,mappingVersions=self.versions))
    def source(self,ident):return copy.deepcopy(self.info)
    def home(self):return copy.deepcopy(self._home)
    def working_set(self,ident):return {'id':S,'manifest':copy.deepcopy(self.manifest)}
    def records_page(self,workspace,ident,after,limit):
        self.reads+=1
        records=[{**r,'id':f'{ident}:{n}'} for n,r in enumerate(self.rows) if after<n<=after+limit]
        if self.gap:records=records[1:]
        return dict(records=records,recordCount=len(self.rows),importId=ident,nextCursor=None)
    def read_artifact(self,manifest,name,target):
        self.reads+=1;Path(target).write_bytes(self.files[manifest[name+'Archive']['key']].read_bytes())

    def enable_working(self):
        from app.ap_shared.bills.working.builds import WorkingBuilder
        from app.ap_shared.bills.working.policy import make_policy
        from app.ap_shared.bills.working.protections import ProtectionSet
        builder=WorkingBuilder(self.db,self.root/'working',dict(importId=I,sourceDigest=self.info['file_hash'],recordCount=2),
            make_policy('last_12_months',datetime(2026,11,4,tzinfo=timezone.utc)),ProtectionSet(),time.monotonic)
        try:
            while not builder.step(time.monotonic()+5)['done']:pass
            built=builder.artifacts()
            mf={**built['summary'],'workingSetId':S}
            for name in ('index','context'):
                artifact=built[name+'Archive'];key=f'{W}/bill-working/v1/{mf["workingDigest"]}/{artifact["hash"]}.sqlite.gz'
                mf[name+'Archive']={**artifact,'key':key};self.files[key]=Path(built[name+'ArchivePath'])
            self.manifest=mf;self._home.update(active_working_set_id=S,working_set_version=1)
        finally:builder.close()
