"""Semantic protections derived only from authoritative current saved evidence."""
import re
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
    def __init__(self, base, authorize, duplicate_members_reader=None):
        self.base, self.authorize = base, authorize
        self.duplicate_members_reader = duplicate_members_reader

    def _epoch(self, auth):
        self.authorize(auth); self.base._private_bucket()
        home = self.base._one(self.base.client.table('ap_workspaces').select('bill_protection_epoch').eq('id', self.base.config.workspace_id))
        return integer(home['bill_protection_epoch'], minimum=0)

    def _pages(self, table, key, auth):
        after = None; count = 0
        while True:
            self.authorize(auth); self.base._private_bucket()
            query = self.base._table(table).order(key).limit(500)
            if after is not None:
                query = query.gt(key, after)
            rows = query.execute().data
            if type(rows) is not list or len(rows) > 500:
                raise SnapshotError('bill_incomplete')
            for row in rows:
                value = row.get(key)
                if type(value) is not str or (after is not None and value <= after):
                    raise SnapshotError('bill_incomplete')
                after = value; count += 1
                if count > MAX_RECORDS:
                    raise SnapshotError('bill_limit')
                yield row
            if len(rows) < 500:
                return

    def snapshot(self, source_import_id: str, auth) -> dict:
        require_uuid(source_import_id)
        before = self._epoch(auth)
        source = self.base.import_info(self.base.config.workspace_id, source_import_id)
        if source['state'] != 'ready':
            raise SnapshotError('bill_incomplete')
        mappings = {r['vendor']: r['bill_vendor'] for r in self._pages('ap_vendor_mappings', 'vendor', auth)}
        protections = ProtectionSet()
        for statement in self._pages('ap_statements', 'id', auth):
            self.authorize(auth)
            revision = self.base._one(self.base._table('ap_statement_revisions').eq('id', require_uuid(statement['current_revision_id'])))
            if revision['statement_id'] != statement['id']:
                raise SnapshotError('bill_incomplete')
            protections.add_statement(statement, revision, mappings)
        for review in self._pages('ap_duplicate_reviews', 'key', auth):
            if review['decision'] == 'not_duplicate':
                continue
            if self.duplicate_members_reader is None:
                raise SnapshotError('bill_incomplete')
            self.authorize(auth)
            evidence = self.duplicate_members_reader(review, auth)
            protections.add_duplicate({**review, 'memberCount': evidence['memberCount']}, evidence['members'])
        after = self._epoch(auth)
        if before != after:
            raise SnapshotError('bill_conflict')
        return dict(epoch=after, digest=protections.digest(), protections=protections)
