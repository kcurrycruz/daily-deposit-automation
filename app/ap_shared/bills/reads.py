"""Shared read-only source queries. Authorization is supplied by the caller."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from app.ap_mail.contracts import SourcePin, MailError, payload_digest, bounded_text
from ..models import RULE_VERSION, validate_record, integer
from .archive import SnapshotCache
from .contracts import SnapshotError, canonical_hash, validate_query, encode_cursor, decode_cursor, RESPONSE_BYTES
from .index import SnapshotIndex
from .normalization import vendor_key, invoice_key
from .parser import encoded
from .working.archive import WorkingCache
from .working.contracts import validate_working_manifest
from .working.queries import WorkingQueries


class LegacyReadCache:
    def __init__(self):self.directory=None;self.db=None;self.key=None
    def close(self):
        if self.db:self.db.close();self.db=None
        if self.directory:self.directory.cleanup();self.directory=None
        self.key=None

    def prepare(self, repository, source, context, authorize):
        key=(source['id'],source['file_hash'],source['record_count'])
        authorize(context)
        if self.key==key:return self.db
        self.close();self.directory=tempfile.TemporaryDirectory(prefix='ap-bill-read-')
        db=self.db=sqlite3.connect(Path(self.directory.name)/'index.sqlite')
        try:
            integer(source['record_count'],minimum=1,maximum=100000)
            db.executescript('create table bill_records(ordinal integer primary key,vendor_key text,reference_key text,kind text,amount integer,record text);create table bill_vendors(vendor_key text primary key,vendor text,ordinal integer);create table bill_warnings(id integer primary key,source_rows text,reason text);')
            after=-1
            while True:
                authorize(context)
                page=repository.base.records_page(repository.config.workspace_id,source['id'],after,500)
                if page.get('recordCount')!=source['record_count'] or page.get('importId')!=source['id']:raise SnapshotError('bill_incomplete')
                for raw in page['records']:
                    after+=1;record=validate_record(raw)
                    if record['id']!=f'{source["id"]}:{after}' or after>=source['record_count']:raise SnapshotError('bill_incomplete')
                    db.execute('insert into bill_records values(?,?,?,?,?,?)',(after,vendor_key(record['vendor']),invoice_key(record['invoiceNumber']),record.get('kind','invoice'),record['amount'],encoded(record)))
                    db.execute('insert or replace into bill_vendors values(?,?,?)',(vendor_key(record['vendor']),record['vendor'],after))
                if page['nextCursor'] is None:break
                if not page['records'] or page['nextCursor']!=after:raise SnapshotError('bill_incomplete')
            if after+1!=source['record_count']:raise SnapshotError('bill_incomplete')
            db.executescript('create index bill_reference on bill_records(reference_key,kind);create index bill_vendor_amount on bill_records(vendor_key,kind,amount);')
            db.commit();db.execute('pragma query_only=ON');db.execute('pragma trusted_schema=OFF')
            authorize(context);self.key=key;return db
        except Exception:self.close();raise


@contextmanager
def open_source_index(repository, config, cache, import_id, context, authorize, legacy_cache=None):
    """Same source validation for interactive sessions and an explicit machine grant."""
    authorize(context);source=repository.source(import_id)
    if source['id']!=import_id or source['state']!='ready':raise SnapshotError('bill_incomplete')
    if source.get('storage_format','rows-v1')=='snapshot-v2':
        if source['snapshot_manifest']['originalHash']!=source['file_hash'] or source['snapshot_manifest']['recordCount']!=source['record_count']:raise SnapshotError('bill_invalid_archive')
        with cache.acquire(config.workspace_id,import_id,source['snapshot_manifest'],context,authorize) as db:
            yield SnapshotIndex(db,build=False),source
        return
    own=legacy_cache is None;legacy_cache=legacy_cache or LegacyReadCache()
    try:
        db=legacy_cache.prepare(repository,source,context,authorize)
        yield SnapshotIndex(db,build=False),source
        authorize(context)
    finally:
        if own:legacy_cache.close()


class ReadCaches:
    """One active full-source/working-set pair; no per-attachment archive reload."""
    def __init__(self, repository):self.repo=repository;self.key=None;self._new()
    def _new(self):
        self.snapshot=SnapshotCache(self.repo.snapshot);self.working=WorkingCache(self.repo.working);self.legacy=LegacyReadCache()
    def bind(self, pin):
        key=(pin.import_id,pin.source_digest,pin.working_set_id,pin.working_digest)
        if self.key is not None and self.key!=key:self.close();self._new()
        self.key=key
    def close(self):self.snapshot.close();self.working.close();self.legacy.close()


def safe_read(method):
    def wrapped(self,*args,**kwargs):
        try:return method(self,*args,**kwargs)
        except (MailError,PermissionError):raise
        except SnapshotError as error:
            if error.code=='bill_range_loading':raise
            raise MailError('stale_source' if error.code in ('bill_conflict','bill_range_refresh') else 'unavailable') from None
        except (ValueError,KeyError,TypeError,sqlite3.DatabaseError):raise MailError('unavailable') from None
    return wrapped


class BillReadAPI:
    def __init__(self, repository, authorize, caches, *, preliminary=False):
        self.repo,self.authorize,self.caches=repository,authorize,caches
        self.config=repository.config;self.repository=repository.working;self.bill_ops=self
        self._grant=object();self._context=None
        self.preliminary=preliminary

    def _check(self, grant):
        if grant is not self._grant:raise PermissionError('Read grant required.')
        self.authorize()

    @safe_read
    def pin(self):
        self.authorize();ctx=self.repo.read_context();home=ctx['home'];source=ctx['source'];working=ctx['working']
        mappings=ctx['mappings'];versions=ctx['mappingVersions']
        if type(mappings) is not dict or type(versions) is not dict or set(mappings)!=set(versions):raise MailError('unavailable')
        for name,vendor in mappings.items():bounded_text(name);bounded_text(vendor)
        active=home.get('active_import_id');set_id=home.get('active_working_set_id')
        if active is not None and (not source or source['id']!=active or source['state']!='ready'):raise MailError('stale_source')
        if set_id is not None:
            if (not working or working['workingSetId']!=set_id or working['source']['importId']!=active or
                    working['source']['sourceDigest']!=source['file_hash'] or working['source']['recordCount']!=source['record_count']):raise MailError('stale_source')
            validate_working_manifest(working)
            if not self.preliminary and home.get('working_protection_epoch')!=home.get('bill_protection_epoch'):raise MailError('stale_source')
        elif working is not None:raise MailError('stale_source')
        pin=SourcePin(active,home.get('import_version',0),source['file_hash'] if active else None,set_id,
            home.get('working_set_version',0),home.get('bill_protection_epoch',0),working['workingDigest'] if working else None,
            payload_digest({'mappings':mappings,'versions':versions}),versions,RULE_VERSION)
        self.authorize();self._context=ctx;return pin

    def assert_current(self,pin):
        if self.pin()!=pin:raise MailError('stale_source')

    def description(self,pin):
        self.assert_current(pin);source=self._context['source']
        if not pin.import_id:return None
        return dict(id=pin.import_id,record_count=source['record_count'],metadata=source['metadata'],
            created_at=source.get('created_at'),vendorDigest=source.get('snapshot_manifest',{}).get('vendorDigest'),workingSet=self._context['working'],
            rangeRefreshPending=bool(pin.working_set_id and self._context['home'].get('working_protection_epoch')!=pin.protection_epoch))

    def mappings(self,pin):self.assert_current(pin);return dict(self._context['mappings'])

    def _bind(self,pin):
        self.assert_current(pin);self.caches.bind(pin);self.cache=self.caches.working

    @contextmanager
    def _index(self,import_id,grant):
        self._check(grant)
        with open_source_index(self.repo.snapshot,self.config,self.caches.snapshot,import_id,grant,self._check,self.caches.legacy) as value:yield value

    @safe_read
    def candidates_page(self,pin,query,cursor,limit=500):
        self._bind(pin);integer(limit,minimum=1,maximum=500)
        if query.get('importId')!=pin.import_id:raise MailError('stale_source')
        if pin.working_set_id:
            result=WorkingQueries(self,allow_pending_protections=self.preliminary).candidates_page(pin.working_set_id,query,cursor,self._grant,limit)
        else:
            query=validate_query(query);query_hash=canonical_hash(query);after=decode_cursor(cursor,pin.import_id,query_hash)
            with self._index(pin.import_id,self._grant) as (index,_):result=index.candidates_page(query,after,limit,RESPONSE_BYTES-4096)
            result['importId']=pin.import_id
            result['nextCursor']=encode_cursor(pin.import_id,query_hash,result['nextCursor']) if result['nextCursor'] is not None else None
        self.assert_current(pin);return result

    @safe_read
    def vendors_page(self,pin,cursor,limit=500,include_archived=False):
        self._bind(pin);integer(limit,minimum=1,maximum=500)
        if pin.working_set_id:
            result=WorkingQueries(self,allow_pending_protections=self.preliminary).vendors_page(pin.working_set_id,cursor,self._grant,limit,include_archived)
        else:
            if include_archived:raise MailError('invalid')
            query_hash=canonical_hash(['bill_vendors_page',pin.import_id]);after=decode_cursor(cursor,pin.import_id,query_hash)
            with self._index(pin.import_id,self._grant) as (index,source):
                result=index.vendors_page(after,limit)
                if source.get('storage_format')=='snapshot-v2':result['vendorDigest']=source['snapshot_manifest']['vendorDigest']
                else:
                    hasher=hashlib.sha256(b'[')
                    for n,(vendor,) in enumerate(index.db.execute('select vendor from bill_vendors order by ordinal')):
                        if n:hasher.update(b',')
                        hasher.update(encoded({'vendor':vendor}).encode('utf-8'))
                    hasher.update(b']');result['vendorDigest']=hasher.hexdigest()
            result['importId']=pin.import_id
            result['nextCursor']=encode_cursor(pin.import_id,query_hash,result['nextCursor']) if result['nextCursor'] is not None else None
        self.assert_current(pin);return result

    @safe_read
    def archived_references_page(self,pin,references,cursor,limit=500):
        self._bind(pin)
        if not pin.working_set_id:raise MailError('invalid')
        result=WorkingQueries(self,allow_pending_protections=self.preliminary).archived_references_page(pin.import_id,references,cursor,self._grant,limit)
        self.assert_current(pin);return result
