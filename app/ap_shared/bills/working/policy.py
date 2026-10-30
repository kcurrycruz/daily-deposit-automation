"""Pure coverage rules. Export payment fields guide retention, not settlement."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from ...models import MAX_SAFE_CENTS

POLICY_VERSION = 'ap-active-range-v1'
REASONS = ('all', 'recent', 'date_unknown', 'unsettled', 'follow_up', 'non_invoice')


def _date(value):
    if type(value) is not str or len(value) != 10:
        return None
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except ValueError:
        return None


def _cutoff(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        if day.year <= 1:
            raise ValueError('The active BILL date is outside the supported range.') from None
        return day.replace(year=day.year - 1, day=28)


def validate_policy(value):
    if (type(value) is not dict or set(value) != {'version', 'mode', 'asOfDate', 'cutoffDate'}
            or value['version'] != POLICY_VERSION or value['mode'] not in ('all', 'last_12_months')):
        raise ValueError('Invalid active BILL range policy.')
    day = _date(value['asOfDate'])
    if day is None or value['cutoffDate'] != ('' if value['mode'] == 'all' else _cutoff(day).isoformat()):
        raise ValueError('Invalid active BILL range dates.')
    return dict(value)


def make_policy(mode: str, now: datetime) -> dict:
    if (mode not in ('all', 'last_12_months') or not isinstance(now, datetime)
            or now.tzinfo is None or now.utcoffset() is None):
        raise ValueError('A valid mode and aware server clock are required.')
    day = now.astimezone(ZoneInfo('America/New_York')).date()
    return validate_policy(dict(version=POLICY_VERSION, mode=mode, asOfDate=day.isoformat(),
                                cutoffDate='' if mode == 'all' else _cutoff(day).isoformat()))


def _cents(value):
    return type(value) is int and 0 <= value <= MAX_SAFE_CENTS


def _settled_for_retention(record):
    amount, due = record.get('amount'), record.get('reportedAmountDue')
    if (not _cents(amount) or amount == 0 or record.get('status') != 'PaidInFull'
            or record.get('sourceIssues')):
        return False
    if due is not None:
        return type(due) is int and due == 0
    paid, credit = record.get('reportedPaidAmount'), record.get('reportedCreditAmount')
    if not _cents(paid) or (credit is not None and not _cents(credit)):
        return False
    return paid + (0 if credit is None else credit) == amount


def retention_reasons(record: dict, policy: dict, *, protected: bool = False) -> list[str]:
    policy = validate_policy(policy)
    if type(record) is not dict or type(protected) is not bool:
        raise ValueError('A valid BILL record and protection flag are required.')
    if policy['mode'] == 'all':
        return ['all']
    reasons = []
    day = _date(record.get('invoiceDate'))
    if day is None:
        reasons.append('date_unknown')
    elif day.isoformat() >= policy['cutoffDate']:
        reasons.append('recent')
    if not _settled_for_retention(record):
        reasons.append('unsettled')
    if protected:
        reasons.append('follow_up')
    if record.get('kind', 'invoice') != 'invoice':
        reasons.append('non_invoice')
    return reasons
