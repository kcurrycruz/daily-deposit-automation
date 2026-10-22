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
from .contracts import (DuplicateError, RULE_VERSION, MAX_BYTES, MAX_ARCHIVE_BYTES,
                        canonical_hash, validate_manifest, validate_pin)

SCHEMA = {
    'findings': 'id integer primary key,key text unique,classification text,strength text,reasons text,latest_date text,member_count integer,preview text,search text',
    'members': 'finding_id integer,ordinal integer,fp text,primary key(finding_id,ordinal)',
    'scan_meta': 'key text primary key,value text not null',
}


class DuplicateArtifactWriter:
    def __init__(self, source_path, target_path):
        self.source_path, self.target = Path(source_path), Path(target_path)
        self.final = self.target.with_suffix('.sqlite')
        self.source = sqlite3.connect(self.source_path.resolve().as_uri() + '?mode=ro', uri=True)
        self.source.execute('pragma query_only=ON')
        self.db = sqlite3.connect(self.final)
        self.db.execute('pragma cache_size=-8192')
        for name, definition in SCHEMA.items():
            self.db.execute('create table ' + name + '(' + definition + ')')
        self.tables, self.table, self.after = list(SCHEMA), 0, -1
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
            rows = self.source.execute('select rowid,* from ' + name + ' where rowid>? order by rowid limit 5000', (self.after,)).fetchall()
            if rows:
                marks = ','.join('?' for _ in rows[0][1:])
                self.db.executemany('insert into ' + name + ' values(' + marks + ')', (r[1:] for r in rows))
                self.after = rows[-1][0]
            else:
                self.table += 1; self.after = -1
            self.db.commit(); self._bounded()
            if self.table == len(self.tables):
                self.db.executescript('create index finding_order on findings(strength desc,latest_date desc,key);pragma user_version=1;')
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
                    self.info = dict(format='bill-duplicates-v1', ruleVersion=RULE_VERSION,
                        sourceDigest=meta['pin']['sourceDigest'], importId=meta['pin']['importId'],
                        hash=hashlib.sha256(data).hexdigest(), bytes=len(data),
                        expandedHash=self.expanded_hash.hexdigest(), expandedBytes=self.final.stat().st_size,
                        findingCount=meta['counts']['findingCount'], recordCount=meta['counts']['recordCount'])
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

    def _open(self, path, manifest):
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('pragma query_only=ON'); db.execute('pragma trusted_schema=OFF'); db.execute('pragma cache_size=-8192')
            if hasattr(db, 'enable_load_extension'):
                db.enable_load_extension(False)
            if db.execute('pragma user_version').fetchone()[0] != 1 or db.execute('pragma quick_check').fetchone()[0] != 'ok':
                raise DuplicateError('duplicate_invalid_source')
            tables = {r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
            if tables != set(SCHEMA):
                raise DuplicateError('duplicate_invalid_source')
            if db.execute("select 1 from sqlite_master where type in ('view','trigger') limit 1").fetchone():
                raise DuplicateError('duplicate_invalid_source')
            columns = {'findings': 'id key classification strength reasons latest_date member_count preview search',
                       'members': 'finding_id ordinal fp', 'scan_meta': 'key value'}
            for table, names in columns.items():
                if [r[1] for r in db.execute('pragma table_info(' + table + ')')] != names.split():
                    raise DuplicateError('duplicate_invalid_source')
            meta = {k: json.loads(v) for k, v in db.execute('select key,value from scan_meta')}
            pin = validate_pin(meta['pin']); counts = meta['counts']
            if pin['importId'] != manifest['importId'] or pin['sourceDigest'] != manifest['sourceDigest'] or counts['recordCount'] != manifest['recordCount'] or counts['findingCount'] != manifest['findingCount']:
                raise DuplicateError('duplicate_invalid_source')
            if db.execute('select count(*) from findings').fetchone()[0] != manifest['findingCount']:
                raise DuplicateError('duplicate_invalid_source')
            if db.execute('select 1 from findings where key is null or member_count<2 limit 1').fetchone():
                raise DuplicateError('duplicate_invalid_source')
            if db.execute('select 1 from members m left join findings f on f.id=m.finding_id where f.id is null or m.ordinal<0 or m.ordinal>=? limit 1', (manifest['recordCount'],)).fetchone():
                raise DuplicateError('duplicate_invalid_source')
            if db.execute('select 1 from findings f where f.member_count<>(select count(*) from members m where m.finding_id=f.id) limit 1').fetchone():
                raise DuplicateError('duplicate_invalid_source')
            return db
        except Exception:
            db.close(); raise

    @contextmanager
    def acquire(self, workspace_id, scan_id, manifest, authorization, authorize):
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
                    self.entries[key] = dict(directory=directory, path=target, size=size, refs=0, last=self.clock())
                except Exception:
                    directory.cleanup(); raise
            entry = self.entries[key]
            entry['refs'] += 1; self.entries.move_to_end(key)
        try:
            authorize(authorization)
            db = self._open(entry['path'], manifest)
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
            for key in list(self.entries):
                self._remove(key)
            if not self.entries:
                self.root.cleanup()
