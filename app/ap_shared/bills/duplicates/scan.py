"""Resumable, disk-backed pattern scan; no vendor-wide all-pairs search."""
import hashlib
import json
import re
import sqlite3
from ...models import validate_record
from ..normalization import vendor_key, invoice_key
from .contracts import (DuplicateError, RULE_VERSION, MAX_FINDINGS, MAX_BYTES, encoded,
                        canonical_hash, validate_pin,validate_finding_evidence)
from .rules import eligible, classify, bill_fingerprint, normalized_identity, identity_warnings, invoice_day, currency_key
from .vendor_patterns import compact_reference,reference_shape
from .vendor_scan import VendorCandidates


class DuplicateScan:
    def __init__(self, connection, pin, monotonic):
        self.db, self.pin, self.clock = connection, validate_pin(pin), monotonic
        self.read = self.eligible = self.probes = 0
        self.input_done = self.done = False
        self.after = -1
        self.current = self.pending = None
        self.db.executescript('''
          pragma cache_size=-8192; pragma temp_store=FILE;
          pragma journal_mode=MEMORY; pragma synchronous=OFF;
          create table scan_records(ordinal integer primary key,ident text,fp text,warn text,raw_ref text);
          create index scan_identity on scan_records(ident,ordinal);
          create table nodes(ident text primary key,ordinal integer unique,n integer,
            vendor text,ref text,amount integer,currency text,stem text,day integer,warning integer,preview text,compact text,shape text);
          create index node_ref on nodes(vendor,ref,ordinal);
          create index node_stem on nodes(vendor,amount,stem,ordinal);
          create table fingerprints(ident text,fp text,n integer,primary key(ident,fp));
          create table warning_keys(ident text,warn text,primary key(ident,warn));
          create table findings(id integer primary key,key text unique,classification text,strength text,
            reasons text,latest_date text,member_count integer,preview text,search text,evidence text not null);
          create table members(finding_id integer,ordinal integer,fp text,primary key(finding_id,ordinal));
          create table scan_meta(key text primary key,value text not null);
        ''')
        self.vendor_candidates=VendorCandidates(self)
        self.db.execute('insert into scan_meta values(?,?)', ('pin', encoded(pin)))
        self.db.commit()

    def _size(self):
        if self.db.execute('pragma page_count').fetchone()[0] * self.db.execute('pragma page_size').fetchone()[0] > MAX_BYTES:
            raise DuplicateError('duplicate_limit')

    def ingest(self, records, deadline=float('inf')):
        if self.input_done or len(records) > 5000:
            raise DuplicateError('duplicate_invalid_source')
        consumed=0
        for item in records:
            if self.clock()>=deadline:break
            if type(item['ordinal']) is not int or item['ordinal'] != self.read or self.read >= self.pin['recordCount']:
                raise DuplicateError('duplicate_invalid_source')
            value = validate_record(item['bill']); ordinal = self.read; self.read += 1;consumed+=1
            if not eligible(value):
                continue
            self.eligible += 1
            ident = canonical_hash(normalized_identity(value)); fp = bill_fingerprint(value)
            issues = identity_warnings(value); warn = canonical_hash(issues) if issues else ''
            vk, ref = vendor_key(value['vendor']), invoice_key(value['invoiceNumber'])
            stem = re.fullmatch(r'([0-9]{4,})[A-Z]?', ref)
            preview = {k: value.get(k, '') for k in ('vendor', 'invoiceNumber', 'amount', 'invoiceDate', 'currency')}
            preview.update(kind='invoice', sourceIssues='. '.join(issues))
            self.db.execute('insert into scan_records values(?,?,?,?,?)', (ordinal, ident, fp, warn, value['invoiceNumber']))
            self.db.execute('''insert into nodes values(?,?,?,?,?,?,?,?,?,?,?,?,?)
              on conflict(ident) do update set n=n+1,warning=max(warning,excluded.warning)''',
                (ident, ordinal, 1, vk, ref, value['amount'], currency_key(value.get('currency')),
                 stem[1] if stem else '', invoice_day(value), bool(issues), encoded(preview),compact_reference(value['invoiceNumber']),reference_shape(value['invoiceNumber'])))
            self.db.execute('insert into fingerprints values(?,?,1) on conflict(ident,fp) do update set n=n+1', (ident, fp))
            if warn:
                self.db.execute('insert or ignore into warning_keys values(?,?)', (ident, warn))
        self._size(); self.db.commit()
        return consumed

    def finish_input(self):
        if self.read != self.pin['recordCount']:
            raise DuplicateError('duplicate_invalid_source')
        self.input_done = True

    def _node(self, row):
        names = 'ident ordinal n vendor ref amount currency stem day warning preview compact shape'.split()
        return dict(zip(names, row))

    def _next_node(self):
        row = self.db.execute('select * from nodes where ordinal>? order by ordinal limit 1', (self.after,)).fetchone()
        if row is None:
            self.done = True
            return
        node = self._node(row)
        modes = [('exact', node['ref'])]
        if node['day'] is not None:
            if node['stem']:
                modes.append(('stem', node['stem']))
            variants = set()
            if len(node['ref']) >= 4:
                ref = node['ref']
                for i in range(len(ref) - 1):
                    if ref[i] != ref[i + 1] and ref[i] in '0123456789' and ref[i + 1] in '0123456789':
                        variants.add(ref[:i] + ref[i + 1] + ref[i] + ref[i + 2:])
            modes.extend(('swap', ref) for ref in sorted(variants))
        self.current = dict(node=node, modes=modes, mode=0, after=node['ordinal'])
        if node['n'] > 1:
            evidence = classify(json.loads(node['preview']), json.loads(node['preview']))
            self._begin([node], evidence)

    def _next_pair(self):
        cur = self.current; node = cur['node']
        while cur['mode'] < len(cur['modes']):
            mode, key = cur['modes'][cur['mode']]
            if mode == 'stem':
                sql = '''select * from nodes indexed by node_stem where vendor=? and amount=? and stem=?
                         and ordinal>? and ref<>? and day between ? and ? order by ordinal limit 1'''
                params = (node['vendor'], node['amount'], key, cur['after'], node['ref'], node['day'] - 30, node['day'] + 30)
            elif mode == 'swap':
                sql = '''select * from nodes indexed by node_ref where vendor=? and ref=?
                         and amount=? and day=? and ordinal>? order by ordinal limit 1'''
                params = (node['vendor'], key, node['amount'], node['day'], cur['after'])
            else:
                sql = 'select * from nodes indexed by node_ref where vendor=? and ref=? and ordinal>? order by ordinal limit 1'
                params = (node['vendor'], key, cur['after'])
            raw = self.db.execute(sql, params).fetchone()
            self.probes += 1
            if raw is None:
                cur['mode'] += 1; cur['after'] = node['ordinal']
                return
            other = self._node(raw); cur['after'] = other['ordinal']
            evidence = classify(json.loads(node['preview']), json.loads(other['preview']))
            if evidence:
                if node['n'] > 1 or other['n'] > 1 or node['warning'] or other['warning']:
                    evidence['classification'] = 'export_review'
                    evidence['reasons'] = sorted(set(evidence['reasons'] + ['ambiguous_source']))
                self._begin([node, other], evidence)
            return
        if self.vendor_candidates.step(cur):
            self.after = node['ordinal']; self.current = None

    def _begin(self, nodes, evidence):
        if self.db.execute('select count(*) from findings').fetchone()[0] >= MAX_FINDINGS:
            raise DuplicateError('duplicate_limit')
        ids = [n['ident'] for n in nodes]; placeholders = ','.join('?' for _ in ids)
        rows = self.db.execute('select r.ordinal,r.raw_ref,n.preview from scan_records r join nodes n on n.ident=r.ident where r.ident in (' +
                               placeholders + ') order by r.ordinal limit 2', ids).fetchall()
        previews = [{**{k: json.loads(raw)[k] for k in ('vendor', 'amount', 'invoiceDate', 'currency')},
                     'ordinal': ordinal, 'invoiceNumber': ref} for ordinal, ref, raw in rows]
        latest = max((json.loads(n['preview'])['invoiceDate'] for n in nodes), default='')
        search = ' '.join([n['vendor'] for n in nodes] + [n['ref'] for n in nodes]).casefold()
        days=[n['day'] for n in nodes]
        gap=max(days)-min(days) if all(d is not None for d in days) else None
        detail=evidence.get('evidence',dict(version=1,dateGapDays=gap,
            referenceReuse='exact_reference' in evidence['reasons'] and gap is not None and gap>30,profiles=[]))
        validate_finding_evidence(detail,evidence['classification'],previews,sum(n['n'] for n in nodes))
        result = self.db.execute('insert into findings values(NULL,NULL,?,?,?,?,?,?,?,?)',
            (evidence['classification'], evidence['strength'], encoded(evidence['reasons']), latest,
             sum(n['n'] for n in nodes), encoded(previews), search,encoded(detail)))
        hasher = hashlib.sha256(('[1,' + encoded(RULE_VERSION) + ',[').encode())
        fps = self.db.execute('select fp,sum(n) from fingerprints where ident in (' + placeholders + ') group by fp order by fp', ids)
        self.pending = dict(ids=ids, placeholders=placeholders, id=result.lastrowid, evidence=evidence,
                            phase='fps', cursor=fps, first=True, hasher=hasher)

    def _pending_step(self):
        p = self.pending; row = p['cursor'].fetchone(); self.probes += 1
        if row is not None:
            if p['phase'] in ('fps', 'warnings'):
                if not p['first']:
                    p['hasher'].update(b',')
                p['hasher'].update(encoded(list(row) if p['phase'] == 'fps' else row[0]).encode())
                p['first'] = False
            else:
                self.db.execute('insert into members values(?,?,?)', (p['id'], row[0], row[1]))
            return
        if p['phase'] == 'fps':
            p['hasher'].update(('],' + encoded(p['evidence']['classification']) + ',[').encode())
            p['cursor'] = self.db.execute('select distinct warn from warning_keys where ident in (' +
                                          p['placeholders'] + ') order by warn', p['ids'])
            p['phase'] = 'warnings'; p['first'] = True
        elif p['phase'] == 'warnings':
            p['hasher'].update(b']]')
            key = p['hasher'].hexdigest()
            existing = self.db.execute('select id from findings where key=?', (key,)).fetchone()
            if existing:
                self.db.execute('delete from findings where id=?', (p['id'],)); self.pending = None
                return
            self.db.execute('update findings set key=? where id=?', (key, p['id']))
            p['cursor'] = self.db.execute('select ordinal,fp from scan_records where ident in (' +
                                         p['placeholders'] + ') order by ordinal', p['ids'])
            p['phase'] = 'members'
        else:
            self.pending = None

    def step(self, deadline, max_probes=10000):
        if not self.input_done or type(max_probes) is not int or not 1 <= max_probes <= 10000:
            raise DuplicateError('duplicate_invalid_source')
        used = 0
        self.db.set_progress_handler(lambda: 1 if self.clock() >= deadline else 0, 2000)
        try:
            while not self.done and used < max_probes and self.clock() < deadline:
                if self.pending:
                    self._pending_step()
                elif self.current:
                    self._next_pair()
                else:
                    self._next_node(); self.probes += 1
                used += 1
            self.db.commit(); self._size()
        except sqlite3.OperationalError:
            # An interrupted SQLite aggregate cannot be represented as a complete
            # result. Restart rather than publishing a partially consumed query.
            raise DuplicateError('duplicate_restart') from None
        finally:
            self.db.set_progress_handler(None, 0)
        return dict(done=self.done, probes=self.probes, used=used)

    def finish(self):
        if not self.done or self.pending:
            raise DuplicateError('duplicate_unavailable')
        counts = dict(recordCount=self.read, eligibleRecords=self.eligible, excludedRecords=self.read - self.eligible,
                      findingCount=self.db.execute('select count(*) from findings').fetchone()[0], probes=self.probes)
        self.db.execute('insert or replace into scan_meta values(?,?)', ('counts', encoded(counts)))
        self.db.commit()
        return counts
