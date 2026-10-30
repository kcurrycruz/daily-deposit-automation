"""Cooperative exact-reference exclusions; immutable evidence is never rewritten."""
import time
from ..normalization import vendor_key,invoice_key
from .contracts import DuplicateError
from .rules import bill_fingerprint

POLICY='exact-vendor-reference-v1'

class ExactReferenceExclusions:
    def __init__(self,source_reader,*,clock=time.monotonic):
        self.source,self.clock=source_reader,clock
        self.after=-1;self.current=None;self.done=False

    def initialize(self,db):
        db.execute('create table exact_reference_exclusions(key text primary key)')

    def advance(self,db,artifact,scan,pin,auth,deadline):
        used=groups=0
        while not self.done and self.clock()<deadline and used<1000 and groups<250:
            if self.current is None:
                row=db.execute('select id,key,member_count from findings where id>? order by id limit 1',(self.after,)).fetchone()
                if row is None:self.done=True;break
                ident,key,total=row
                if type(total) is not int or total<2 or artifact.execute('select count(*) from members where finding_id=?',(ident,)).fetchone()[0]!=total:raise DuplicateError('duplicate_invalid_source')
                self.current=dict(id=ident,key=key,total=total,after=-1,read=0,identity=None)
            job=self.current
            pairs=artifact.execute('select ordinal,fp from members where finding_id=? and ordinal>? order by ordinal limit 100',(job['id'],job['after'])).fetchall()
            if not pairs:raise DuplicateError('duplicate_invalid_source')
            ordinals=[n for n,_ in pairs]
            self.source.ops._check(auth)
            values=self.source.members(pin,ordinals,auth)
            if len(values)!=len(pairs):raise DuplicateError('duplicate_invalid_source')
            mixed=False
            for (n,fp),value in zip(pairs,values):
                if type(n) is not int or not 0<=n<pin['recordCount'] or value.get('ordinal')!=n:raise DuplicateError('duplicate_invalid_source')
                bill=value['bill'];original=n
                if pin['storageFormat']=='working-v1':
                    mapped=artifact.execute('select source_ordinal,fp from source_map where ordinal=?',(n,)).fetchone()
                    if mapped is None or mapped!=(value.get('sourceOrdinal'),fp):raise DuplicateError('duplicate_invalid_source')
                    original=mapped[0]
                if bill.get('id')!=f'{pin["importId"]}:{original}' or bill_fingerprint(bill)!=fp:raise DuplicateError('duplicate_invalid_source')
                identity=(vendor_key(bill['vendor']),invoice_key(bill['invoiceNumber']))
                if not all(identity):raise DuplicateError('duplicate_invalid_source')
                if job['identity'] is None:job['identity']=identity
                elif job['identity']!=identity:mixed=True
                job['read']+=1;job['after']=n;used+=1
            self.source.ops._check(auth)
            if job['read']>job['total']:raise DuplicateError('duplicate_invalid_source')
            if mixed or job['read']==job['total']:
                if not mixed:db.execute('insert into exact_reference_exclusions values(?)',(job['key'],))
                self.after=job['id'];self.current=None;groups+=1
        db.commit();return self.done
