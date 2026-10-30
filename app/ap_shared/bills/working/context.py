"""Source-bound historical summaries; missing coverage is never a negative result."""
from datetime import date
import json
from ..contracts import SnapshotError


def context_keys(vendor, amount, day):
    # Corroboration uses the earlier date of a pair at most three days apart.
    days = range(max(1, day-3), day+1)
    months = sorted({date.fromordinal(d).replace(day=1).toordinal() for d in days})
    return [(vendor, month) for month in months], [(vendor, amount, d) for d in days]


class HistoryContext:
    def __init__(self, db):
        self.db = db

    def profile(self, vendor_key: str, month_ordinal: int) -> dict:
        row = self.db.execute('select value from profiles where vendor=? and month=?',
                              (vendor_key, month_ordinal)).fetchone()
        if row is None:
            raise SnapshotError('bill_incomplete')
        value = json.loads(row[0])
        required = {'periodStart', 'periodEnd', 'distinctReferences', 'shapes', 'established'}
        if type(value) is not dict or set(value) != required:
            raise SnapshotError('bill_invalid_archive')
        if (value['periodStart'] != date.fromordinal(max(1, month_ordinal-365)).isoformat()
                or value['periodEnd'] != date.fromordinal(max(1, month_ordinal-1)).isoformat()
                or type(value['distinctReferences']) is not int or value['distinctReferences'] < 0
                or type(value['shapes']) is not list or len(value['shapes']) > 3
                or type(value['established']) is not bool):
            raise SnapshotError('bill_invalid_archive')
        shapes = value['shapes']
        for shape in shapes:
            if (type(shape) is not dict or set(shape) != {'shape', 'references'}
                    or type(shape['shape']) is not str or not shape['shape']
                    or type(shape['references']) is not int or shape['references'] < 3):
                raise SnapshotError('bill_invalid_archive')
        total = sum(v['references'] for v in shapes)
        if (len({v['shape'] for v in shapes}) != len(shapes) or total > value['distinctReferences']
                or shapes != sorted(shapes, key=lambda v: (-v['references'], v['shape']))
                or value['established'] != (value['distinctReferences'] >= 20 and total*10 >= value['distinctReferences']*9)):
            raise SnapshotError('bill_invalid_archive')
        return value

    def recurring(self, vendor_key: str, amount: int, day: int) -> bool:
        row = self.db.execute('select value from recurrences where vendor=? and amount=? and day=?',
                              (vendor_key, amount, day)).fetchone()
        if row is None:
            raise SnapshotError('bill_incomplete')
        if type(row[0]) is not int or row[0] not in (0, 1):
            raise SnapshotError('bill_invalid_archive')
        return bool(row[0])
