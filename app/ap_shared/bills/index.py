"""Disk-backed invoice consolidation and bounded parameterized lookups."""
import hashlib
import json
import sqlite3
import time
from ..models import integer, validate_record
from .contracts import MAX_RECORDS, MAX_INDEX_BYTES, PAGE_SIZE, SnapshotError, canonical_hash, validate_query
from .normalization import vendor_key, invoice_key
from .parser import encoded


class SnapshotIndex:
    def __init__(self, connection, *, build=True):
        self.db = connection
        self.pending = None
        self.group_after = -1
        self.record_count = 0
        self.collapsed = 0
        self.done = not build
        self.native = False
        self.has_lines = False
        if build:
            meta = {k: json.loads(v) for k, v in self.db.execute('select key,value from bill_meta')}
            self.native, self.has_lines = meta['format'] == 'bill-native', meta['hasLines']
            self.db.executescript('''
              pragma cache_size=-8192;
              pragma temp_store=FILE;
              pragma max_page_count=131072;
              create table bill_groups(first_row integer primary key,group_key text unique);
              insert into bill_groups select min(source_row),group_key from bill_stage group by group_key;
              create table bill_records(ordinal integer primary key,vendor_key text,reference_key text,
                kind text,amount integer,record text not null);
              create table bill_vendors(vendor_key text primary key,vendor text not null,ordinal integer not null);
            ''')

    def _begin_group(self):
        group = self.db.execute('select first_row,group_key from bill_groups where first_row>? order by first_row limit 1', (self.group_after,)).fetchone()
        if not group:
            self.done = True
            return
        self.group_after, key = group
        self.pending = dict(key=key, phase='analyze', after=0, n=0, first=None, base=None,
                            consistent=True, counts=True, issues=False, valid_sum=True, total=0)

    def _analyze(self, source_row, record, issues, count, order, line_amount, consistent):
        p = self.pending
        if p['first'] is None:
            p['first'], p['base'], p['count'] = record, consistent, count
        p['after'] = source_row
        p['n'] += 1
        p['consistent'] &= consistent == p['base']
        p['counts'] &= count == p['count']
        p['issues'] |= issues != '[]'
        p['valid_sum'] &= line_amount is not None
        p['total'] += line_amount or 0

    def _analyzed(self):
        p = self.pending
        first = json.loads(p['first'])
        distinct, minimum, maximum = self.db.execute('select count(distinct line_order),min(line_order),max(line_order) from bill_stage where group_key=?', (p['key'],)).fetchone()
        complete = self.has_lines and p['count'] is not None and p['count'] > 0 and p['count'] == p['n'] and p['counts'] and distinct == p['n'] and minimum == 0 and maximum == p['n'] - 1
        sums = p['valid_sum'] and first['amount'] is not None and p['total'] == first['amount']
        safe = self.native and p['consistent'] and complete and sums and not p['issues']
        if safe:
            first['sourceRows'] = self.db.execute('select group_concat(source_row) from (select source_row from bill_stage where group_key=? order by source_row)', (p['key'],)).fetchone()[0]
            self._emit(first)
            self.collapsed += p['n'] - 1
            self.pending = None
            return
        p['reason'] = ('Repeated vendor/reference rows do not establish one complete, consistent bill. Review the candidates.' if p['n'] > 1
                       else 'Line-item detail is incomplete or does not agree with the bill total.' if self.has_lines and (not complete or not sums) else '') if self.native else ''
        p['after'], p['phase'] = 0, 'emit'

    def _emit(self, record):
        if self.record_count >= MAX_RECORDS:
            raise SnapshotError('bill_limit')
        record = validate_record(record)
        vendor = vendor_key(record['vendor'])
        self.db.execute('insert into bill_records values(?,?,?,?,?,?)',
                        (self.record_count, vendor, invoice_key(record['invoiceNumber']), record.get('kind', 'invoice'), record['amount'], encoded(record)))
        self.db.execute('insert or replace into bill_vendors values(?,?,?)', (vendor, record['vendor'], self.record_count))
        self.record_count += 1

    def consolidate_step(self, max_groups=500, deadline=float('inf')):
        integer(max_groups, minimum=1, maximum=500)
        rows_processed = groups_processed = 0
        try:
            while not self.done and groups_processed < max_groups and rows_processed < 5000 and time.monotonic() < deadline:
                if self.pending is None:
                    self._begin_group()
                    if self.done:
                        break
                p = self.pending
                row = self.db.execute('select source_row,record,issues,line_count,line_order,line_amount,consistent from bill_stage where group_key=? and source_row>? order by source_row limit 1', (p['key'], p['after'])).fetchone()
                if row is None:
                    if p['phase'] == 'analyze':
                        self._analyzed()
                    else:
                        self.pending = None
                    if self.pending is None:
                        groups_processed += 1
                    continue
                rows_processed += 1
                if p['phase'] == 'analyze':
                    self._analyze(*row)
                else:
                    source, record, issues, *_ = row
                    p['after'] = source
                    record, issues = json.loads(record), json.loads(issues)
                    if self.native:
                        reasons = list(dict.fromkeys(issues + ([p['reason']] if p['reason'] else [])))
                        record['sourceIssues'] = ' '.join(reasons)
                        if record['sourceIssues']:
                            self.db.execute('insert into bill_warnings(source_rows,reason) values(?,?)', (record['sourceRows'], record['sourceIssues']))
                    self._emit(record)
            self.db.commit()
            return dict(done=self.done, checkpoint=self.group_after)
        except sqlite3.DatabaseError:
            self.db.rollback()
            raise SnapshotError('bill_limit') from None

    def finish(self):
        if not self.done:
            raise SnapshotError('bill_incomplete')
        meta = {k: json.loads(v) for k, v in self.db.execute('select key,value from bill_meta')}
        if 'counts' in meta:
            return dict(counts=meta['counts'], vendorDigest=meta['vendorDigest'])
        count = self.db.execute('select count(*) from bill_records').fetchone()[0]
        if not count:
            raise SnapshotError('bill_invalid_archive')
        self.db.executescript('create index bill_reference on bill_records(reference_key,kind);create index bill_vendor_amount on bill_records(vendor_key,kind,amount);')
        counts = dict(recordCount=count, sourceRowCount=meta['sourceRowCount'], collapsedRowCount=self.collapsed,
                      excludedRowCount=meta['excludedRowCount'], warningCount=self.db.execute('select count(*) from bill_warnings').fetchone()[0])
        # Incrementally hash the canonical vendor array without an invoice-sized allocation.
        hasher = hashlib.sha256(b'[')
        for at, (vendor,) in enumerate(self.db.execute('select vendor from bill_vendors order by ordinal')):
            if at:
                hasher.update(b',')
            hasher.update(encoded(dict(vendor=vendor)).encode())
        hasher.update(b']')
        digest = hasher.hexdigest()
        for key, value in [('counts', counts), ('vendorDigest', digest)]:
            self.db.execute('insert or replace into bill_meta values(?,?)', (key, encoded(value)))
        # Discard only derived staging tables, never the original CSV or finalized records.
        self.db.executescript('drop table bill_stage;drop table bill_groups;pragma user_version=1;')
        self.db.commit()
        # DROP leaves pages (and their old CSV bytes) on SQLite's freelist. Pack
        # only the final search data, not hundreds of MiB of discarded staging.
        self.db.execute('vacuum')
        return dict(counts=counts, vendorDigest=digest)

    def vendors_page(self, after=-1, limit=PAGE_SIZE):
        integer(after, minimum=-1, maximum=750000); integer(limit, minimum=1, maximum=PAGE_SIZE)
        total = self.db.execute('select count(*) from bill_vendors').fetchone()[0]
        rows = self.db.execute('select ordinal,vendor from bill_vendors where ordinal>? order by ordinal limit ?', (after, limit)).fetchall()
        last = rows[-1][0] if rows else after
        more = self.db.execute('select 1 from bill_vendors where ordinal>? limit 1', (last,)).fetchone()
        return dict(total=total, vendors=[dict(vendor=r[1]) for r in rows], nextCursor=last if more else None)

    def warnings_page(self, after=-1, limit=PAGE_SIZE, max_bytes=1024*1024-4096):
        integer(after, minimum=-1, maximum=750000); integer(limit, minimum=1, maximum=PAGE_SIZE)
        rows = self.db.execute('select id,source_rows,reason from bill_warnings where id>? order by id limit ?', (after, limit)).fetchall()
        integer(max_bytes,minimum=512,maximum=1024*1024-4096)
        output=dict(warnings=[],total=self.db.execute('select count(*) from bill_warnings').fetchone()[0],nextCursor=None)
        wire_bytes=len(encoded(output).encode())+128;last=after
        for row_id,source_rows,reason in rows:
            item=dict(rows=source_rows,reason=reason);size=len(encoded(item).encode())+(1 if output['warnings'] else 0)
            if wire_bytes+size>max_bytes:
                if not output['warnings']:raise SnapshotError('bill_limit')
                break
            output['warnings'].append(item);wire_bytes+=size;last=row_id
        more = self.db.execute('select 1 from bill_warnings where id>? limit 1', (last,)).fetchone()
        output['nextCursor']=last if more else None
        return output

    def candidates_page(self, query, after=-1, limit=PAGE_SIZE, max_bytes=1024 * 1024 - 4096):
        query = validate_query(query)
        integer(after, minimum=-1, maximum=750000); integer(limit, minimum=1, maximum=PAGE_SIZE)
        integer(max_bytes, minimum=512, maximum=1024 * 1024 - 4096)
        conditions, params = [], []
        for key in query['references']:
            conditions.append('(reference_key=? and kind=?)'); params.extend([key['invoiceKey'], key['kind']])
        for key in query['amounts']:
            conditions.append('(vendor_key=? and kind=? and amount=?)'); params.extend([key['vendorKey'], key['kind'], key['amount']])
        predicate = '(' + ' or '.join(conditions) + ')' if conditions else '0'
        total = self.db.execute('select count(*) from bill_records where ' + predicate, params).fetchone()[0]
        output = dict(importId=query['importId'], queryDigest=canonical_hash(query), total=total,
                      afterOrdinal=after, nextCursor=None, records=[])
        wire_bytes = len(encoded(output).encode()) + 128
        rows = self.db.execute('select ordinal,record from bill_records where ' + predicate + ' and ordinal>? order by ordinal limit ?', [*params, after, limit])
        last = after
        for ordinal, raw in rows:
            record = {**validate_record(json.loads(raw)), 'id': f'{query["importId"]}:{ordinal}'}
            record_bytes = len(encoded(record).encode()) + (1 if output['records'] else 0)
            if wire_bytes + record_bytes > max_bytes:
                if not output['records']:
                    raise SnapshotError('bill_limit')
                break
            output['records'].append(record)
            wire_bytes += record_bytes
            last = ordinal
        more = self.db.execute('select 1 from bill_records where ' + predicate + ' and ordinal>? limit 1', [*params, last]).fetchone()
        output['nextCursor'] = last if more else None
        return output
