"""Semantic protections derived only from authoritative current saved evidence."""
import re
from collections import OrderedDict
import threading
import time
from ...models import DECISIONS, validate_record, require_uuid, integer
from ..contracts import canonical_hash, MAX_RECORDS, SnapshotError
from ..normalization import vendor_key, invoice_key

_DONE = 'Reviewed — no action needed'


def _adventure(value):
    stem = re.sub(r'[.,]', '', vendor_key(value))
    suffix = r'\s+(?:incorporated|inc|llc|ltd|limited|corporation|corp|company|co)$'
    while re.search(suffix, stem):
        stem = re.sub(suffix, '', stem).strip()
    return stem in ('adventure in food', 'adventure in food trading')


class ProtectionSet:
    def __init__(self):
        self.keys = set()

    def _add(self, vendor, reference, kind, *, adventure=False):
        if (type(reference) is not str or not invoice_key(reference) or len(reference) > 1024
                or kind not in ('invoice', 'credit')):
            raise ValueError('Saved follow-up has no usable invoice reference.')
        if vendor is not None and (type(vendor) is not str or not vendor_key(vendor)):
            raise ValueError('Saved follow-up has an invalid vendor.')
        key = invoice_key(reference)
        references = [key]
        digits = re.fullmatch(r'([0-9]+)[A-Z]?', key)
        if kind == 'invoice' and adventure and digits:
            references = [digits[1], *(digits[1] + letter for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')]
        self.keys.update((None if vendor is None else vendor_key(vendor), ref, kind) for ref in references)
        if len(self.keys) > MAX_RECORDS:
            raise ValueError('Saved follow-up protection exceeds supported coverage.')

    def _candidate(self, value):
        bill = validate_record(value)
        self._add(bill['vendor'], bill['invoiceNumber'], bill.get('kind', 'invoice'),
                  adventure=_adventure(bill['vendor']))

    def _result(self, row, resolution, vendor, adventure):
        candidates = row.get('candidates', [])
        if type(candidates) is not list:
            raise ValueError('Saved follow-up candidates are unavailable.')
        reference, kind = row.get('invoiceNumber'), row.get('kind', 'invoice')
        if kind not in ('invoice', 'credit'):
            # Account activity can still protect a specific recorded BILL candidate.
            if not candidates:
                raise ValueError('Saved account follow-up cannot be linked to a BILL record.')
        else:
            self._add(vendor, reference, kind, adventure=adventure)
        for candidate in candidates:
            self._candidate(candidate)
        proof = resolution.get('confirmedMatch')
        if proof is not None:
            if type(proof) is not dict or 'candidate' not in proof:
                raise ValueError('Saved confirmed-match evidence is unavailable.')
            self._candidate(proof['candidate'])

    def add_statement(self, statement: dict, revision: dict, mappings: dict):
        doc, results, resolutions = revision.get('doc'), revision.get('results'), revision.get('resolutions')
        if (type(doc) is not dict or type(doc.get('rows')) is not list or type(results) is not list
                or type(resolutions) is not dict or type(mappings) is not dict):
            raise ValueError('Current saved statement evidence is unavailable.')
        name = doc.get('vendor')
        if type(name) is not str or not name:
            raise ValueError('Current saved statement vendor is unavailable.')
        # An explicit mapping resolves the namespace. Without one, do not assume
        # a statement display name is the exact BILL vendor; protect the reference
        # across plausible vendors instead of excluding its actual source bill.
        vendor = mappings.get(name)
        if vendor is not None and (type(vendor) is not str or not vendor_key(vendor)):
            raise ValueError('Saved vendor mapping is invalid.')
        adventure = _adventure(vendor or name)
        by_id = {}
        resolved_refs = set()
        for row in results:
            if type(row) is not dict or not row.get('id') or row['id'] in by_id:
                raise ValueError('Saved statement results are incomplete.')
            by_id[row['id']] = row
            decision = resolutions.get(row['id'], {}).get('decision')
            if decision is not None and decision not in DECISIONS:
                raise ValueError('Saved statement decision is unrecognized.')
            unresolved = decision is not None and decision != _DONE
            automatic = not decision and row.get('status') in ('matched', 'presence')
            if unresolved or (not statement.get('completed') and not decision and not automatic):
                self._result(row, resolutions.get(row['id'], {}), vendor, adventure)
            elif decision == _DONE or automatic:
                resolved_refs.add((invoice_key(row.get('invoiceNumber', '')), row.get('kind', 'invoice')))
        for ident, resolution in resolutions.items():
            if type(resolution) is not dict:
                raise ValueError('Saved follow-up decision is unavailable.')
            if resolution.get('decision') and ident not in by_id:
                raise ValueError('Saved follow-up has no corresponding result evidence.')
        if not statement.get('completed'):
            for row in doc['rows']:
                if type(row) is not dict:
                    raise ValueError('Saved statement row is unavailable.')
                kind = row.get('type', 'invoice')
                if kind not in ('invoice', 'credit'):
                    continue
                key = (invoice_key(row.get('invoiceNumber', '')), kind)
                if key not in resolved_refs:
                    self._add(vendor, row.get('invoiceNumber'), kind, adventure=adventure)

    def add_duplicate(self, review: dict, members: list[dict]):
        if review.get('decision') not in ('confirmed_duplicate', 'not_duplicate', 'unreviewed'):
            raise ValueError('Saved duplicate decision is unrecognized.')
        if review['decision'] == 'not_duplicate':
            return
        count = review.get('memberCount')
        if (type(count) is not int or count < 2 or type(members) is not list
                or len(members) != count or len({m.get('ordinal') for m in members}) != count):
            raise ValueError('Saved duplicate member evidence is incomplete.')
        for member in members:
            self._candidate(member.get('bill'))

    def protects(self, record: dict) -> bool:
        key = (vendor_key(record['vendor']), invoice_key(record['invoiceNumber']), record.get('kind', 'invoice'))
        return key in self.keys or (None, key[1], key[2]) in self.keys

    def digest(self) -> str:
        return canonical_hash(sorted(self.keys, key=lambda k: (k[0] or '', k[1], k[2])))


class ProtectionRepository:
    """Resume private evidence collection; reuse immutable revision derivations."""
    def __init__(self, base, authorize, duplicate_members_reader=None,*,state=None,monotonic=time.monotonic):
        self.base,self.authorize,self.duplicate_members_reader=base,authorize,duplicate_members_reader
        self.state=state if state is not None else {};self.clock=monotonic
        self.lock=self.state.setdefault('lock',threading.RLock())
        self.entries=self.state.setdefault('entries',OrderedDict())
        self.revisions=self.state.setdefault('revisions',OrderedDict())

    def _epoch(self,auth):
        self.authorize(auth);self.base._private_bucket()
        home=self.base._one(self.base.client.table('ap_workspaces').select('bill_protection_epoch').eq('id',self.base.config.workspace_id))
        return integer(home['bill_protection_epoch'],minimum=0)

    def _peek(self,entry,table,key,auth):
        if entry['pending']:return entry['pending'][0]
        if entry['ended']:return None
        self.authorize(auth);self.base._private_bucket()
        query=self.base._table(table).order(key).limit(500)
        if entry['after'] is not None:query=query.gt(key,entry['after'])
        rows=query.execute().data;entry['requests']+=1
        if type(rows) is not list or len(rows)>500:raise SnapshotError('bill_incomplete')
        previous=entry['after']
        for row in rows:
            value=row.get(key)
            if type(value) is not str or previous is not None and value<=previous:raise SnapshotError('bill_incomplete')
            previous=value
        entry['pending']=rows;entry['ended']=len(rows)<500
        return rows[0] if rows else None

    def _advance(self,entry,key):
        row=entry['pending'].pop(0);entry['after']=row[key];entry['count']+=1
        if entry['count']>MAX_RECORDS:raise SnapshotError('bill_limit')

    def _next_phase(self,entry):
        entry.update(phase={'mappings':'statements','statements':'reviews','reviews':'done'}[entry['phase']],pending=[],ended=False,after=None,count=0)

    def snapshot(self,source_import_id,auth,*,deadline=None):
        require_uuid(source_import_id);deadline=min(self.clock()+5,deadline if deadline is not None else float('inf'))
        with self.lock:
            before=self._epoch(auth);nonce=getattr(auth,'session_nonce','local')
            key=(source_import_id,before,nonce)
            for old,item in list(self.entries.items()):
                if self.clock()-item['last']>=3600 or old[0]==source_import_id and old[1]!=before:del self.entries[old]
            entry=self.entries.get(key)
            if entry is None:
                if self.base.import_info(self.base.config.workspace_id,source_import_id)['state']!='ready':raise SnapshotError('bill_incomplete')
                while len(self.entries)>=2:self.entries.popitem(last=False)
                entry=dict(phase='mappings',pending=[],ended=False,after=None,count=0,requests=0,last=self.clock(),mappings={},protections=ProtectionSet(),member_after=-1,member_count=0,member_total=None)
                self.entries[key]=entry
            self.entries.move_to_end(key);entry['last']=self.clock();entry['requests']=0
            try:
                while entry['phase']!='done' and self.clock()<deadline and entry['requests']<8:
                    phase=entry['phase'];table,field={'mappings':('ap_vendor_mappings','vendor'),'statements':('ap_statements','id'),'reviews':('ap_duplicate_reviews','key')}[phase]
                    row=self._peek(entry,table,field,auth)
                    if row is None:self._next_phase(entry);continue
                    if self.clock()>=deadline:break
                    self.authorize(auth)
                    if phase=='mappings':entry['mappings'][row['vendor']]=row['bill_vendor'];self._advance(entry,field)
                    elif phase=='statements':
                        rid=require_uuid(row['current_revision_id']);ident=require_uuid(row['id'])
                        cached_key=(rid,ident,canonical_hash(entry['mappings']),bool(row.get('completed')))
                        if cached_key not in self.revisions:
                            revision=self.base._one(self.base._table('ap_statement_revisions').eq('id',rid));entry['requests']+=1
                            if revision['statement_id']!=ident:raise SnapshotError('bill_incomplete')
                            derived=ProtectionSet();derived.add_statement(row,revision,entry['mappings'])
                            while self.revisions and (len(self.revisions)>=2000 or sum(len(keys) for keys in self.revisions.values())+len(derived.keys)>MAX_RECORDS):self.revisions.popitem(last=False)
                            self.revisions[cached_key]=frozenset(derived.keys)
                        self.revisions.move_to_end(cached_key);entry['protections'].keys.update(self.revisions[cached_key]);self._advance(entry,field)
                    else:
                        if row['decision']=='not_duplicate':self._advance(entry,field);continue
                        if row['decision'] not in ('confirmed_duplicate','unreviewed') or self.duplicate_members_reader is None:raise SnapshotError('bill_incomplete')
                        evidence=self.duplicate_members_reader(row,auth,deadline=deadline,after=entry['member_after'])
                        total=integer(evidence['memberCount'],minimum=2,maximum=MAX_RECORDS)
                        if entry['member_total'] is not None and entry['member_total']!=total:raise SnapshotError('bill_incomplete')
                        members=evidence['members']
                        if type(members) is not list or not members or len(members)>250:raise SnapshotError('bill_incomplete')
                        for member in members:
                            n=integer(member['ordinal'],minimum=entry['member_after']+1,maximum=MAX_RECORDS-1)
                            entry['protections']._candidate(member['bill']);entry['member_after']=n;entry['member_count']+=1
                        entry['member_total']=total
                        if evidence.get('nextCursor') is None:
                            if entry['member_count']!=total:raise SnapshotError('bill_incomplete')
                            self._advance(entry,field);entry.update(member_after=-1,member_count=0,member_total=None)
                        elif evidence['nextCursor']!=entry['member_after'] or entry['member_count']>=total:raise SnapshotError('bill_incomplete')
                    if len(entry['protections'].keys)>MAX_RECORDS:raise SnapshotError('bill_limit')
                after=self._epoch(auth)
                if before!=after:raise SnapshotError('bill_conflict')
                if entry['phase']!='done':raise SnapshotError('bill_range_loading')
                return dict(epoch=after,digest=entry['protections'].digest(),protections=entry['protections'])
            except SnapshotError as error:
                if error.code!='bill_range_loading':self.entries.pop(key,None)
                raise
            except Exception:
                self.entries.pop(key,None);raise
