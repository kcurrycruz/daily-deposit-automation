"""Complete current-import reads. No statement-specific candidate subsets."""
import json
from contextlib import closing,contextmanager
from collections import OrderedDict
import tempfile
import threading
import time
from ...models import integer, validate_record
from .contracts import DuplicateError, validate_pin,canonical_hash,MAX_BYTES
from ..contracts import validate_manifest
from .preparation import Unpack,connect,stamp,bounded


class DuplicateSource:
    def __init__(self, base_repository, bill_operations,prepared=None):
        self.base, self.ops = base_repository, bill_operations
        self.prepared=prepared

    def prepare(self,pin,authorization,deadline):
        self._check(pin,authorization)
        if pin['storageFormat']!='snapshot-v2' or self.prepared is None:return True
        source=self.ops.repository.source(pin['importId'])
        ready=self.prepared.prepare(pin,source['snapshot_manifest'],authorization,self.ops._check,deadline)
        self._check(pin,authorization);return ready

    @contextmanager
    def _index(self,pin,authorization):
        if self.prepared is None:
            with self.ops._index(pin['importId'],authorization) as (index,_):yield index.db
        else:
            with self.prepared.acquire(pin,authorization,self.ops._check) as db:yield db

    def pin(self, authorization):
        self.ops._check(authorization)
        current = self.ops.repository.current()
        if not current['active_import_id']:
            return None
        source = self.ops.repository.source(current['active_import_id'])
        if source['state'] != 'ready':
            raise DuplicateError('duplicate_invalid_source')
        return validate_pin(dict(importId=source['id'], importVersion=current['import_version'],
                                 sourceDigest=source['file_hash'], storageFormat=source.get('storage_format', 'rows-v1'),
                                 recordCount=source['record_count']))

    def _check(self, pin, authorization):
        validate_pin(pin)
        if self.pin(authorization) != pin:
            raise DuplicateError('duplicate_conflict')

    def read_page(self, pin, after, limit, authorization):
        self._check(pin, authorization)
        integer(after, minimum=-1, maximum=pin['recordCount'] - 1)
        integer(limit, minimum=1, maximum=5000)
        if pin['storageFormat'] == 'snapshot-v2':
            with self._index(pin,authorization) as db:
                rows = [(n, validate_record(json.loads(raw))) for n, raw in db.execute(
                    'select ordinal,record from bill_records where ordinal>? order by ordinal limit ?', (after, limit))]
        else:
            limit = min(limit, 500)
            page = self.base.records_page(self.base.config.workspace_id, pin['importId'], after, limit)
            expected_last = min(after + limit, pin['recordCount'] - 1)
            expected_cursor = expected_last if expected_last < pin['recordCount'] - 1 else None
            if page['recordCount'] != pin['recordCount'] or page['importId'] != pin['importId'] or page['nextCursor'] != expected_cursor:
                raise DuplicateError('duplicate_invalid_source')
            rows = []
            for at, raw in enumerate(page['records'], after + 1):
                if raw.get('id') != f'{pin["importId"]}:{at}':
                    raise DuplicateError('duplicate_invalid_source')
                rows.append((at, validate_record(raw)))
        expected = min(limit, pin['recordCount'] - after - 1)
        if len(rows) != expected or any(n != after + i + 1 for i, (n, _) in enumerate(rows)):
            raise DuplicateError('duplicate_invalid_source')
        self._check(pin, authorization)
        last = rows[-1][0] if rows else after
        return dict(records=[dict(ordinal=n, bill=b) for n, b in rows], total=pin['recordCount'],
                    nextOrdinal=last if last + 1 < pin['recordCount'] else None)

    def members(self, pin, ordinals, authorization):
        self._check(pin, authorization)
        if type(ordinals) is not list or not 1 <= len(ordinals) <= 100 or len(set(ordinals)) != len(ordinals):
            raise DuplicateError('duplicate_invalid_source')
        for n in ordinals:
            integer(n, minimum=0, maximum=pin['recordCount'] - 1)
        if pin['storageFormat'] == 'snapshot-v2':
            with self._index(pin,authorization) as db:
                found = dict(db.execute('select ordinal,record from bill_records where ordinal in (' +
                             ','.join('?' for _ in ordinals) + ')', ordinals))
            if len(found) != len(ordinals):
                raise DuplicateError('duplicate_invalid_source')
            output = [dict(ordinal=n, bill={**validate_record(json.loads(found[n])), 'id': f'{pin["importId"]}:{n}'}) for n in ordinals]
        else:
            output = [self.read_page(pin, n - 1, 1, authorization)['records'][0] for n in ordinals]
        self._check(pin, authorization)
        return output


class SourcePreparationCache:
    """Hash-verified immutable source copies; complete ordinal reads validate rows.

    No full quick_check on every source page. A corrupt used B-tree fails its
    bounded read; missing or invalid records fail the complete source scan.
    """
    def __init__(self,base):
        self.base=base;self.root=tempfile.TemporaryDirectory(prefix='hwfc-duplicate-source-')
        self.entries=OrderedDict();self.lock=threading.RLock()

    def _key(self,pin):return canonical_hash([pin['importId'],pin['sourceDigest']])

    def prepare(self,pin,manifest,auth,authorize,deadline):
        authorize(auth);manifest=validate_manifest(manifest);key=self._key(pin)
        if manifest['originalHash']!=pin['sourceDigest'] or manifest['recordCount']!=pin['recordCount']:
            raise DuplicateError('duplicate_invalid_source')
        with self.lock:
            now=time.monotonic()
            for old,item in list(self.entries.items()):
                if now-item['last']>=3600:item['unpack'].close();del self.entries[old]
            if key in self.entries and self.entries[key]['ready']:
                item=self.entries[key]
                if stamp(item['unpack'].path)!=item['stamp']:raise DuplicateError('duplicate_invalid_source')
                item['last']=now;authorize(auth);return True
            if now>=deadline:return False
            if key not in self.entries:
                for old,item in list(self.entries.items()):
                    if sum(i['size'] for i in self.entries.values())+manifest['indexArchive']['expandedBytes']<=MAX_BYTES:break
                    item['unpack'].close();del self.entries[old]
                if sum(i['size'] for i in self.entries.values())+manifest['indexArchive']['expandedBytes']>MAX_BYTES:
                    raise DuplicateError('duplicate_limit')
                unpack=Unpack(self.root.name,lambda p:self.base.read_artifact(manifest,'index',p),manifest['indexArchive'])
                self.entries[key]=dict(unpack=unpack,ready=False,last=now,size=manifest['indexArchive']['expandedBytes'])
            item=self.entries[key];unpack=item['unpack']
            try:
                if not unpack.step(deadline):authorize(auth);return False
                if time.monotonic()>=deadline:authorize(auth);return False
                with closing(connect(unpack.path)) as db:
                    if db.execute('pragma user_version').fetchone()[0]!=1:raise DuplicateError('duplicate_invalid_source')
                    schema=db.execute("select type,name from sqlite_master where name not like 'sqlite_%'").fetchall()
                    if {name for kind,name in schema if kind=='table'}!={'bill_meta','bill_records','bill_vendors','bill_warnings'} or any(kind in ('view','trigger') for kind,_ in schema):
                        raise DuplicateError('duplicate_invalid_source')
                    meta={k:json.loads(v) for k,v in db.execute('select key,value from bill_meta')}
                    if meta['counts']['recordCount']!=pin['recordCount'] or meta['vendorDigest']!=manifest['vendorDigest']:
                        raise DuplicateError('duplicate_invalid_source')
                authorize(auth);item.update(ready=True,stamp=stamp(unpack.path),last=time.monotonic());return True
            except Exception:
                unpack.close();del self.entries[key];raise

    @contextmanager
    def acquire(self,pin,auth,authorize):
        authorize(auth)
        with self.lock:
            item=self.entries.get(self._key(pin))
            if not item or not item['ready']:raise DuplicateError('duplicate_conflict')
            if stamp(item['unpack'].path)!=item['stamp']:raise DuplicateError('duplicate_invalid_source')
            with closing(connect(item['unpack'].path)) as db:
                bounded(db,time.monotonic()+5)
                yield db;authorize(auth)
            item['last']=time.monotonic()

    def close(self):
        with self.lock:
            for item in self.entries.values():item['unpack'].close()
            self.entries.clear();self.root.cleanup()
