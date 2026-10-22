import json
import sqlite3
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from fixtures.ap_shared.duplicate_cases import PIN, bill


class SourceTests(unittest.TestCase):
    def fixture(self, legacy=False):
        from app.ap_shared.bills.duplicates.source import DuplicateSource
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        db.execute('create table bill_records(ordinal integer primary key,record text)')
        db.executemany('insert into bill_records values(?,?)', [(n, json.dumps(bill(str(n)))) for n in range(3)])
        current = dict(active_import_id=PIN['importId'], import_version=1)
        source = dict(id=PIN['importId'], state='ready', storage_format='rows-v1' if legacy else 'snapshot-v2',
                      file_hash='a' * 64, record_count=3)
        @contextmanager
        def index(import_id, auth):
            self.assertEqual(import_id, PIN['importId'])
            yield SimpleNamespace(db=db), source
        def records(workspace, import_id, after, limit):
            page = [{**json.loads(raw), 'id': f'{import_id}:{n}'} for n, raw in
                    db.execute('select ordinal,record from bill_records where ordinal>? order by ordinal limit ?', (after, limit))]
            last = after + len(page)
            return dict(records=page, recordCount=3, importId=import_id, nextCursor=last if last < 2 else None)
        base = SimpleNamespace(records_page=records, config=SimpleNamespace(workspace_id=PIN['importId']))
        repo = SimpleNamespace(current=lambda: current, source=lambda _: source)
        ops = SimpleNamespace(_check=lambda _: None, repository=repo, _index=index)
        return DuplicateSource(base, ops), current, db, base

    def test_snapshot_and_legacy_are_complete_and_pinned(self):
        for legacy in [False, True]:
            reader, current, _, _ = self.fixture(legacy)
            pin = reader.pin(None)
            first = reader.read_page(pin, -1, 2, None)
            self.assertEqual([r['ordinal'] for r in first['records']], [0, 1])
            self.assertEqual(first['nextOrdinal'], 1)
            last = reader.read_page(pin, 1, 2, None)
            self.assertIsNone(last['nextOrdinal'])
            self.assertEqual([r['ordinal'] for r in reader.members(pin, [0, 2], None)], [0, 2])
            current['import_version'] = 2
            with self.assertRaises(ValueError):
                reader.read_page(pin, -1, 2, None)

    def test_missing_legacy_page_is_not_empty_success(self):
        reader, _, _, base = self.fixture(True)
        pin = reader.pin(None)
        original = base.records_page
        base.records_page = lambda *args: {**original(*args), 'records': []}
        with self.assertRaises(ValueError):
            reader.read_page(pin, -1, 2, None)

    def test_snapshot_evidence_past_one_hundred_thousand_is_not_truncated(self):
        reader, _, db, _ = self.fixture()
        reader.ops.repository.source(PIN['importId'])['record_count'] = 100002
        raw = json.dumps(bill())
        db.executemany('insert into bill_records values(?,?)', ((n, raw) for n in range(3, 100002)))
        pin = reader.pin(None)
        page = reader.read_page(pin, 99999, 3, None)
        self.assertEqual([r['ordinal'] for r in page['records']], [100000, 100001])
        self.assertIsNone(page['nextOrdinal'])
