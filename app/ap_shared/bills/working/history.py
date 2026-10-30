"""Compact full-source training inputs; never stores duplicate candidate evidence."""
from ...models import validate_record
from ..contracts import MAX_INDEX_BYTES,SnapshotError,canonical_hash
from ..normalization import vendor_key,invoice_key
from ..duplicates.rules import eligible,normalized_identity,identity_warnings,invoice_day
from ..duplicates.vendor_patterns import VendorPatterns,reference_shape


class TrainingHistory:
    def __init__(self,db,record_count,monotonic):
        self.db,self.record_count,self.clock=db,record_count,monotonic;self.read=0
        db.executescript('''
          pragma cache_size=-8192;pragma temp_store=FILE;
          pragma journal_mode=MEMORY;pragma synchronous=OFF;
          create table nodes(ident text primary key,ordinal integer unique,n integer,
            vendor text,ref text,amount integer,day integer,warning integer,shape text);
        ''')
        self.patterns=VendorPatterns(db)

    def ingest(self,items,deadline=float('inf')):
        if len(items)>5000:raise SnapshotError('bill_incomplete')
        consumed=0
        for item in items:
            if self.clock()>=deadline:break
            n=item['ordinal']
            if type(n) is not int or n!=self.read or n>=self.record_count:raise SnapshotError('bill_incomplete')
            value=validate_record(item['bill']);self.read+=1;consumed+=1
            if not eligible(value):continue
            identity=canonical_hash(normalized_identity(value))
            self.db.execute('''insert into nodes values(?,?,?,?,?,?,?,?,?)
              on conflict(ident) do update set n=n+1,warning=max(warning,excluded.warning)''',
              (identity,n,1,vendor_key(value['vendor']),invoice_key(value['invoiceNumber']),value['amount'],
               invoice_day(value),bool(identity_warnings(value)),reference_shape(value['invoiceNumber'])))
        if self.db.execute('pragma page_count').fetchone()[0]*self.db.execute('pragma page_size').fetchone()[0]>MAX_INDEX_BYTES:raise SnapshotError('bill_limit')
        self.db.commit();return consumed

    def finish_input(self):
        if self.read!=self.record_count:raise SnapshotError('bill_incomplete')
