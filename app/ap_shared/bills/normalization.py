"""Exact lookup and numeric semantics shared with the existing JS importer."""
from datetime import date
import re

# ECMAScript whitespace, not Python's broader Unicode whitespace definition.
SPACE = r'[\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]'
_space = re.compile(SPACE + '+')
_edges = re.compile('^' + SPACE + '+|' + SPACE + '+$')
_number = r'((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?)'
_money = re.compile(r'^(?:\(\$?' + _number + r'\)|([+-]?)(?:\$)?' + _number + r'(-?)|\$([+-])' + _number + r')$')


def trim(value):
    return _edges.sub('', str(value))


def vendor_key(value):
    return _space.sub(' ', trim(value).lower())


def invoice_key(value):
    return _space.sub('', trim(value).upper())


def header_key(value):
    return re.sub('[^a-z0-9]', '', trim(value).lower())


def ordinal(value):
    return int(value) if re.fullmatch('[0-9]+', value) and len(value) < 17 and int(value) <= 9007199254740991 else None


def parse_cents(value):
    raw = _space.sub('', str(value))
    match = _money.fullmatch(raw)
    if not match:
        return None
    parenthesized, sign, number, trailing, dollar_sign, dollar_number = match.groups()
    if sign and trailing:
        return None
    whole, _, decimal = (parenthesized or number or dollar_number).replace(',', '').partition('.')
    if len(whole) > 14:
        return None
    result = int(whole) * 100 + int(decimal.ljust(2, '0'))
    if result > 9007199254740991:
        return None
    return -result if parenthesized or sign == '-' or trailing == '-' or dollar_sign == '-' else result


def date_iso(value):
    raw = trim(value)
    parts = re.fullmatch(r'([0-9]{1,2})/([0-9]{1,2})/([0-9]{2}|[0-9]{4})', raw)
    if parts:
        month, day, year = parts.groups()
        raw = f'{"20" + year if len(year) == 2 else year}-{int(month):02d}-{int(day):02d}'
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw):
        return ''
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return ''
