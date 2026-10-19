"""Process-local derived work. Durable originals, not these handles, are recovery state."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from .archive import IndexArchiveWriter
from .contracts import LEASE_SECONDS, SnapshotError
from .index import SnapshotIndex
from .parser import CsvStage
from ..models import require_uuid, integer


class BuildRegistry:
    def __init__(self, root=None, clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic):
        self.root = tempfile.TemporaryDirectory(prefix='hwfc-bill-build-', dir=root)
        self.clock, self.monotonic = clock, monotonic
        self.lock = threading.RLock()
        self.entries, self.directories = {}, {}
        self.closed = False

    def paths(self, job_id):
        require_uuid(job_id)
        with self.lock:
            if self.closed:
                raise SnapshotError('bill_restart')
            if job_id not in self.directories:
                self.directories[job_id] = tempfile.TemporaryDirectory(prefix='job-', dir=self.root.name)
            folder = Path(self.directories[job_id].name)
            return dict(csv=folder / 'original.csv', archive=folder / 'original.gz',
                        index=folder / 'index.sqlite', packed=folder / 'index.gz')

    def start(self, job):
        require_uuid(job['id']); require_uuid(job['generation'])
        with self.lock:
            if job['id'] in self.entries:
                if self.entries[job['id']]['generation'] != job['generation']:
                    raise SnapshotError('bill_conflict')
                return
            for key, entry in list(self.entries.items()):
                if self.monotonic() - entry['last'] >= LEASE_SECONDS:
                    self.release(key)
            if len(self.entries) >= 2:
                raise SnapshotError('bill_conflict')
            paths = self.paths(job['id'])
            db = sqlite3.connect(paths['index'], check_same_thread=False)
            try:
                parser = CsvStage(db, paths['csv'])
            except Exception:
                db.close()
                raise
            self.entries[job['id']] = dict(generation=job['generation'], workspace=job['workspace_id'],
                nonce=job['session_nonce'], paths=paths, db=db, parser=parser, index=None, packer=None,
                phase='reading', checkpoint=0, replies={}, sourceRows=0, recordCount=0,
                lock=threading.RLock(), last=self.monotonic(), summary=None, artifact=None,
                sourceFormat='bill-native' if parser.native else 'template')

    def step(self, job_id, generation, expected_checkpoint, authorization, authorize):
        authorize(authorization)
        require_uuid(job_id); require_uuid(generation); integer(expected_checkpoint, minimum=0)
        with self.lock:
            entry = self.entries.get(job_id)
        if not entry:
            return dict(state='restart_required', generation=generation, checkpoint=expected_checkpoint,
                        sourceRowCount=0, recordCount=0)
        with entry['lock']:
            if entry['workspace'] != authorization.workspace_id or entry['nonce'] != authorization.session_nonce:
                raise PermissionError('This BILL build is not available in this session.')
            if entry['generation'] != generation:
                raise SnapshotError('bill_conflict')
            if expected_checkpoint in entry['replies']:
                authorize(authorization)
                return json.loads(json.dumps(entry['replies'][expected_checkpoint]))
            if expected_checkpoint != entry['checkpoint']:
                raise SnapshotError('bill_conflict')
            deadline = self.monotonic() + 5
            if entry['phase'] == 'reading':
                progress = entry['parser'].read_step(max_rows=5000, deadline=deadline)
                entry['sourceRows'] = progress['sourceRowCount']
                if progress['done']:
                    entry['parser'].close()
                    entry['index'] = SnapshotIndex(entry['db'])
                    entry['phase'] = 'grouping'
            elif entry['phase'] == 'grouping':
                progress = entry['index'].consolidate_step(max_groups=500, deadline=deadline)
                entry['recordCount'] = entry['index'].record_count
                if progress['done']:
                    entry['summary'] = entry['index'].finish()
                    entry['db'].close(); entry['db'] = None
                    entry['packer'] = IndexArchiveWriter(entry['paths']['index'], entry['paths']['packed'])
                    entry['phase'] = 'packaging'
            elif entry['phase'] == 'packaging':
                progress = entry['packer'].step(max_bytes=4 * 1024 * 1024, deadline=deadline)
                if progress['done']:
                    entry['artifact'] = progress['artifact']
                    entry['phase'] = 'prepared'
            elif entry['phase'] != 'prepared':
                raise SnapshotError('bill_restart')
            authorize(authorization)
            entry['checkpoint'] += 1
            entry['last'] = self.monotonic()
            result = dict(state=entry['phase'], generation=generation, checkpoint=entry['checkpoint'],
                          sourceRowCount=entry['sourceRows'], recordCount=entry['recordCount'])
            entry['replies'][expected_checkpoint] = result
            return json.loads(json.dumps(result))

    def artifacts(self, job_id):
        with self.lock:
            entry = self.entries.get(job_id)
            if not entry or entry['phase'] != 'prepared':
                raise SnapshotError('bill_incomplete')
            return dict(indexArchivePath=entry['paths']['packed'], indexArchive=entry['artifact'],
                        summary=entry['summary'], sourceFormat=entry['sourceFormat'])

    def release(self, job_id):
        with self.lock:
            entry = self.entries.pop(job_id, None)
            if entry:
                with entry['lock']:
                    entry['parser'].close()
                    if entry['db']:
                        entry['db'].close()
                    if entry['packer']:
                        entry['packer'].close()
            directory = self.directories.pop(job_id, None)
            if directory:
                Path(directory.name).resolve().relative_to(Path(self.root.name).resolve())
                directory.cleanup()

    def close(self):
        with self.lock:
            self.closed = True
            for job_id in list(self.directories):
                self.release(job_id)
            self.root.cleanup()
