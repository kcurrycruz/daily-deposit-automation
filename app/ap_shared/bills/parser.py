"""CSV input is streamed into temporary SQLite staging, never a row list."""
import csv
import json
import time
from ..models import validate_record
from .contracts import MAX_COLUMNS, MAX_FIELD_BYTES, MAX_SOURCE_ROWS, SnapshotError
from .normalization import trim, header_key, vendor_key, invoice_key, parse_cents, date_iso, ordinal

BILL_COLUMNS = ['Active?', 'Vendor Name', 'Vendor Id', 'Invoice #', 'Invoice Date', 'Due Date',
                'GL Posting Date', 'Amount', 'Paid Amount', 'Amount Due', 'Credits Applied',
                'Status', 'Paid On', 'Full Payment Date', 'Currency', 'Created', 'Total Line Items']


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class CsvStage:
    def __init__(self, connection, csv_path):
        self.db = connection
        self.owns_file = not hasattr(csv_path, 'read')
        self.stream = open(csv_path, encoding='utf-8-sig', newline='') if self.owns_file else csv_path
        self.done = False
        self.source_count = 0
        self.excluded = 0
        csv.field_size_limit(MAX_FIELD_BYTES)
        self.reader = csv.reader(self.stream, strict=True)
        try:
            self.header = next(self.reader)
            if self.header:
                self.header[0] = self.header[0].removeprefix('\ufeff')
            self.names = [header_key(h) for h in self.header]
            if not self.names or len(self.names) > MAX_COLUMNS or len(set(self.names)) != len(self.names) or any(len(h.encode('utf8')) > MAX_FIELD_BYTES for h in self.header):
                raise ValueError
            self.positions = {name: i for i, name in enumerate(self.names)}
            self.native = all(n in self.names for n in ['vendorname', 'invoice', 'amount'])
            if not self.native and not all(n in self.names for n in ['vendor', 'invoicenumber', 'amount']):
                raise ValueError
            self.has_lines = self.native and all(header_key(c) in self.positions for c in ['Total Line Items', 'Bill Line Item Order', 'Bill Line Item Amount'])
            self.db.executescript('''
              create table bill_stage(source_row integer primary key,group_key text,record text,issues text,
                line_count integer,line_order integer,line_amount integer,consistent text);
              create index bill_stage_group on bill_stage(group_key,source_row);
              create table bill_warnings(id integer primary key,source_rows text not null,reason text not null);
              create table bill_meta(key text primary key,value text not null);
            ''')
            self._meta('format', 'bill-native' if self.native else 'template')
            self._meta('hasLines', self.has_lines)
        except (ValueError, csv.Error, UnicodeError, StopIteration):
            self.close()
            raise SnapshotError('bill_invalid_archive') from None

    def _meta(self, key, value):
        self.db.execute('insert or replace into bill_meta values(?,?)', (key, encoded(value)))

    def _get(self, row, column):
        position = self.positions.get(header_key(column))
        return trim(row[position]) if position is not None else ''

    def close(self):
        if self.owns_file:
            self.stream.close()

    def read_step(self, max_rows=5000, deadline=float('inf')):
        if type(max_rows) is not int or not 1 <= max_rows <= 5000:
            raise SnapshotError('bill_limit')
        processed = 0
        try:
            while not self.done and processed < max_rows and time.monotonic() < deadline:
                row = next(self.reader, None)
                if row is None:
                    self.done = True
                    break
                if not any(trim(v) for v in row):
                    continue
                self.source_count += 1
                processed += 1
                if self.source_count > MAX_SOURCE_ROWS or len(row) != len(self.header) or any(len(v.encode('utf8')) > MAX_FIELD_BYTES for v in row):
                    raise SnapshotError('bill_limit' if self.source_count > MAX_SOURCE_ROWS else 'bill_invalid_archive')
                source_row = self.source_count + 1
                self._native_row(row, source_row) if self.native else self._template_row(row, source_row)
            self._meta('sourceRowCount', self.source_count)
            self._meta('excludedRowCount', self.excluded)
            self.db.commit()
            return dict(done=self.done, sourceRowCount=self.source_count, checkpoint=self.source_count)
        except (csv.Error, UnicodeError, ValueError) as error:
            self.db.rollback()
            if isinstance(error, SnapshotError):
                raise
            raise SnapshotError('bill_invalid_archive') from None

    def _native_row(self, row, source_row):
        get = lambda c: self._get(row, c)
        active, vendor, reference = get('Active?'), get('Vendor Name'), get('Invoice #')
        if active in ('Inactive', 'DraftDeleted') or not vendor or not reference:
            self.excluded += 1
            reason = ('Excluded: vendor name or invoice number is missing.' if not vendor or not reference
                      else f'Excluded: export marks this bill {active}.')
            self.db.execute('insert into bill_warnings(source_rows,reason) values(?,?)', (str(source_row), reason))
            return
        issues = []

        def money(column, required=False, signed=False):
            raw = get(column)
            result = parse_cents(raw)
            if (raw or required) and result is None:
                issues.append(f'{column} is missing or invalid.')
            if not signed and result is not None and result < 0:
                issues.append(f'{column} is negative; review the source transaction.')
            return result

        def day(column):
            raw = get(column)
            result = date_iso(raw)
            if raw and not result:
                issues.append(f'{column} is invalid.')
            return result

        if active != 'Active':
            issues.append('Active status is not confirmed by this export.')
        status = get('Status')
        if status not in ('Open', 'PaidInFull', 'Scheduled'):
            issues.append('Bill status is missing or unrecognized.')
        amount, invoice_date = money('Amount', True), day('Invoice Date')
        if not invoice_date:
            issues.append('Invoice date is not established.')
        record = dict(id=f'bill-native-{source_row}', vendor=vendor, invoiceNumber=reference, amount=amount,
                      kind='invoice', currency=get('Currency'), status=status, invoiceDate=invoice_date,
                      reportedPaidAmount=money('Paid Amount'), reportedAmountDue=money('Amount Due'),
                      reportedCreditAmount=money('Credits Applied'), reportedPaidOn=day('Paid On'),
                      reportedFullPaymentDate=day('Full Payment Date'), clearedPaymentAmount=None,
                      scheduledAmount=None, creditAmount=None, paymentDate='', comparisonScope='invoice-only',
                      sourceRows=str(source_row), sourceIssues='')
        line_amount = money('Bill Line Item Amount', True, True) if self.has_lines else None
        validate_record({**record, 'sourceIssues': ' '.join(issues)})
        key = encoded([vendor_key(vendor), get('Vendor Id'), invoice_key(reference), invoice_date or get('Invoice Date')])
        self.db.execute('insert into bill_stage values(?,?,?,?,?,?,?,?)',
                        (source_row, key, encoded(record), encoded(issues), ordinal(get('Total Line Items')),
                         ordinal(get('Bill Line Item Order')), line_amount, encoded([get(c) for c in BILL_COLUMNS])))

    def _template_row(self, row, source_row):
        get = lambda c: self._get(row, c)
        amount = parse_cents(get('amount'))
        if not get('vendor') or not get('invoiceNumber') or amount is None:
            raise SnapshotError('bill_invalid_archive')
        record = dict(id=get('id') or f'csv-{source_row-2}', vendor=get('vendor'), invoiceNumber=get('invoiceNumber'),
                      amount=amount, kind=get('kind') or 'invoice', currency=get('currency') or 'USD',
                      paymentDate=date_iso(get('paymentDate')), status=get('status'))
        if get('paymentDate') and not record['paymentDate']:
            raise SnapshotError('bill_invalid_archive')
        for name in ('clearedPaymentAmount', 'scheduledAmount', 'creditAmount'):
            parsed = parse_cents(get(name))
            if get(name) and parsed is None:
                raise SnapshotError('bill_invalid_archive')
            record[name] = parsed if parsed is not None else 0
        validate_record(record)
        self.db.execute('insert into bill_stage values(?,?,?,?,?,?,?,?)',
                        (source_row, str(source_row), encoded(record), '[]', None, None, None, '[]'))
