"""Authenticated import state machine. Financial values never enter diagnostics."""
import atexit
import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import tempfile
import threading
from uuid import UUID, uuid5
from ..access import require_access
from ..models import allowed, integer, text, date_value, require_uuid, validate_record
from .archive import verify_csv_archive, SnapshotCache
from .builds import BuildRegistry
from .contracts import (SnapshotError, MAX_ARCHIVE_BYTES, CHUNK_BYTES, RESPONSE_BYTES,
                        canonical_hash, validate_manifest, validate_query, encode_cursor, decode_cursor)
from .index import SnapshotIndex
from .normalization import vendor_key, invoice_key
from .parser import encoded
from .repository import BillRepository

_runtimes = {}
_runtime_lock = threading.RLock()


def create_bill_operations(base, config, clock, revalidate):
    repository = BillRepository(base)
    key = canonical_hash([config.supabase_url, config.workspace_id, config.bucket, config.supabase_secret_key])
    with _runtime_lock:
        if key not in _runtimes:
            builds, cache = BuildRegistry(), SnapshotCache(repository)
            atexit.register(builds.close); atexit.register(cache.close)
            _runtimes[key] = builds, cache
        builds, cache = _runtimes[key]
    return BillOperations(repository, config, clock, revalidate, builds, cache)


class BillOperations:
    def __init__(self, repository, config, clock, revalidate, builds, cache):
        self.repository, self.config, self.clock, self.revalidate = repository, config, clock, revalidate
        self.builds, self.cache = builds, cache

    def _check(self, authorization):
        current = self.revalidate()
        if current != authorization:
            raise PermissionError('AP access is locked.')
        require_access({'_ap_authorization': current, '_ap_session_nonce': current.session_nonce}, self.config, self.clock())

    def _job(self, job_id, auth):
        self._check(auth); require_uuid(job_id)
        job = self.repository.job(job_id)
        if job['workspace_id'] != self.config.workspace_id or job['session_nonce'] != auth.session_nonce:
            raise PermissionError('This BILL update belongs to another access session.')
        return job

    def _rpc(self, operation, data, request_id, auth, step):
        self._check(auth)
        return self.repository.rpc(operation, {**data, 'session_nonce': auth.session_nonce}, str(uuid5(UUID(request_id), step)))

    def _source_info(self, import_id):
        source = self.repository.source(import_id)
        if source['state'] != 'ready':
            raise SnapshotError('bill_incomplete')
        return dict(importId=source['id'], recordCount=source['record_count'],
                    storageFormat=source.get('storage_format', 'rows-v1'), metadata=source['metadata'])

    def _cleanup(self, job_id, auth):
        self._check(auth)
        try:
            self.repository.cleanup_acknowledged_chunks(job_id)
        except Exception:
            # Cleanup is optional after the immutable original is saved. Never report
            # failure as though the durable original had been lost or delete it instead.
            self._check(auth)

    def _finish_upload(self, job, request_id, auth):
        if job['state'] != 'uploading':
            result = dict(job_id=job['id'], generation=job['generation'], checkpoint=job['checkpoint'], state=job['state'])
            if job.get('import_id'):
                result.update(self._source_info(job['import_id']), duplicate=True,
                              alreadyCurrent=job['state'] == 'activated', confirmationRequired=job['state'] == 'prepared')
            return result
        paths = self.builds.paths(job['id'])
        with open(paths['archive'], 'wb') as assembled:
            for position in range((job['metadata']['compressed_size'] + CHUNK_BYTES - 1) // CHUNK_BYTES):
                self._check(auth)
                info = job['chunks'].get(str(position))
                if not info:
                    raise SnapshotError('bill_incomplete')
                raw = self.repository.read_chunk(job['id'], position, info)
                if len(raw) != info['size'] or hashlib.sha256(raw).hexdigest() != info['hash']:
                    raise SnapshotError('bill_invalid_archive')
                assembled.write(raw)
        if paths['archive'].stat().st_size != job['metadata']['compressed_size']:
            raise SnapshotError('bill_incomplete')
        with open(paths['archive'], 'rb') as packed:
            source = verify_csv_archive(packed, paths['csv'])
        self._check(auth)
        existing = self.repository.lookup_hash(source['originalHash'])
        if existing:
            if existing['state'] != 'ready':
                raise SnapshotError('bill_conflict')
            reused = self._rpc('job_reuse', dict(job_id=job['id'], original_hash=source['originalHash']), request_id, auth, 'reuse')
            self._cleanup(job['id'], auth); self.builds.release(job['id'])
            return {**reused, **self._source_info(existing['id']), 'state': 'prepared',
                    'generation': job['generation'], 'checkpoint': job['checkpoint']}
        original = self.repository.put_artifact(job['id'], 'original', paths['archive'], request_id, original_hash=source['originalHash'])
        self._rpc('job_uploaded', dict(job_id=job['id'], original_hash=source['originalHash'],
                  original_bytes=source['originalBytes'], original_archive=original), request_id, auth, 'original-ready')
        job = self._job(job['id'], auth)
        self.builds.start(job)
        self._cleanup(job['id'], auth)
        return dict(job_id=job['id'], generation=job['generation'], checkpoint=job['checkpoint'], state='reading')

    def _prepare(self, job, data, request_id, auth):
        if job['state'] in ('prepared', 'activated'):
            return dict(state='prepared', generation=job['generation'], checkpoint=job['checkpoint'],
                        **self._source_info(job['import_id']))
        if data.get('restart', False):
            changed = self._rpc('job_restart', dict(job_id=job['id'], generation=data['generation']), request_id, auth, 'restart')
            self.builds.release(job['id'])
            job = self._job(job['id'], auth)
            paths = self.builds.paths(job['id'])
            self.repository.read_original(job, paths['archive'])
            with open(paths['archive'], 'rb') as source:
                verified = verify_csv_archive(source, paths['csv'])
            if verified['originalHash'] != job['original_hash'] or verified['originalBytes'] != job['metadata']['original_bytes']:
                raise SnapshotError('bill_invalid_archive')
            self.builds.start(job)
            return dict(state='reading', generation=changed['generation'], checkpoint=0,
                        sourceRowCount=0, recordCount=0)
        progress = self.builds.step(job['id'], data['generation'], data['expected_checkpoint'], auth, self._check)
        if progress['state'] == 'restart_required':
            return progress
        self._rpc('job_checkpoint', dict(job_id=job['id'], generation=progress['generation'],
                  expected_checkpoint=data['expected_checkpoint'], next_checkpoint=progress['checkpoint'],
                  state='packaging' if progress['state'] == 'prepared' else progress['state'],
                  counts=dict(sourceRowCount=progress['sourceRowCount'], recordCount=progress['recordCount'])),
                  request_id, auth, 'checkpoint')
        if progress['state'] == 'prepared':
            built = self.builds.artifacts(job['id'])
            self._check(auth)
            stored = self.repository.put_artifact(job['id'], 'index', built['indexArchivePath'], request_id)
            manifest = validate_manifest(dict(format='snapshot-v2', parserVersion='bill-csv-v1', indexVersion=1,
                originalHash=job['original_hash'], originalBytes=job['metadata']['original_bytes'],
                originalArchive=job['original_archive'], indexArchive={**built['indexArchive'], **stored},
                vendorDigest=built['summary']['vendorDigest'], **built['summary']['counts']))
            counts = built['summary']['counts']
            metadata = dict(loaded=True, simulated=False, label=job['metadata']['filename'],
                asOf=job['metadata'].get('as_of', ''), refreshedAt=self.clock().astimezone(timezone.utc).isoformat(),
                sourceFormat=built['sourceFormat'], importedRowCount=counts['sourceRowCount'],
                collapsedRowCount=counts['collapsedRowCount'], excludedRowCount=counts['excludedRowCount'],
                sourceIssueCount=counts['warningCount'])
            staged = self._rpc('snapshot_stage', dict(job_id=job['id'], generation=job['generation'], manifest=manifest,
                               metadata=metadata), request_id, auth, 'stage-snapshot')
            self.builds.release(job['id'])
            progress.update(self._source_info(staged['import_id']))
        return progress

    @contextmanager
    def _index(self, import_id, auth):
        self._check(auth)
        source = self.repository.source(import_id)
        if source['state'] != 'ready':
            raise SnapshotError('bill_incomplete')
        if source.get('storage_format', 'rows-v1') == 'snapshot-v2':
            with self.cache.acquire(self.config.workspace_id, import_id, source['snapshot_manifest'], auth, self._check) as connection:
                yield SnapshotIndex(connection, build=False), source
            return
        # Legacy sources stay immutable and readable. Build only a temporary local
        # index from their complete paginated records; never rewrite their rows.
        with tempfile.TemporaryDirectory(prefix='hwfc-bill-legacy-') as folder:
            from pathlib import Path
            connection = sqlite3.connect(Path(folder) / 'legacy.sqlite')
            try:
                connection.executescript('create table bill_records(ordinal integer primary key,vendor_key text,reference_key text,kind text,amount integer,record text);create table bill_vendors(vendor_key text primary key,vendor text,ordinal integer);create table bill_warnings(id integer primary key,source_rows text,reason text);')
                after = -1
                while True:
                    self._check(auth)
                    page = self.repository.base.records_page(self.config.workspace_id, import_id, after, 500)
                    for record in page['records']:
                        after += 1
                        record = validate_record(record)
                        if record['id'] != f'{import_id}:{after}':
                            raise SnapshotError('bill_incomplete')
                        connection.execute('insert into bill_records values(?,?,?,?,?,?)', (after, vendor_key(record['vendor']), invoice_key(record['invoiceNumber']), record.get('kind', 'invoice'), record['amount'], encoded(record)))
                        connection.execute('insert or replace into bill_vendors values(?,?,?)', (vendor_key(record['vendor']), record['vendor'], after))
                    if page['nextCursor'] is None:
                        break
                if after + 1 != source['record_count']:
                    raise SnapshotError('bill_incomplete')
                connection.commit()
                connection.execute('create index bill_reference on bill_records(reference_key,kind)')
                connection.execute('create index bill_vendor_amount on bill_records(vendor_key,kind,amount)')
                yield SnapshotIndex(connection, build=False), source
                self._check(auth)
            finally:
                connection.close()

    def handle(self, action, payload, request_id, authorization):
        require_uuid(request_id); self._check(authorization)
        auth = authorization
        if action == 'bill_upload_begin':
            data = allowed(payload, 'filename compressed_size as_of', 'filename compressed_size')
            text(data['filename'], maximum=1024, blank=False)
            integer(data['compressed_size'], minimum=1, maximum=MAX_ARCHIVE_BYTES)
            date_value(data.get('as_of', ''))
            job_id = str(uuid5(UUID(auth.session_nonce), request_id))
            begun = self._rpc('job_begin', {**data, 'job_id': job_id, 'as_of': data.get('as_of', '')}, request_id, auth, 'begin')
            try:
                self.repository.reserve(job_id, 2 * data['compressed_size'] + MAX_ARCHIVE_BYTES, str(uuid5(UUID(request_id), 'reserve')))
            except SnapshotError as error:
                if error.code == 'bill_quota':
                    self._rpc('job_abandon', dict(job_id=job_id, generation=begun['generation']), request_id, auth, 'quota-cancel')
                raise
            return begun
        if action == 'bill_upload_chunk':
            data = allowed(payload, 'job_id index data', 'job_id index data')
            job = self._job(data['job_id'], auth); position = integer(data['index'], minimum=0, maximum=127)
            if job['state'] != 'uploading':
                raise SnapshotError('bill_conflict')
            try:
                raw = base64.b64decode(text(data['data'], maximum=4 * ((CHUNK_BYTES + 2) // 3)), validate=True)
            except (ValueError, binascii.Error):
                raise SnapshotError('bill_invalid_archive') from None
            expected = min(CHUNK_BYTES, job['metadata']['compressed_size'] - position * CHUNK_BYTES)
            if expected <= 0 or len(raw) != expected:
                raise SnapshotError('bill_limit')
            previous = job['chunks'].get(str(position))
            descriptor = dict(hash=hashlib.sha256(raw).hexdigest(), size=len(raw))
            if (previous and previous != descriptor) or (not previous and position != len(job['chunks'])):
                raise SnapshotError('bill_conflict')
            self.repository.write_chunk(job['id'], position, raw)
            return self._rpc('job_chunk', dict(job_id=job['id'], index=position, size=len(raw), chunk_hash=descriptor['hash']), request_id, auth, 'chunk')
        if action in ('bill_upload_finish', 'bill_prepare_step', 'bill_activate', 'bill_cancel'):
            fields = {'bill_upload_finish': 'job_id', 'bill_prepare_step': 'job_id generation expected_checkpoint restart',
                      'bill_activate': 'job_id confirm_restore', 'bill_cancel': 'job_id'}[action]
            data = allowed(payload, fields, 'job_id generation expected_checkpoint' if action == 'bill_prepare_step' else 'job_id')
            job = self._job(data['job_id'], auth)
            if action == 'bill_upload_finish':
                return self._finish_upload(job, request_id, auth)
            if action == 'bill_prepare_step':
                require_uuid(data['generation']); integer(data['expected_checkpoint'], minimum=0)
                if type(data.get('restart', False)) is not bool:
                    raise SnapshotError('bill_incomplete')
                return self._prepare(job, data, request_id, auth)
            if type(data.get('confirm_restore', False)) is not bool:
                raise SnapshotError('bill_incomplete')
            if job['state'] == 'activated':
                return dict(alreadyCurrent=True, **self._source_info(job['import_id']))
            source = self.repository.source(job['import_id']) if job.get('import_id') else None
            needs_restore = source is not None and source['file_hash'] != job.get('original_hash')
            # Reused sources are prepared before any local build, with no completed build counts.
            needs_restore = needs_restore or (job['state'] == 'prepared' and not job.get('counts') and job['checkpoint'] == 0)
            if action == 'bill_cancel' or (needs_restore and not data.get('confirm_restore', False)):
                self._rpc('job_abandon', dict(job_id=job['id'], generation=job['generation']), request_id, auth, 'cancel')
                self.builds.release(job['id'])
                return dict(cancelled=True)
            if job['state'] != 'prepared':
                raise SnapshotError('bill_incomplete')
            self._rpc('snapshot_activate', dict(job_id=job['id'], import_id=job['import_id'],
                      expected_import_version=job['expected_import_version'], confirm_restore=data.get('confirm_restore', False)), request_id, auth, 'activate')
            return self._source_info(job['import_id'])
        if action in ('bill_vendors_page', 'bill_candidates_page', 'bill_warnings_page'):
            if action == 'bill_candidates_page':
                data = allowed(payload, 'query cursor limit', 'query')
                query = validate_query(data['query']); import_id = query['importId']; query_hash = canonical_hash(query)
            else:
                data = allowed(payload, 'import_id cursor limit', 'import_id')
                import_id = require_uuid(data['import_id']); query_hash = canonical_hash([action, import_id])
            limit = integer(data.get('limit', 500), minimum=1, maximum=500)
            after = decode_cursor(data.get('cursor'), import_id, query_hash)
            with self._index(import_id, auth) as (index, source):
                if action == 'bill_candidates_page':
                    result = index.candidates_page(query, after, limit, RESPONSE_BYTES - 4096)
                elif action == 'bill_vendors_page':
                    result = index.vendors_page(after, limit)
                    hasher = hashlib.sha256(b'[')
                    for at, (vendor,) in enumerate(index.db.execute('select vendor from bill_vendors order by ordinal')):
                        if at: hasher.update(b',')
                        hasher.update(encoded(dict(vendor=vendor)).encode())
                    hasher.update(b']'); result['vendorDigest'] = hasher.hexdigest()
                else:
                    result = index.warnings_page(after, limit)
                result['importId'] = import_id
                result['nextCursor'] = encode_cursor(import_id, query_hash, result['nextCursor']) if result['nextCursor'] is not None else None
                self._check(auth)
                return result
        raise SnapshotError('bill_incomplete')
