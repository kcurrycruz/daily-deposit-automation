"""Scope-pinned active reads and explicit exact-reference archive lookups."""
import json
import time
from ...models import allowed,integer,require_uuid,validate_record
from ..contracts import (SnapshotError,canonical_hash,validate_query,encode_cursor,decode_cursor,RESPONSE_BYTES)
from ..index import SnapshotIndex
from ..parser import encoded


class WorkingQueries:
    def __init__(self,operations):
        self.ops=operations;self.repo=operations.repository;self.cache=operations.cache

    def _scope(self,set_id,auth):
        self.ops._check(auth);require_uuid(set_id);home=self.repo.home()
        if home.get('active_working_set_id')!=set_id:raise SnapshotError('bill_conflict')
        if home.get('working_protection_epoch')!=home['bill_protection_epoch']:
            raise SnapshotError('bill_range_refresh')
        manifest=self.repo.working_set(set_id)['manifest']
        if manifest['source']['importId']!=home['active_import_id']:raise SnapshotError('bill_conflict')
        return manifest

    def _prepare(self,manifest,auth):
        if not self.cache.prepare(manifest,auth,self.ops._check,time.monotonic()+5):
            raise SnapshotError('bill_range_loading')

    def candidates_page(self,set_id,query,cursor,auth,limit=500):
        manifest=self._scope(set_id,auth);integer(limit,minimum=1,maximum=500)
        scoped=allowed(query,'importId workingSetId references amounts','importId workingSetId references amounts')
        if scoped['workingSetId']!=set_id or scoped['importId']!=manifest['source']['importId']:
            raise SnapshotError('bill_conflict')
        validate_query({k:v for k,v in scoped.items() if k!='workingSetId'})
        query_hash=canonical_hash(scoped);after=decode_cursor(cursor,scoped['importId'],query_hash)
        self._prepare(manifest,auth)
        conditions=[];params=[]
        for key in scoped['references']:
            conditions.append('(reference_key=? and kind=?)');params.extend([key['invoiceKey'],key['kind']])
        for key in scoped['amounts']:
            conditions.append('(vendor_key=? and kind=? and amount=?)');params.extend([key['vendorKey'],key['kind'],key['amount']])
        predicate='('+' or '.join(conditions)+')' if conditions else '0'
        with self.cache.acquire(manifest,auth,self.ops._check) as (db,_):
            total=db.execute('select count(*) from working_records where '+predicate,params).fetchone()[0]
            out=dict(importId=scoped['importId'],workingSetId=set_id,workingDigest=manifest['workingDigest'],queryDigest=query_hash,
                     total=total,afterOrdinal=after,nextCursor=None,records=[])
            size=len(encoded(out).encode())+2048;last=after
            rows=db.execute('select source_ordinal,record from working_records where '+predicate+' and source_ordinal>? order by source_ordinal limit ?', [*params,after,limit])
            for ordinal,raw in rows:
                record={**validate_record(json.loads(raw)),'id':f'{scoped["importId"]}:{ordinal}'}
                added=len(encoded(record).encode())+1
                if size+added>RESPONSE_BYTES:
                    if not out['records']:raise SnapshotError('bill_limit')
                    break
                size+=added;out['records'].append(record);last=ordinal
            more=db.execute('select 1 from working_records where '+predicate+' and source_ordinal>? limit 1', [*params,last]).fetchone()
            if more:out['nextCursor']=encode_cursor(scoped['importId'],query_hash,last)
        self._scope(set_id,auth);return out

    def vendors_page(self,set_id,cursor,auth,limit=500,include_archived=False):
        manifest=self._scope(set_id,auth);integer(limit,minimum=1,maximum=500)
        if type(include_archived) is not bool:raise SnapshotError('bill_incomplete')
        identity=canonical_hash(['working-vendors',set_id,manifest['workingDigest'],include_archived])
        after=decode_cursor(cursor,manifest['source']['importId'],identity);self._prepare(manifest,auth)
        table='archive_vendors' if include_archived else 'working_vendors'
        with self.cache.acquire(manifest,auth,self.ops._check) as (db,_):
            total=db.execute('select count(*) from '+table).fetchone()[0]
            rows=db.execute('select ordinal,vendor from '+table+' where ordinal>? order by ordinal limit ?', (after,limit)).fetchall()
            last=rows[-1][0] if rows else after
            more=db.execute('select 1 from '+table+' where ordinal>? limit 1',(last,)).fetchone()
            out=dict(importId=manifest['source']['importId'],workingSetId=set_id,workingDigest=manifest['workingDigest'],
                     total=total,vendors=[dict(vendor=v) for _,v in rows],vendorDigest=manifest['archiveVendorDigest' if include_archived else 'vendorDigest'],
                     nextCursor=encode_cursor(manifest['source']['importId'],identity,last) if more else None)
        self._scope(set_id,auth);return out

    def archived_references_page(self,import_id,references,cursor,auth,limit=500):
        require_uuid(import_id);home=self.repo.home();set_id=home.get('active_working_set_id')
        if home['active_import_id']!=import_id or not set_id:raise SnapshotError('bill_conflict')
        manifest=self._scope(set_id,auth)
        query=validate_query(dict(importId=import_id,references=references,amounts=[]))
        if not references:raise SnapshotError('bill_incomplete')
        integer(limit,minimum=1,maximum=500)
        identity=canonical_hash(['archived-references',query,set_id,manifest['workingDigest']])
        after=decode_cursor(cursor,import_id,identity);self._prepare(manifest,auth)
        with self.ops.bill_ops._index(import_id,auth) as (index,_):
            page=SnapshotIndex(index.db,build=False).candidates_page(query,after,limit,RESPONSE_BYTES-4096)
        with self.cache.acquire(manifest,auth,self.ops._check) as (db,_):
            ordinals=[int(record['id'].split(':')[-1]) for record in page['records']]
            active={n for n, in db.execute('select source_ordinal from working_records where source_ordinal in ('+','.join('?' for _ in ordinals)+')',ordinals)} if ordinals else set()
        page.update(workingSetId=set_id,workingDigest=manifest['workingDigest'],queryDigest=identity,
                    archivedIds=[r['id'] for r,n in zip(page['records'],ordinals) if n not in active])
        page['nextCursor']=encode_cursor(import_id,identity,page['nextCursor']) if page['nextCursor'] is not None else None
        self._scope(set_id,auth);return page

    def handle(self,action,payload,auth):
        if action=='bill_candidates_page':
            data=allowed(payload,'query cursor limit','query')
            if type(data['query']) is not dict:raise SnapshotError('bill_incomplete')
            return self.candidates_page(data['query'].get('workingSetId'),data['query'],data.get('cursor'),auth,data.get('limit',500))
        if action=='bill_vendors_page':
            data=allowed(payload,'import_id working_set_id cursor limit include_archived','import_id working_set_id')
            manifest=self._scope(data['working_set_id'],auth)
            if data['import_id']!=manifest['source']['importId']:raise SnapshotError('bill_conflict')
            return self.vendors_page(data['working_set_id'],data.get('cursor'),auth,data.get('limit',500),data.get('include_archived',False))
        if action=='bill_archived_candidates_page':
            data=allowed(payload,'import_id references cursor limit','import_id references')
            return self.archived_references_page(data['import_id'],data['references'],data.get('cursor'),auth,data.get('limit',500))
        raise SnapshotError('bill_incomplete')
