"""Conservative bill patterns; a suggestion is never proof of double payment."""
from datetime import date
import re
from ...models import MAX_SAFE_CENTS
from ..normalization import vendor_key, invoice_key, trim
from .contracts import RULE_VERSION, canonical_hash

_STEM = re.compile(r'^([0-9]{4,})([A-Z]?)$')
_PAYMENT_WARNING = ('Paid Amount ', 'Amount Due ', 'Credits Applied ', 'Paid On ',
                    'Full Payment Date ', 'Bill status is missing or unrecognized')


def eligible(bill):
    return (type(bill.get('amount')) is int and 0 < bill['amount'] <= MAX_SAFE_CENTS
            and bill.get('kind', 'invoice') == 'invoice'
            and type(bill.get('vendor')) is str and bool(vendor_key(bill['vendor']))
            and type(bill.get('invoiceNumber')) is str and bool(invoice_key(bill['invoiceNumber'])))


def currency_key(value):
    value = value.strip().upper() if type(value) is str else ''
    return value if re.fullmatch('[A-Z]{3}', value) else ''


def invoice_day(bill):
    value = bill.get('invoiceDate', '')
    try:
        return date.fromisoformat(value).toordinal() if len(value) == 10 else None
    except (ValueError, TypeError):
        return None


def identity_warnings(bill):
    parts = str(bill.get('sourceIssues', '')).split('.')
    return sorted(set(p.strip() for p in parts if p.strip() and not p.strip().startswith(_PAYMENT_WARNING)))


def normalized_identity(bill):
    return [vendor_key(bill['vendor']), invoice_key(bill['invoiceNumber']), bill.get('kind', 'invoice'),
            bill.get('invoiceDate', ''), bill['amount'], currency_key(bill.get('currency'))]


def bill_fingerprint(bill):
    return canonical_hash([1, normalized_identity(bill), trim(bill['invoiceNumber'])])


def reference_reasons(left, right):
    a, b = invoice_key(left['invoiceNumber']), invoice_key(right['invoiceNumber'])
    if a == b:
        return ['exact_reference']
    reasons = []
    sa, sb = _STEM.fullmatch(a), _STEM.fullmatch(b)
    if sa and sb and sa[1] == sb[1] and sa[2] != sb[2]:
        reasons.append('trailing_letter')
    if len(a) == len(b) and len(a) >= 4:
        differences = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(differences) == 2:
            x, y = differences
            if y == x + 1 and a[x] in '0123456789' and a[y] in '0123456789' and a[x] == b[y] and a[y] == b[x]:
                reasons.append('digit_transposition')
    return reasons


def classify(left, right):
    if not eligible(left) or not eligible(right) or vendor_key(left['vendor']) != vendor_key(right['vendor']):
        return None
    ca, cb = currency_key(left.get('currency')), currency_key(right.get('currency'))
    if ca and cb and ca != cb:
        return None
    reasons = reference_reasons(left, right)
    if not reasons:
        return None
    exact = 'exact_reference' in reasons
    equal = left['amount'] == right['amount']
    da, db = invoice_day(left), invoice_day(right)
    if not exact and (not equal or da is None or db is None or abs(da - db) > 30):
        return None
    # Routine deliveries often share totals and nearby sequential references.
    # A digit swap needs the same invoice day, unlike a trailing-letter variant.
    if 'digit_transposition' in reasons and da != db:
        return None
    classification = 'exact_pattern' if exact and equal else 'amount_difference' if exact else 'possible_duplicate'
    if not equal:
        reasons.append('different_amount')
    if not ca or not cb:
        reasons.append('currency_unknown')
    if da is None or db is None:
        reasons.append('date_unknown')
    elif da != db:
        reasons.append('different_invoice_dates')
    if normalized_identity(left) == normalized_identity(right):
        classification = 'export_review'
        reasons.append('indistinguishable_identity')
    if identity_warnings(left) or identity_warnings(right):
        classification = 'export_review'
        reasons.append('ambiguous_source')
    # Same-date exact economic identities are ambiguous with this export, not
    # evidence that the import-scoped IDs represent independent BILL objects.
    return dict(classification=classification, strength='possible', reasons=sorted(set(reasons)))


def finding_key(members, classification, warnings, rule_version=RULE_VERSION):
    return canonical_hash([1, rule_version, sorted(members), classification, sorted(set(warnings))])
