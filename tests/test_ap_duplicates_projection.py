import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4
from fixtures.ap_shared.duplicate_cases import PIN, bill
from test_ap_shared_access import CONFIG
from app.ap_shared.bills.duplicates.contracts import RULE_VERSION


class ProjectionRepository:
    def __init__(self):
        self.config = CONFIG; self.revision = 1; self.pages = 0
        self.pin = {**PIN, 'recordCount': 10000}
        self.reviews = [dict(key=f'{n:064x}', decision='not_duplicate', initials='KC', note='',
                             version=1, at='2026-10-22T12:00:00Z', reviewedImportId=PIN['importId']) for n in range(550)]
    def current(self): return self.pin
    def review_revision(self): return self.revision
    def reviews_page(self, after_key=None, limit=500):
        self.pages += 1
        values = [r for r in self.reviews if after_key is None or r['key'] > after_key]
        return dict(reviews=values[:limit], nextCursor=values[limit-1]['key'] if len(values)>limit else None)


class ProjectionSource:
    def __init__(self, repo): self.repo=repo; self.ops=SimpleNamespace(_check=lambda _:None)
    def members(self, pin, ordinals, auth):
        if pin != self.repo.pin: raise ValueError('stale')
        return [dict(ordinal=n,bill={**bill(str(n)), 'sourceIssues':'warning '*10000}) for n in ordinals]


class ProjectionCache:
    def __init__(self, path): self.path=path
    @contextmanager
    def acquire(self, *args, **kwargs):
        db=sqlite3.connect(self.path)
        try: yield db
        finally: db.close()


class DuplicateProjectionTests(unittest.TestCase):
    def fixture(self):
        from app.ap_shared.bills.duplicates.projection import ReviewProjection
        from app.ap_shared.bills.duplicates.artifacts import SCHEMA
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path=Path(temp.name)/'result.sqlite'; db=sqlite3.connect(path)
        for name, schema in SCHEMA.items(): db.execute('create table '+name+'('+schema+')')
        for n in range(620):
            db.execute('insert into findings values(?,?,?,?,?,?,?,?,?,?)',
                       (n,f'{n:064x}','possible_duplicate','possible','["suffix"]','2026-10-01',
                        10000 if n==619 else 2,'[]', 'é 100%_ "quote"' if n==600 else 'synthetic '+str(n),
                        json.dumps(dict(version=1,dateGapDays=0,referenceReuse=False,profiles=[]))))
            count=10000 if n==619 else 2
            db.executemany('insert into members values(?,?,?)', ((n,i,'a'*64) for i in range(count)))
        db.commit(); db.close()
        repo=ProjectionRepository(); source=ProjectionSource(repo)
        cache=ProjectionCache(path); scan=dict(id=str(uuid4()),workspace_id=CONFIG.workspace_id,
            import_id=PIN['importId'],source_digest=PIN['sourceDigest'],rule_version=RULE_VERSION,manifest={})
        projection=ReviewProjection(repo,cache,source,time.monotonic); self.addCleanup(projection.close)
        return projection,repo,scan
    def test_scoped_projection_rejects_swapped_original_ordinal(self):
        from app.ap_shared.bills.duplicates.rules import bill_fingerprint
        p,repo,scan=self.fixture()
        repo.pin={**repo.pin,'storageFormat':'working-v1','workingSetId':str(uuid4()),'workingDigest':repo.pin['sourceDigest'],'workingVersion':1,'fullSourceDigest':'f'*64,'fullRecordCount':10001,'mappingDigest':'d'*64}
        scan['rule_version']='bill-duplicates-v4';scan['working_set_id']=repo.pin['workingSetId']
        with sqlite3.connect(p.cache.path) as db:
            db.execute('create table source_map(ordinal integer primary key,source_ordinal integer,fp text)')
            for n in range(2):
                value=bill(str(n));fp=bill_fingerprint(value)
                db.execute('update members set fp=? where finding_id=0 and ordinal=?',(fp,n))
                db.execute('insert into source_map values(?,?,?)',(n,n+1,fp))
        db.close()
        p.source.members=lambda pin,ordinals,auth:[dict(ordinal=n,sourceOrdinal=n+2,bill=bill(str(n))) for n in ordinals]
        self.ready(p,scan)
        with self.assertRaisesRegex(ValueError,'could not be verified'):
            p.members_page(scan,'0'*64,None,100,None)

    def ready(self,p,scan):
        for _ in range(30):
            result=p.prepare(scan,None,time.monotonic()+5)
            if result['ready']: return result
        self.fail('projection never completed')
    def test_complete_review_pages_and_counts_never_use_partial_projection(self):
        p,repo,scan=self.fixture()
        with self.assertRaises(ValueError): p.findings_page(scan,{},None,100,None)
        self.assertFalse(p.prepare(scan,None,time.monotonic()-1)['ready'])
        self.ready(p,scan); self.assertGreaterEqual(repo.pages,2)
        page=p.findings_page(scan,{},None,100,None)
        self.assertEqual(page['counts'],dict(all=620,reviewed=550,unreviewed=70))
        self.assertEqual(len(page['findings']),70)
        self.assertEqual(page['total'],70)
        self.assertTrue(all(f['review'] is None for f in page['findings']))
        self.assertEqual(page['findings'][0]['latestInvoiceDate'],'2026-10-01')
        self.assertEqual(page['findings'][0]['preview'],[])
        self.assertFalse(page['findings'][0]['priorReview'])
        self.assertEqual(page['findings'][0]['evidence']['version'],1)

    def test_new_pattern_filters_accept_valid_classes_without_expanding_review_scope(self):
        p,_,scan=self.fixture();self.ready(p,scan)
        for kind in ['reference_entry_issue','possible_wrong_vendor']:
            page=p.findings_page(scan,dict(classification=kind),None,100,None)
            self.assertEqual(page['total'],0)
        with self.assertRaises(ValueError):p.findings_page(scan,dict(classification='any_sql'),None,100,None)
    def test_order_cursor_binding_literal_search_and_revision_changes(self):
        p,repo,scan=self.fixture(); self.ready(p,scan)
        filters=dict(review='all',classification=None,search='')
        page=p.findings_page(scan,filters,None,100,None)
        self.assertEqual([f['key'] for f in page['findings']],[f'{n:064x}' for n in range(100)])
        next_page=p.findings_page(scan,filters,page['nextCursor'],100,None)
        self.assertEqual(next_page['findings'][0]['key'],f'{100:064x}')
        for search in ['%', '_', 'é', '"quote"']:
            result=p.findings_page(scan,{**filters,'search':search},None,100,None)
            self.assertEqual(result['total'],1)
            self.assertEqual(result['counts'],dict(all=620,reviewed=550,unreviewed=70))
        for change in [dict(review='reviewed'),dict(search='different')]:
            with self.assertRaises(ValueError): p.findings_page(scan,{**filters,**change},page['nextCursor'],100,None)
        with self.assertRaises(ValueError): p.findings_page(scan,filters,'forged',100,None)
        repo.revision+=1
        with self.assertRaises(ValueError): p.findings_page(scan,filters,page['nextCursor'],100,None)
    def test_revision_during_build_and_source_rule_mismatch_reject_evidence(self):
        p,repo,scan=self.fixture()
        original=repo.reviews_page
        def racing(*args):
            output=original(*args); repo.revision+=1; return output
        repo.reviews_page=racing
        with self.assertRaises(ValueError): self.ready(p,scan)
        repo.reviews_page=original; self.ready(p,scan)
        for bad in [{**scan,'source_digest':'b'*64},{**scan,'rule_version':'future'}]:
            with self.assertRaises(ValueError): p.members_page(bad,f'{619:064x}',None,100,None)
        with self.assertRaises(ValueError): p.members_page(scan,'f'*64,None,100,None)
    def test_large_group_members_are_byte_bounded_and_complete(self):
        p,repo,scan=self.fixture(); self.ready(p,scan)
        seen=[]; cursor=None
        while True:
            page=p.members_page(scan,f'{619:064x}',cursor,100,None)
            self.assertLessEqual(len(page['members']),100)
            self.assertLess(len(json.dumps(page).encode()),1024*1024)
            seen.extend(m['ordinal'] for m in page['members'])
            cursor=page['nextCursor']
            if cursor is None: break
        self.assertEqual(seen,list(range(10000)))
