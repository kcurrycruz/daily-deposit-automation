"""Cooperative exact-reference exclusions; immutable evidence is never rewritten."""
import time
from ..normalization import vendor_key,invoice_key
from .contracts import DuplicateError
from .rules import bill_fingerprint

POLICY='exact-vendor-reference-v1'

class ExactReferenceExclusions:
    def __init__(self,source_reader,*,clock=time.monotonic):
        self.source,self.clock=source_reader,clock
        self.after=-1;self.current=None;self.done=False;self.records={}

    def initialize(self,db):
        db.execute('create table exact_reference_exclusions(key text primary key)')

    def _members(self,db,artifact,job,pairs,pin,auth):
        ordinals=[n for n,_ in pairs]
        if any(n not in self.records for n in ordinals):
            # At most 100 immutable source records, shared across nearby small
            # groups. Source.members revalidates the source before/after the read.
            kept={n:self.records[n] for n in ordinals if n in self.records}
            wanted=list(dict.fromkeys(n for n in ordinals if n not in kept))
            seen=set(wanted)|set(kept)
            for ident, in db.execute('select id from findings where id>? order by id limit 49',(job['id'],)):
                if len(wanted)+len(kept)>=100:break
                for n, in artifact.execute('select ordinal from members where finding_id=? order by ordinal limit 100',(ident,)):
                    if n not in seen:
                        wanted.append(n);seen.add(n)
                        if len(wanted)+len(kept)==100:break
            values=self.source.members(pin,wanted,auth)
            if len(values)!=len(wanted) or any(value.get('ordinal')!=n for n,value in zip(wanted,values)):raise DuplicateError('duplicate_invalid_source')
            kept.update(zip(wanted,values));self.records=kept
        return [self.records[n] for n in ordinals]

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
            values=self._members(db,artifact,job,pairs,pin,auth)
            if len(values)!=len(pairs):raise DuplicateError('duplicate_invalid_source')
            mixed=False;pending=dict(job)
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
                if pending['identity'] is None:pending['identity']=identity
                elif pending['identity']!=identity:mixed=True
                pending['read']+=1;pending['after']=n;used+=1
            self.source.ops._check(auth)
            if pending['read']>job['total']:raise DuplicateError('duplicate_invalid_source')
            if mixed or pending['read']==job['total']:
                if not mixed:
                    db.execute('insert into exact_reference_exclusions values(?)',(job['key'],));db.commit()
                self.after=job['id'];self.current=None;groups+=1
            else:self.current=pending
        db.commit();return self.done
