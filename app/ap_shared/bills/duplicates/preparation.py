"""Cooperative private archive preparation; never expose a partially verified file."""
from contextlib import closing
import gzip
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import time
import zlib
from .contracts import DuplicateError,MAX_BYTES


class Unpack:
    def __init__(self,root,download,expected):
        self.directory=tempfile.TemporaryDirectory(prefix='prepared-',dir=root)
        self.path=Path(self.directory.name)/'index.sqlite'
        self.packed=Path(self.directory.name)/'archive.gz'
        self.download,self.expected=download,expected
        self.incoming=self.output=None
        self.hash=hashlib.sha256();self.size=0;self.done=False

    def step(self,deadline,max_bytes=4*1024*1024):
        if self.done:return True
        if time.monotonic()>=deadline:return False
        if self.incoming is None:
            self.download(self.packed)
            # The repository has already verified the bounded compressed bytes.
            self.incoming=gzip.open(self.packed,'rb');self.output=open(self.path,'wb')
        consumed=0
        while consumed<max_bytes and time.monotonic()<deadline:
            try:chunk=self.incoming.read(min(65536,max_bytes-consumed))
            except (OSError,EOFError,zlib.error):raise DuplicateError('duplicate_invalid_source') from None
            if not chunk:
                self.incoming.close();self.output.close();self.incoming=self.output=None
                if self.size!=self.expected['expandedBytes'] or self.hash.hexdigest()!=self.expected['expandedHash']:
                    raise DuplicateError('duplicate_invalid_source')
                self.done=True;return True
            self.size+=len(chunk);consumed+=len(chunk)
            if self.size>min(MAX_BYTES,self.expected['expandedBytes']):raise DuplicateError('duplicate_limit')
            self.hash.update(chunk);self.output.write(chunk)
        return False

    def close(self):
        for stream in (self.incoming,self.output):
            if stream:stream.close()
        self.incoming=self.output=None
        self.directory.cleanup()


def connect(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('pragma query_only=ON');db.execute('pragma trusted_schema=OFF');db.execute('pragma cache_size=-8192')
        if hasattr(db,'enable_load_extension'):db.enable_load_extension(False)
        return db
    except Exception:
        db.close();raise


def bounded(db,deadline):
    db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)


def stamp(path):
    value=Path(path).stat()
    return value.st_size,value.st_mtime_ns
