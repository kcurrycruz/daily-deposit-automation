"""Fresh compact result artifacts and private, verified read-only caches."""
from collections import OrderedDict
from contextlib import closing, contextmanager
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from .contracts import (DuplicateError, RULE_VERSION, ARTIFACT_FORMAT,MAX_BYTES, MAX_ARCHIVE_BYTES,
                        canonical_hash, validate_manifest, validate_pin,validate_finding_evidence,
                        WORKING_RULE_VERSION,WORKING_ARTIFACT_FORMAT,WORKING_PIN_FIELDS,rule_for_pin)
from .preparation import Unpack,connect,bounded,stamp

SCHEMA = {
    'findings': 'id integer primary key,key text unique,classification text,strength text,reasons text,latest_date text,member_count integer,preview text,search text,evidence text not null',
    'members': 'finding_id integer,ordinal integer,fp text,primary key(finding_id,ordinal)',
    'scan_meta': 'key text primary key,value text not null',
}
WORKING_SCHEMA={**SCHEMA,'source_map':'ordinal integer primary key,source_ordinal integer unique,fp text not null'}


def _mapping_add(hasher,ordinal,original,fp,total):
    if type(original) is not int or not 0<=original<total:raise DuplicateError('duplicate_invalid_source')
    try:hasher.add(ordinal,original,fp)
    except ValueError:raise DuplicateError('duplicate_invalid_source') from None


def _member_mapping_valid(db):
    return not db.execute('select 1 from members m left join source_map s on s.ordinal=m.ordinal where s.ordinal is null or s.fp<>m.fp limit 1').fetchone()


def _finding_evidence(db,ident,kind,raw,previews,count):
    members=None
    if kind in ('reference_entry_issue','possible_wrong_vendor'):
        members=[n for n, in db.execute('select ordinal from members where finding_id=? order by ordinal limit 3',(ident,))]
    return validate_finding_evidence(json.loads(raw),kind,json.loads(previews),count,members)


class DuplicateArtifactWriter:
    def __init__(self, source_path, target_path):
        self.source_path, self.target = Path(source_path), Path(target_path)
        self.final = self.target.with_suffix('.sqlite')
        # The registry lock serializes step/close, but Streamlit can run each
        # cooperative request on a different script thread.
        self.source = sqlite3.connect(self.source_path.resolve().as_uri() + '?mode=ro', uri=True, check_same_thread=False)
        self.source.execute('pragma query_only=ON')
        self.pin=validate_pin(json.loads(self.source.execute("select value from scan_meta where key='pin'").fetchone()[0]))
        self.working=self.pin['storageFormat']=='working-v1';self.schema=WORKING_SCHEMA if self.working else SCHEMA
        self.mapping=None
        if self.working:
            from ..working.contracts import MappingDigest
            self.mapping=MappingDigest()
        self.db = sqlite3.connect(self.final, check_same_thread=False)
        self.db.execute('pragma cache_size=-8192')
        self.db.execute('pragma journal_mode=MEMORY');self.db.execute('pragma synchronous=OFF')
        for name, definition in self.schema.items():
            self.db.execute('create table ' + name + '(' + definition + ')')
        self.db.execute('create index finding_order on findings(strength desc,latest_date desc,key)')
        self.tables, self.table, self.after = list(self.schema), 0, -1
        self.phase, self.done, self.info = 'copy', False, None
        self.input = self.output = self.compressor = None
        self.expanded_hash = hashlib.sha256()

    def _bounded(self):
        if self.final.stat().st_size > MAX_BYTES:
            raise DuplicateError('duplicate_limit')

    def step(self, max_bytes=4194304, deadline=None):
        if self.done:
            return dict(done=True, artifact=self.info)
        deadline = deadline if deadline is not None else time.monotonic() + 5
        if self.phase == 'copy' and time.monotonic() < deadline:
            name = self.tables[self.table]
            rows = self.source.execute('select rowid,* from ' + name + ' where rowid>? order by rowid limit 250', (self.after,)).fetchall()
            if rows:
                marks = ','.join('?' for _ in rows[0][1:])
                for row in rows:
                    if time.monotonic()>=deadline:break
                    if name=='findings':_finding_evidence(self.source,row[1],row[3],row[10],row[8],row[7])
                    if name=='source_map':_mapping_add(self.mapping,row[1],row[2],row[3],self.pin['fullRecordCount'])
                    self.db.execute('insert into '+name+' values('+marks+')',row[1:]);self.after=row[0]
            else:
                self.table += 1; self.after = -1
            self.db.commit(); self._bounded()
            if self.table == len(self.tables):
                if self.working and (self.mapping.count!=self.pin['recordCount'] or self.mapping.hexdigest()!=self.pin['mappingDigest'] or not _member_mapping_valid(self.db)):
                    raise DuplicateError('duplicate_invalid_source')
                self.db.execute('pragma user_version='+('3' if self.working else '2'))
                self.db.commit(); self.db.close(); self.db = None; self.source.close(); self.source = None
                self._bounded()
                self.input = open(self.final, 'rb'); self.output = open(self.target, 'wb')
                self.compressor = gzip.GzipFile(filename='', fileobj=self.output, mode='wb', mtime=0)
                self.phase = 'pack'
        if self.phase == 'pack':
            processed = 0
            while processed < max_bytes and time.monotonic() < deadline:
                chunk = self.input.read(min(65536, max_bytes - processed))
                if not chunk:
                    self.compressor.close(); self.compressor = None; self.output.close(); self.output = None
                    self.input.close(); self.input = None
                    data = self.target.read_bytes()
                    if not data or len(data) > MAX_ARCHIVE_BYTES:
                        raise DuplicateError('duplicate_limit')
                    with closing(sqlite3.connect(self.final.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                        meta = {k: json.loads(v) for k, v in db.execute('select key,value from scan_meta')}
                    self.info = dict(format=WORKING_ARTIFACT_FORMAT if self.working else ARTIFACT_FORMAT, ruleVersion=rule_for_pin(meta['pin']),
                        sourceDigest=meta['pin']['sourceDigest'], importId=meta['pin']['importId'],
                        hash=hashlib.sha256(data).hexdigest(), bytes=len(data),
                        expandedHash=self.expanded_hash.hexdigest(), expandedBytes=self.final.stat().st_size,
                        findingCount=meta['counts']['findingCount'], recordCount=meta['counts']['recordCount'])
                    if self.working:self.info.update({k:meta['pin'][k] for k in WORKING_PIN_FIELDS.split()})
                    self.done = True
                    break
                self.expanded_hash.update(chunk); self.compressor.write(chunk); processed += len(chunk)
                if self.output.tell() > MAX_ARCHIVE_BYTES:
                    raise DuplicateError('duplicate_limit')
        return dict(done=self.done, artifact=self.info)

    def close(self):
        for name in ('compressor', 'output', 'input', 'db', 'source'):
            handle = getattr(self, name, None)
            if handle is not None:
                handle.close(); setattr(self, name, None)


class DuplicateArtifactCache:
    def __init__(self, repository, root=None, clock=time.monotonic):
        self.repository, self.clock = repository, clock
        self.root = tempfile.TemporaryDirectory(prefix='hwfc-duplicates-cache-', dir=root)
        self.entries = OrderedDict()
        self.pending={}
        self.lock, self.closed = threading.RLock(), False

    def _remove(self, key):
        entry = self.entries[key]
        if entry['refs'] == 0:
            entry['directory'].cleanup(); del self.entries[key]

    def _evict(self, extra):
        for key, entry in list(self.entries.items()):
            if entry['refs'] == 0 and self.clock() - entry['last'] >= 3600:
                self._remove(key)
        for key in list(self.entries):
            if sum(e['size'] for e in self.entries.values()) + extra <= MAX_BYTES:
                break
            self._remove(key)
        if sum(e['size'] for e in self.entries.values()) + extra > MAX_BYTES:
            raise DuplicateError('duplicate_limit')

    def _open(self, path, manifest, validate=True):
        db = connect(path)
        working=manifest['ruleVersion']==WORKING_RULE_VERSION
        try:
            db.execute('pragma query_only=ON'); db.execute('pragma trusted_schema=OFF'); db.execute('pragma cache_size=-8192')
            if hasattr(db, 'enable_load_extension'):
                db.enable_load_extension(False)
            if db.execute('pragma user_version').fetchone()[0] != (3 if working else 2) or validate and db.execute('pragma quick_check').fetchone()[0] != 'ok':
                raise DuplicateError('duplicate_invalid_source')
            tables = {r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
            if tables != set(WORKING_SCHEMA if working else SCHEMA):
                raise DuplicateError('duplicate_invalid_source')
            if db.execute("select 1 from sqlite_master where type in ('view','trigger') limit 1").fetchone():
                raise DuplicateError('duplicate_invalid_source')
            columns = {'findings': 'id key classification strength reasons latest_date member_count preview search evidence',
                       'members': 'finding_id ordinal fp', 'scan_meta': 'key value'}
            if working:columns['source_map']='ordinal source_ordinal fp'
            for table, names in columns.items():
                if [r[1] for r in db.execute('pragma table_info(' + table + ')')] != names.split():
                    raise DuplicateError('duplicate_invalid_source')
            meta = {k: json.loads(v) for k, v in db.execute('select key,value from scan_meta')}
            pin = validate_pin(meta['pin']); counts = meta['counts']
            if pin['importId'] != manifest['importId'] or pin['sourceDigest'] != manifest['sourceDigest'] or counts['recordCount'] != manifest['recordCount'] or counts['findingCount'] != manifest['findingCount']:
                raise DuplicateError('duplicate_invalid_source')
            if working and any(pin[k]!=manifest[k] for k in WORKING_PIN_FIELDS.split()):raise DuplicateError('duplicate_invalid_source')
            if not validate:return db
            if db.execute('select count(*) from findings').fetchone()[0] != manifest['findingCount']:
                raise DuplicateError('duplicate_invalid_source')
            if db.execute('select 1 from findings where key is null or member_count<2 limit 1').fetchone():
                raise DuplicateError('duplicate_invalid_source')
            if db.execute('select 1 from members m left join findings f on f.id=m.finding_id where f.id is null or m.ordinal<0 or m.ordinal>=? limit 1', (manifest['recordCount'],)).fetchone():
                raise DuplicateError('duplicate_invalid_source')
            if db.execute('select 1 from findings f where f.member_count<>(select count(*) from members m where m.finding_id=f.id) limit 1').fetchone():
                raise DuplicateError('duplicate_invalid_source')
            for ident,kind,raw,previews,count in db.execute('select id,classification,evidence,preview,member_count from findings'):
                _finding_evidence(db,ident,kind,raw,previews,count)
            if working:
                from ..working.contracts import MappingDigest
                mapping=MappingDigest()
                for n,original,fp in db.execute('select ordinal,source_ordinal,fp from source_map order by ordinal'):
                    _mapping_add(mapping,n,original,fp,manifest['fullRecordCount'])
                if mapping.count!=manifest['recordCount'] or mapping.hexdigest()!=manifest['mappingDigest'] or not _member_mapping_valid(db):raise DuplicateError('duplicate_invalid_source')
            return db
        except Exception:
            db.close(); raise

    @contextmanager
    def acquire(self, workspace_id, scan_id, manifest, authorization, authorize,prepared_only=False):
        authorize(authorization)
        manifest = validate_manifest(manifest)
        if workspace_id != self.repository.config.workspace_id or not manifest['key'].startswith(workspace_id + '/'):
            raise PermissionError('AP workspace access denied.')
        key = (workspace_id, scan_id, canonical_hash(manifest))
        db = None
        with self.lock:
            if self.closed:
                raise DuplicateError()
            if key not in self.entries:
                if prepared_only:raise DuplicateError('duplicate_conflict')
                self._evict(manifest['expandedBytes'])
                directory = tempfile.TemporaryDirectory(prefix='result-', dir=self.root.name)
                try:
                    compressed = Path(directory.name) / 'result.gz'
                    self.repository.read_result(manifest, compressed)
                    authorize(authorization)
                    target = Path(directory.name) / 'result.sqlite'
                    size = 0; hasher = hashlib.sha256()
                    with gzip.open(compressed, 'rb') as incoming, open(target, 'wb') as out:
                        while chunk := incoming.read(65536):
                            size += len(chunk)
                            if size > MAX_BYTES or size > manifest['expandedBytes']:
                                raise DuplicateError('duplicate_limit')
                            hasher.update(chunk); out.write(chunk)
                    if size != manifest['expandedBytes'] or hasher.hexdigest() != manifest['expandedHash']:
                        raise DuplicateError('duplicate_invalid_source')
                    checked = self._open(target, manifest); checked.close()
                    authorize(authorization)
                    self.entries[key] = dict(directory=directory, path=target, size=size, refs=0, last=self.clock(),stamp=stamp(target))
                except Exception:
                    directory.cleanup(); raise
            entry = self.entries[key]
            entry['refs'] += 1; self.entries.move_to_end(key)
        try:
            authorize(authorization)
            if stamp(entry['path'])!=entry['stamp']:raise DuplicateError('duplicate_invalid_source')
            db = connect(entry['path'])
            yield db
            authorize(authorization)
        except (sqlite3.DatabaseError, OSError, KeyError, json.JSONDecodeError):
            raise DuplicateError('duplicate_invalid_source') from None
        finally:
            if db is not None:
                db.close()
            with self.lock:
                entry['refs'] -= 1; entry['last'] = self.clock()
                if self.closed:
                    self._remove(key)
                    if not self.entries:
                        self.root.cleanup()

    def close(self):
        with self.lock:
            self.closed = True
            for pending in self.pending.values():pending['unpack'].close()
            self.pending.clear()
            for key in list(self.entries):
                self._remove(key)
            if not self.entries:
                self.root.cleanup()

    def prepare(self,workspace_id,scan_id,manifest,authorization,authorize,deadline):
        authorize(authorization);manifest=validate_manifest(manifest)
        if workspace_id!=self.repository.config.workspace_id or not manifest['key'].startswith(workspace_id+'/'):
            raise PermissionError('AP workspace access denied.')
        key=(workspace_id,scan_id,canonical_hash(manifest))
        with self.lock:
            if self.closed:raise DuplicateError()
            # Only current-source scans reach preparation through operations.
            # Partial files have no readers and are never durable evidence.
            for old,item in list(self.pending.items()):
                if old[0]==workspace_id and old!=key:
                    item['unpack'].close();del self.pending[old]
            if key in self.entries:
                if stamp(self.entries[key]['path'])!=self.entries[key]['stamp']:raise DuplicateError('duplicate_invalid_source')
                authorize(authorization);return True
            if time.monotonic()>=deadline:return False
            if key not in self.pending:
                self._evict(manifest['expandedBytes']+sum(p['size'] for p in self.pending.values()))
                unpack=Unpack(self.root.name,lambda p:self.repository.read_result(manifest,p),manifest)
                self.pending[key]=dict(unpack=unpack,size=manifest['expandedBytes'],phase='findings',after=-1,n=0,member_after=(-1,-1),group=None,mapping=None,map_after=-1)
            item=self.pending[key];unpack=item['unpack']
            try:
                if not unpack.step(deadline):authorize(authorization);return False
                if time.monotonic()>=deadline:authorize(authorization);return False
                with closing(self._open(unpack.path,manifest,validate=False)) as db:
                    bounded(db,deadline)
                    if item['phase']=='findings':
                        if db.execute('select 1 from findings where id<0 limit 1').fetchone():raise DuplicateError('duplicate_invalid_source')
                        rows=db.execute('''select f.id,f.key,f.member_count,(select count(*) from members m where m.finding_id=f.id),f.classification,f.evidence,f.preview
                            from findings f where f.id>? order by f.id limit 250''',(item['after'],)).fetchall()
                        for ident,key_text,count,actual,kind,raw,previews in rows:
                            if key_text is None or count<2 or count!=actual:raise DuplicateError('duplicate_invalid_source')
                            _finding_evidence(db,ident,kind,raw,previews,count)
                        item['n']+=len(rows)
                        if rows:item['after']=rows[-1][0]
                        else:
                            if item['n']!=manifest['findingCount']:raise DuplicateError('duplicate_invalid_source')
                            item['phase']='members'
                    elif item['phase']=='members':
                        if db.execute('select 1 from members where finding_id<0 limit 1').fetchone():raise DuplicateError('duplicate_invalid_source')
                        rows=db.execute('''select m.finding_id,m.ordinal,f.id from members m left join findings f on f.id=m.finding_id
                            where (m.finding_id,m.ordinal)>(?,?) order by m.finding_id,m.ordinal limit 5000''',item['member_after']).fetchall()
                        if any(found is None or ordinal<0 or ordinal>=manifest['recordCount'] for _,ordinal,found in rows):
                            raise DuplicateError('duplicate_invalid_source')
                        if rows:item['member_after']=rows[-1][:2]
                        else:
                            if manifest['ruleVersion']==WORKING_RULE_VERSION:
                                if not _member_mapping_valid(db):raise DuplicateError('duplicate_invalid_source')
                                from ..working.contracts import MappingDigest
                                item['phase']='mapping';item['mapping']=MappingDigest()
                                authorize(authorization);return False
                            authorize(authorization)
                            self.entries[key]=dict(directory=unpack.directory,path=unpack.path,size=unpack.size,refs=0,last=self.clock(),stamp=stamp(unpack.path))
                            del self.pending[key];return True
                    else:
                        rows=db.execute('select ordinal,source_ordinal,fp from source_map where ordinal>? order by ordinal limit 250',(item['map_after'],)).fetchall()
                        for ordinal,original,fp in rows:_mapping_add(item['mapping'],ordinal,original,fp,manifest['fullRecordCount'])
                        if rows:item['map_after']=rows[-1][0]
                        else:
                            if item['mapping'].count!=manifest['recordCount'] or item['mapping'].hexdigest()!=manifest['mappingDigest']:raise DuplicateError('duplicate_invalid_source')
                            authorize(authorization)
                            self.entries[key]=dict(directory=unpack.directory,path=unpack.path,size=unpack.size,refs=0,last=self.clock(),stamp=stamp(unpack.path))
                            del self.pending[key];return True
                authorize(authorization);return False
            except sqlite3.OperationalError as error:
                if 'interrupted' in str(error):authorize(authorization);return False
                unpack.close();del self.pending[key];raise DuplicateError('duplicate_invalid_source') from None
            except Exception:
                unpack.close();del self.pending[key];raise
