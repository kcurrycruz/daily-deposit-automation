"""Synthetic BILL data only. No company export is a test fixture."""
import csv
import io

HEADERS = ['Active?', 'Vendor Name', 'Vendor Id', 'Invoice #', 'Invoice Date', 'Due Date',
           'GL Posting Date', 'Amount', 'Paid Amount', 'Amount Due', 'Credits Applied',
           'Status', 'Paid On', 'Full Payment Date', 'Currency', 'Created',
           'Total Line Items', 'Bill Line Item Order', 'Bill Line Item Amount']


def export(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    writer.writerow(HEADERS)
    for overrides in rows:
        record = {'Active?': 'Active', 'Vendor Name': 'Synthetic & Co.', 'Vendor Id': 'vendor-1',
                  'Invoice #': '00042-A', 'Invoice Date': '10/01/2026', 'Amount': '138.00',
                  'Paid Amount': '0', 'Credits Applied': '0', 'Status': 'Open',
                  'Total Line Items': '1', 'Bill Line Item Order': '0', 'Bill Line Item Amount': '138.00'}
        record.update(overrides)
        writer.writerow([record.get(h, '') for h in HEADERS])
    return stream.getvalue()
