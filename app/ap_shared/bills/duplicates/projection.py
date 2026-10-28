"""Complete, revision-pinned shared review views with bounded evidence pages."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from ...models import allowed, integer, text
from .artifacts import SCHEMA
from .contracts import (DuplicateError, RULE_VERSION, RESPONSE_BYTES, MAX_BYTES, encoded,
                        digest, encode_cursor, decode_cursor,CLASSIFICATIONS,validate_finding_evidence)
from .preparation import bounded


class ReviewProjection:
    def __init__(self, repository, artifact_cache, source_reader, clock):
        self.repo, self.cache, self.source, self.clock = repository, artifact_cache, source_reader, clock
        self.root = tempfile.TemporaryDirectory(prefix='hwfc-duplicate-reviews-')
        self.entries, self.lock = {}, threading.RLock()

    def _check(self, scan, auth):
        self.source.ops._check(auth)
        pin = self.repo.current()
        if (pin is None or scan['workspace_id'] != self.repo.config.workspace_id or
            pin['importId'] != scan['import_id'] or pin['sourceDigest'] != scan['source_digest'] or
            scan['rule_version'] != RULE_VERSION):
            raise DuplicateError('duplicate_conflict')
        return pin

    def _identity(self, scan, revision):
        return (scan['workspace_id'], scan['id'], scan['import_id'], scan['source_digest'], RULE_VERSION, revision)

    def invalidate(self, workspace_id):
        with self.lock:
            for key in list(self.entries):
                if key[0] == workspace_id:
                    self.entries.pop(key)['path'].unlink(missing_ok=True)

    def _new(self, scan, revision):
        self.invalidate(scan['workspace_id'])
        path = Path(self.root.name) / (scan['id'] + '.sqlite')
        with closing(sqlite3.connect(path)) as db:
            db.execute('pragma cache_size=-8192')
            db.execute('create table findings(' + SCHEMA['findings'] + ')')
            db.execute('create index finding_order on findings(strength desc,latest_date desc,key)')
            db.execute('create table reviews(key text primary key,decision text,review text)')
            db.commit()
        entry = dict(path=path, phase='findings', after=-1, cursor=None, ready=False, counts=None,
                     count_after=-1,all_count=0,reviewed=0)
        self.entries[self._identity(scan, revision)] = entry
        return entry

    def prepare(self, scan, authorization, deadline):
        with self.lock:
            self._check(scan, authorization)
            revision = self.repo.review_revision(); key = self._identity(scan, revision)
            entry = self.entries.get(key) or self._new(scan, revision)
            if not entry['ready'] and self.clock() < deadline:
                with closing(sqlite3.connect(entry['path'])) as db:
                    db.execute('pragma cache_size=-8192')
                    bounded(db,deadline)
                    if entry['phase'] == 'findings':
                        with self.cache.acquire(scan['workspace_id'], scan['id'], scan['manifest'], authorization,
                                                self.source.ops._check,prepared_only=True) as artifact:
                            bounded(artifact,deadline)
                            rows = artifact.execute('select * from findings where id>? order by id limit 250', (entry['after'],)).fetchall()
                        if rows:
                            inserted=[]
                            for row in rows:
                                if self.clock()>=deadline:break
                                validate_finding_evidence(json.loads(row[9]),row[2],json.loads(row[7]),row[6])
                                db.execute('insert into findings values(?,?,?,?,?,?,?,?,?,?)',row);inserted.append(row[0])
                            db.commit()
                            if inserted:entry['after']=inserted[-1]
                        else:
                            entry['phase'] = 'reviews'
                    elif entry['phase'] == 'reviews':
                        page = self.repo.reviews_page(entry['cursor'], 100)
                        last=entry['cursor'];processed=0
                        for review in page['reviews']:
                            if self.clock()>=deadline:break
                            if review['decision'] not in ('confirmed_duplicate', 'not_duplicate', 'unreviewed'):
                                raise DuplicateError('duplicate_invalid_source')
                            db.execute('insert into reviews values(?,?,?)', (digest(review['key']), review['decision'], encoded(review)))
                            last=review['key'];processed+=1
                        db.commit();entry['cursor']=last
                        if processed==len(page['reviews']) and page['nextCursor'] is None:
                            entry['phase'] = 'counts'
                    else:
                        rows=db.execute('''select f.id,r.decision from findings f left join reviews r on f.key=r.key
                            where f.id>? order by f.id limit 5000''',(entry['count_after'],)).fetchall()
                        entry['all_count']+=len(rows);entry['reviewed']+=sum(d is not None and d!='unreviewed' for _,d in rows)
                        if rows:entry['count_after']=rows[-1][0]
                        else:
                            entry['counts']=dict(all=entry['all_count'],reviewed=entry['reviewed'],unreviewed=entry['all_count']-entry['reviewed'])
                            entry['ready']=True
                    db.commit()
                if entry['path'].stat().st_size > MAX_BYTES:
                    self.invalidate(scan['workspace_id']); raise DuplicateError('duplicate_limit')
            self._check(scan, authorization)
            if self.repo.review_revision() != revision:
                self.invalidate(scan['workspace_id']); raise DuplicateError('duplicate_conflict')
            return dict(ready=entry['ready'], reviewRevision=revision,
                        counts=entry['counts'] if entry['ready'] else None)

    def _ready(self, scan, auth):
        pin = self._check(scan, auth); revision = self.repo.review_revision()
        entry = self.entries.get(self._identity(scan, revision))
        if entry is None or not entry['ready']:
            raise DuplicateError('duplicate_conflict')
        return pin, revision, entry

    def _filters(self, filters):
        out = allowed(filters, 'review classification search')
        out = dict(review=out.get('review', 'unreviewed'), classification=out.get('classification'), search=out.get('search', ''))
        if out['review'] not in ('unreviewed', 'reviewed', 'all') or out['classification'] not in (None,*CLASSIFICATIONS):
            raise DuplicateError('duplicate_conflict')
        text(out['search'], maximum=256)
        return out

    def _binding(self, scan, revision, kind, filters):
        return dict(workspace=scan['workspace_id'], scan=scan['id'], importId=scan['import_id'],
                    digest=scan['source_digest'], rule=RULE_VERSION, revision=revision, kind=kind, filters=filters)

    def _finish(self, scan, auth, revision):
        self._check(scan, auth)
        if self.repo.review_revision() != revision:
            raise DuplicateError('duplicate_conflict')

    def _base(self, scan, revision):
        return dict(scanId=scan['id'], importId=scan['import_id'], ruleVersion=RULE_VERSION, reviewRevision=revision)

    def _finding(self, row, import_id):
        review=json.loads(row[10]) if row[10] else None
        previews=json.loads(row[7])
        return dict(key=row[1], classification=row[2], strength=row[3], reasons=json.loads(row[4]), latestDate=row[5],
                    latestInvoiceDate=row[5],memberCount=row[6],previews=previews,preview=previews,review=review,
                    priorReview=bool(review and review['reviewedImportId']!=import_id),evidence=validate_finding_evidence(json.loads(row[9]),row[2],previews,row[6]))

    def findings_page(self, scan, filters, cursor, limit, authorization):
        integer(limit, minimum=1, maximum=100); filters = self._filters(filters)
        with self.lock:
            _, revision, entry = self._ready(scan, authorization)
            binding = self._binding(scan, revision, 'findings', filters)
            position = decode_cursor(cursor, binding) or dict(offset=0)
            offset = integer(position.get('offset'), minimum=0, maximum=100000)
            where, params = ['1=1'], []
            if filters['classification']:
                where.append('f.classification=?'); params.append(filters['classification'])
            if filters['search']:
                where.append('instr(f.search,?)>0'); params.append(filters['search'].casefold())
            join = ' from findings f left join reviews r on f.key=r.key where ' + ' and '.join(where)
            with closing(sqlite3.connect(entry['path'])) as db:
                bounded(db,min(self.clock()+5,getattr(self,'deadline',float('inf'))))
                all_count, reviewed = db.execute("select count(*),coalesce(sum(r.decision is not null and r.decision<>'unreviewed'),0)" + join, params).fetchone()
                if filters['review'] == 'reviewed': join += " and r.decision<>'unreviewed'"
                elif filters['review'] == 'unreviewed': join += " and (r.decision is null or r.decision='unreviewed')"
                total = {'all':all_count,'reviewed':reviewed,'unreviewed':all_count-reviewed}[filters['review']]
                rows = db.execute('select f.*,r.review' + join + ' order by f.strength desc,f.latest_date desc,f.key limit ? offset ?',
                                  [*params,limit,offset]).fetchall()
            output=[]; used=0
            for row in rows:
                finding=self._finding(row,scan['import_id']); size=len(encoded(finding).encode())
                if used+size>RESPONSE_BYTES:
                    if not output: raise DuplicateError('duplicate_limit')
                    break
                output.append(finding); used+=size
            after=offset+len(output)
            result=dict(**self._base(scan,revision),findings=output,total=total,
                        counts=entry['counts'],
                        nextCursor=encode_cursor(binding,dict(offset=after)) if after<total else None)
            self._finish(scan,authorization,revision)
            return result

    def members_page(self, scan, finding_key, cursor, limit, authorization):
        digest(finding_key); integer(limit, minimum=1, maximum=100)
        with self.lock:
            pin,revision,entry=self._ready(scan,authorization)
            binding=self._binding(scan,revision,'members',dict(key=finding_key))
            position=decode_cursor(cursor,binding) or dict(after=-1)
            after=integer(position.get('after'),minimum=-1,maximum=pin['recordCount']-1)
            with closing(sqlite3.connect(entry['path'])) as db:
                bounded(db,min(self.clock()+5,getattr(self,'deadline',float('inf'))))
                row=db.execute('select f.*,r.review from findings f left join reviews r on f.key=r.key where f.key=?',(finding_key,)).fetchone()
            if row is None: raise DuplicateError('duplicate_conflict')
            with self.cache.acquire(scan['workspace_id'],scan['id'],scan['manifest'],authorization,self.source.ops._check,prepared_only=True) as artifact:
                bounded(artifact,min(self.clock()+5,getattr(self,'deadline',float('inf'))))
                ordinals=[r[0] for r in artifact.execute('select ordinal from members where finding_id=? and ordinal>? order by ordinal limit ?',
                                                       (row[0],after,limit+1))]
            values=self.source.members(pin,ordinals[:limit],authorization) if ordinals else []
            output=[]; used=0
            for value in values:
                size=len(encoded(value).encode())
                if used+size>RESPONSE_BYTES-32768:
                    if not output: raise DuplicateError('duplicate_limit')
                    break
                used+=size; output.append(value)
            has_more=len(output)<len(ordinals)
            result=dict(**self._base(scan,revision),finding=self._finding(row,scan['import_id']),members=output,total=row[6],
                        nextCursor=encode_cursor(binding,dict(after=output[-1]['ordinal'])) if has_more else None)
            self._finish(scan,authorization,revision)
            return result

    def close(self):
        with self.lock:
            self.entries.clear(); self.root.cleanup()
