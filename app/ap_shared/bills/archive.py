"""Bounded compressed artifacts and authorized, read-only index caching."""
from collections import OrderedDict
from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import zlib
from .contracts import (MAX_SOURCE_BYTES, MAX_ARCHIVE_BYTES, MAX_INDEX_BYTES, LEASE_SECONDS,
                        SnapshotError, canonical_hash, validate_manifest)
from ..models import require_uuid, integer


def _unpack(source, target, limit):
    compressed = hashlib.sha256()
    expanded = hashlib.sha256()
    packed_count = raw_count = 0
    try:
        with tempfile.TemporaryFile(dir=Path(target).parent) as spool:
            while chunk := source.read(256 * 1024):
                packed_count += len(chunk)
                if packed_count > MAX_ARCHIVE_BYTES:
                    raise SnapshotError('bill_limit')
                compressed.update(chunk)
                spool.write(chunk)
            spool.seek(0)
            with gzip.GzipFile(fileobj=spool, mode='rb') as archive, open(target, 'wb') as output:
                while chunk := archive.read(256 * 1024):
                    raw_count += len(chunk)
                    if raw_count > limit:
                        raise SnapshotError('bill_limit')
                    expanded.update(chunk)
                    output.write(chunk)
            if not raw_count:
                raise SnapshotError('bill_invalid_archive')
        return dict(originalHash=expanded.hexdigest(), originalBytes=raw_count,
                    archiveHash=compressed.hexdigest(), archiveBytes=packed_count)
    except (OSError, EOFError, zlib.error):
        raise SnapshotError('bill_invalid_archive') from None


def verify_csv_archive(source, target):
    return _unpack(source, target, MAX_SOURCE_BYTES)


class _HashWriter:
    def __init__(self, output):
        self.output, self.hash, self.bytes = output, hashlib.sha256(), 0

    def write(self, data):
        if self.bytes + len(data) > MAX_ARCHIVE_BYTES:
            raise SnapshotError('bill_limit')
        written = self.output.write(data)
        self.hash.update(data[:written]); self.bytes += written
        return written

    def flush(self):
        self.output.flush()


class IndexArchiveWriter:
    def __init__(self, index_path, output_path):
        self.input = open(index_path, 'rb')
        self.output = open(output_path, 'wb')
        self.writer = _HashWriter(self.output)
        self.gzip = gzip.GzipFile(filename='', mode='wb', fileobj=self.writer, mtime=0)
        self.raw_hash, self.raw_bytes = hashlib.sha256(), 0
        self.artifact = None
        self.closed = False

    def step(self, max_bytes=4 * 1024 * 1024, deadline=float('inf')):
        integer(max_bytes, minimum=1, maximum=4 * 1024 * 1024)
        if self.artifact:
            return dict(done=True, artifact=dict(self.artifact))
        if self.closed:
            raise SnapshotError('bill_restart')
        consumed = 0
        while consumed < max_bytes and time.monotonic() < deadline:
            raw = self.input.read(min(256 * 1024, max_bytes - consumed))
            if not raw:
                self.gzip.close(); self.output.flush()
                self.artifact = dict(hash=self.writer.hash.hexdigest(), bytes=self.writer.bytes,
                                     expandedHash=self.raw_hash.hexdigest(), expandedBytes=self.raw_bytes)
                self.close()
                return dict(done=True, artifact=dict(self.artifact))
            self.raw_bytes += len(raw); consumed += len(raw)
            if self.raw_bytes > MAX_INDEX_BYTES:
                raise SnapshotError('bill_limit')
            self.raw_hash.update(raw); self.gzip.write(raw)
        return dict(done=False, artifact=None)

    def close(self):
        if not self.closed:
            try:
                self.gzip.close()
            finally:
                self.input.close(); self.output.close(); self.closed = True


class SnapshotCache:
    def __init__(self, repository, clock=time.monotonic):
        self.repository, self.clock = repository, clock
        self.budget = MAX_INDEX_BYTES
        self.entries = OrderedDict()
        self.lock = threading.RLock()
        self.root = tempfile.TemporaryDirectory(prefix='hwfc-bill-cache-')
        self.closed = False

    def _remove(self, key):
        entry = self.entries[key]
        if entry['refs']:
            return False
        # Only a TemporaryDirectory we created below this owned cache root is removed.
        Path(entry['directory'].name).resolve().relative_to(Path(self.root.name).resolve())
        entry['directory'].cleanup()
        del self.entries[key]
        return True

    @contextmanager
    def acquire(self, workspace_id, import_id, manifest, authorization, authorize):
        authorize(authorization)
        require_uuid(workspace_id); require_uuid(import_id)
        manifest = validate_manifest(manifest)
        if not manifest['indexArchive']['key'].startswith(workspace_id + '/'):
            raise PermissionError('AP workspace access denied.')
        key = (workspace_id, import_id, canonical_hash(manifest))
        with self.lock:
            if self.closed:
                raise SnapshotError('bill_incomplete')
            for old, entry in list(self.entries.items()):
                if self.clock() - entry['last'] >= LEASE_SECONDS:
                    self._remove(old)
            if key not in self.entries:
                size = manifest['indexArchive']['expandedBytes']
                for old in list(self.entries):
                    if sum(e['size'] for e in self.entries.values()) + size <= self.budget:
                        break
                    self._remove(old)
                if sum(e['size'] for e in self.entries.values()) + size > self.budget:
                    raise SnapshotError('bill_limit')
                directory = tempfile.TemporaryDirectory(prefix='index-', dir=self.root.name)
                try:
                    packed = Path(directory.name) / 'archive.gz'
                    target = Path(directory.name) / 'index.sqlite'
                    self.repository.read_artifact(manifest, 'index', packed)
                    with open(packed, 'rb') as source:
                        result = _unpack(source, target, MAX_INDEX_BYTES)
                    expected = manifest['indexArchive']
                    if any(result[left] != expected[right] for left, right in [('archiveHash', 'hash'), ('archiveBytes', 'bytes'), ('originalHash', 'expandedHash'), ('originalBytes', 'expandedBytes')]):
                        raise SnapshotError('bill_invalid_archive')
                    authorize(authorization)
                    self.entries[key] = dict(directory=directory, path=target, size=size, refs=0, last=self.clock())
                except Exception:
                    directory.cleanup()
                    raise
            entry = self.entries[key]
            entry['refs'] += 1
            self.entries.move_to_end(key)
        connection = None
        try:
            authorize(authorization)
            connection = sqlite3.connect(entry['path'].as_uri() + '?mode=ro', uri=True)
            connection.execute('pragma query_only=ON')
            connection.execute('pragma trusted_schema=OFF')
            connection.execute('pragma cache_size=-8192')
            if hasattr(connection, 'enable_load_extension'):
                connection.enable_load_extension(False)
            if connection.execute('pragma user_version').fetchone()[0] != 1 or connection.execute('pragma quick_check').fetchone()[0] != 'ok':
                raise SnapshotError('bill_invalid_archive')
            tables = {r[0] for r in connection.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
            if tables != {'bill_meta', 'bill_records', 'bill_vendors', 'bill_warnings'}:
                raise SnapshotError('bill_invalid_archive')
            meta = {k: json.loads(v) for k, v in connection.execute('select key,value from bill_meta')}
            if meta['counts']['recordCount'] != manifest['recordCount'] or meta['vendorDigest'] != manifest['vendorDigest']:
                raise SnapshotError('bill_invalid_archive')
            yield connection
            authorize(authorization)
        except (sqlite3.DatabaseError, KeyError, json.JSONDecodeError):
            raise SnapshotError('bill_invalid_archive') from None
        finally:
            if connection:
                connection.close()
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
