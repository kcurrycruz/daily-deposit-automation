"""Cooperative derived indexes; full source is used only during preparation."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from ...models import validate_record
from ..archive import IndexArchiveWriter
from ..contracts import MAX_INDEX_BYTES, SnapshotError
from ..normalization import vendor_key, invoice_key
from ..parser import encoded
from .history import TrainingHistory
from ..duplicates.rules import eligible, invoice_day, bill_fingerprint
from .context import context_keys, HistoryContext
from .contracts import FORMAT, TRAINING_VERSION, validate_source, working_digest, MappingDigest
from .policy import retention_reasons, validate_policy

INDEX_SCHEMA = {
    'working_meta': 'key text primary key,value text not null',
    'working_records': 'ordinal integer primary key,source_ordinal integer unique,vendor_key text,reference_key text,kind text,amount integer,record text not null,retention_reasons text not null',
    'working_vendors': 'vendor_key text primary key,vendor text not null,ordinal integer unique',
    'archive_vendors': 'vendor_key text primary key,vendor text not null,ordinal integer unique',
    'working_warnings': 'id integer primary key,source_rows text,reason text not null',
}
CONTEXT_SCHEMA = {
    'context_meta': 'key text primary key,value text not null',
    'profiles': 'vendor text,month integer,value text not null,primary key(vendor,month)',
    'recurrences': 'vendor text,amount integer,day integer,value integer not null,primary key(vendor,amount,day)',
}


def _create(path, schema):
    db = sqlite3.connect(path, check_same_thread=False)
    db.executescript('pragma cache_size=-8192;pragma journal_mode=MEMORY;pragma synchronous=OFF;pragma max_page_count=131072;')
    for name, fields in schema.items():
        db.execute('create table '+name+'('+fields+')')
    return db


class WorkingBuilder:
    def __init__(self, source_db, output_dir, source: dict, policy: dict, protections, monotonic):
        self.source_db, self.source = source_db, validate_source(source)
        self.policy, self.protections, self.clock = validate_policy(policy), protections, monotonic
        self.output = Path(output_dir); self.output.mkdir(parents=True, exist_ok=True)
        self.identity = working_digest(self.source, self.policy, protections.digest())
        self.scratch = tempfile.TemporaryDirectory(prefix='history-', dir=self.output)
        self.index_path, self.context_path = self.output/'active.sqlite', self.output/'context.sqlite'
        self.db = self.context_db = self.history_db = None
        self.packers = {}; self.packed = {}; self.closed = False
        self.active = 0; self.reasons = Counter(); self.phase = 'reading'; self.done = False
        self.mapping=MappingDigest()
        self.after_profile = ('', 0); self.after_recurrence = ('', -1, 0)
        self.pending_profile = self.pending_recurrence = None; self.summary = None
        try:
            self.db = _create(self.index_path, INDEX_SCHEMA)
            self.context_db = _create(self.context_path, CONTEXT_SCHEMA)
            self.context_db.executescript('create table wanted_profiles(vendor text,month integer,primary key(vendor,month));create table wanted_recurrences(vendor text,amount integer,day integer,primary key(vendor,amount,day));')
            self.history_db = sqlite3.connect(Path(self.scratch.name)/'history.sqlite', check_same_thread=False)
            self.history=TrainingHistory(self.history_db,source['recordCount'],monotonic)
            self.patterns=self.history.patterns
        except Exception:
            self.close(); raise

    def _bounded(self):
        for db in (self.db, self.context_db, self.history_db):
            if db is not None and db.execute('pragma page_count').fetchone()[0]*db.execute('pragma page_size').fetchone()[0] > MAX_INDEX_BYTES:
                raise SnapshotError('bill_limit')

    def _read(self, deadline):
        processed = 0
        while processed < 5000 and self.clock() < deadline:
            after = self.history.read-1
            rows = self.source_db.execute('select ordinal,record from bill_records where ordinal>? order by ordinal limit 250', (after,)).fetchall()
            if not rows:
                if self.history.read != self.source['recordCount']:
                    raise SnapshotError('bill_incomplete')
                self.history.finish_input(); self.phase = 'profiles'; return
            if any(n != after+i+1 for i,(n,_) in enumerate(rows)):
                raise SnapshotError('bill_incomplete')
            items = [dict(ordinal=n, bill=validate_record(json.loads(raw))) for n,raw in rows]
            consumed = self.history.ingest(items, deadline=deadline)
            for item in items[:consumed]:
                n, record = item['ordinal'], item['bill']
                vendor = vendor_key(record['vendor'])
                reasons = retention_reasons(record, self.policy, protected=self.protections.protects(record))
                # A compact complete directory supports an explicit archived
                # lookup even when this vendor has no active invoices.
                for table in (('archive_vendors','working_vendors') if reasons else ('archive_vendors',)):
                    self.db.execute('insert into '+table+' values(?,?,?) on conflict(vendor_key) do update set vendor=excluded.vendor,ordinal=excluded.ordinal', (vendor, record['vendor'], n))
                if not reasons:
                    continue
                record = {**record, 'id': f'{self.source["importId"]}:{n}'}
                self.db.execute('insert into working_records values(?,?,?,?,?,?,?,?)',
                    (self.active,n,vendor,invoice_key(record['invoiceNumber']),record.get('kind','invoice'),record['amount'],encoded(record),encoded(reasons)))
                self.mapping.add(self.active,n,bill_fingerprint(record))
                self.active += 1; self.reasons.update(reasons)
                warning = record.get('sourceIssues', '')
                if 'date_unknown' in reasons:
                    warning = (warning+' Invoice date is unavailable; this older record was retained.').strip()
                if warning:
                    self.db.execute('insert into working_warnings(source_rows,reason) values(?,?)', (record.get('sourceRows',''),warning))
                day = invoice_day(record)
                if eligible(record) and day is not None:
                    profiles, recurrences = context_keys(vendor,record['amount'],day)
                    self.context_db.executemany('insert or ignore into wanted_profiles values(?,?)',profiles)
                    self.context_db.executemany('insert or ignore into wanted_recurrences values(?,?,?)',recurrences)
            self.db.commit(); self.context_db.commit(); processed += consumed
            if consumed < len(items):
                return

    def _profile(self):
        if self.pending_profile is None:
            self.pending_profile = self.context_db.execute('select vendor,month from wanted_profiles where (vendor,month)>(?,?) order by vendor,month limit 1', self.after_profile).fetchone()
            if self.pending_profile is None:
                self.phase = 'recurrences'; return
        value = self.patterns.advance(*self.pending_profile)
        if value is not None:
            self.context_db.execute('insert into profiles values(?,?,?)', (*self.pending_profile, encoded(value)))
            self.after_profile = self.pending_profile; self.pending_profile = None

    def _recurrence(self):
        if self.pending_recurrence is None:
            self.pending_recurrence = self.context_db.execute('select vendor,amount,day from wanted_recurrences where (vendor,amount,day)>(?,?,?) order by vendor,amount,day limit 1', self.after_recurrence).fetchone()
            if self.pending_recurrence is None:
                self.phase = 'finalizing'; return
        value = self.patterns.recurrence(*self.pending_recurrence)
        if value is not None:
            self.context_db.execute('insert into recurrences values(?,?,?,?)', (*self.pending_recurrence,int(value)))
            self.after_recurrence = self.pending_recurrence; self.pending_recurrence = None

    def _finalize(self):
        def directory_digest(table):
            hasher=hashlib.sha256(b'[')
            for n,(vendor,) in enumerate(self.db.execute('select vendor from '+table+' order by ordinal')):
                if n:hasher.update(b',')
                hasher.update(encoded(dict(vendor=vendor)).encode('utf8'))
            hasher.update(b']');return hasher.hexdigest()
        self.summary = dict(format=FORMAT,workingDigest=self.identity,source=self.source,policy=self.policy,
            protectionDigest=self.protections.digest(),trainingVersion=TRAINING_VERSION,
            fullRecordCount=self.source['recordCount'],activeCount=self.active,
            archivedCount=self.source['recordCount']-self.active,retainedReasonCounts=dict(self.reasons),
            vendorDigest=directory_digest('working_vendors'),archiveVendorDigest=directory_digest('archive_vendors'),mappingDigest=self.mapping.hexdigest())
        for db,table in [(self.db,'working_meta'),(self.context_db,'context_meta')]:
            db.execute('insert into '+table+' values(?,?)',('scope',encoded(self.summary)))
            db.execute('pragma user_version=1'); db.commit()
        self.db.executescript('create index working_reference on working_records(reference_key,kind,source_ordinal);create index working_amount on working_records(vendor_key,kind,amount,source_ordinal);')
        self.context_db.executescript('drop table wanted_profiles;drop table wanted_recurrences;')
        self._bounded()
        self.db.close(); self.db=None; self.context_db.close(); self.context_db=None
        self.history_db.close(); self.history_db=None
        Path(self.scratch.name).resolve().relative_to(self.output.resolve());self.scratch.cleanup();self.scratch=None
        for name,path in [('index',self.index_path),('context',self.context_path)]:
            self.packers[name]=IndexArchiveWriter(path,self.output/(name+'.gz'))
        self.phase='packaging'

    def step(self, deadline: float) -> dict:
        if self.closed:
            raise SnapshotError('bill_restart')
        if not self.done and self.clock() < deadline:
            if self.phase=='reading':self._read(deadline)
            elif self.phase in ('profiles','recurrences'):
                for _ in range(250):
                    if self.clock()>=deadline or self.phase not in ('profiles','recurrences'):break
                    self._profile() if self.phase=='profiles' else self._recurrence()
                self.context_db.commit();self.history_db.commit();self._bounded()
            elif self.phase=='finalizing':self._finalize()
            elif self.phase=='packaging':
                for name,writer in self.packers.items():
                    if name not in self.packed and self.clock()<deadline:
                        result=writer.step(deadline=deadline)
                        if result['done']:self.packed[name]=result['artifact']
                if len(self.packed)==2:self.done=True
        return dict(done=self.done,phase=self.phase,recordsRead=self.history.read,activeCount=self.active)

    def artifacts(self) -> dict:
        if not self.done:
            raise SnapshotError('bill_incomplete')
        return dict(summary=dict(self.summary),indexArchive=dict(self.packed['index']),contextArchive=dict(self.packed['context']),
                    indexArchivePath=self.output/'index.gz',contextArchivePath=self.output/'context.gz')

    def close(self):
        for writer in self.packers.values():writer.close()
        for db in (self.db,self.context_db,self.history_db):
            if db is not None:db.close()
        self.db=self.context_db=self.history_db=None
        if self.scratch is not None:
            Path(self.scratch.name).resolve().relative_to(self.output.resolve());self.scratch.cleanup();self.scratch=None
        self.closed=True
