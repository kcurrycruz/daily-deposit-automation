"""Synthetic bills only; never copy production financial records into tests."""
from copy import deepcopy

PIN = dict(importId='00000000-0000-4000-8000-000000000001',
           importVersion=1, sourceDigest='a' * 64, storageFormat='snapshot-v2', recordCount=2)


def bill(reference='271712', *, amount=129981, vendor='Synthetic Foods',
         invoice_date='2026-10-01', currency='USD', **changes):
    return dict(id='source-1', vendor=vendor, invoiceNumber=reference, amount=amount,
                kind='invoice', invoiceDate=invoice_date, currency=currency,
                sourceRows='2', sourceIssues='', **changes)


def changed(value, **changes):
    return {**deepcopy(value), **changes}
