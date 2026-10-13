import { parseCSV, importRecords, cents, dateISO, vendorKey, invoiceKey } from './core.mjs';

const headerKey = value => value.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
const ordinal = value => /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : null;

// Native exports repeat bill-level amounts on each line. Never sum those amounts.
// Payment fields are reported evidence, not proof of settlement or a historical balance.
export function importBillSource(text) {
  const [header, ...rows] = parseCSV(text);
  if (!header) throw Error('CSV is empty.');
  const names = header.map(headerKey);
  if (new Set(names).size !== names.length) throw Error('Duplicate CSV column headers. Use an unmodified BILL export or the app template.');
  const native = ['vendorname', 'invoice', 'amount'].every(name => names.includes(name));
  if (!native) {
    if (names.includes('vendorname') && !names.includes('invoice')) throw Error('This is a vendor directory. Import the Bills CSV export to compare invoices.');
    const records = importRecords(text);
    return { records, summary: { format: 'template', inputRows: rows.length, collapsedRows: 0, excludedRows: 0, issues: [] } };
  }
  const get = (row, column) => (row[names.indexOf(headerKey(column))] ?? '').trim();
  const summary = { format: 'bill-native', inputRows: rows.length, collapsedRows: 0, excludedRows: 0, issues: [] };
  const groups = new Map();
  const hasLines = ['Total Line Items', 'Bill Line Item Order', 'Bill Line Item Amount'].every(column => names.includes(headerKey(column)));
  const report = (sourceRows, reason) => summary.issues.push({ rows: sourceRows, reason });
  rows.forEach((row, index) => {
    const sourceRow = index + 2;
    if (row.length !== header.length) throw Error(`CSV row ${sourceRow} has a different column count. Export the file again without editing it.`);
    const active = get(row, 'Active?');
    const vendor = get(row, 'Vendor Name'), invoiceNumber = get(row, 'Invoice #');
    if (['Inactive', 'DraftDeleted'].includes(active) || !vendor || !invoiceNumber) {
      summary.excludedRows++;
      report(String(sourceRow), !vendor || !invoiceNumber ? 'Excluded: vendor name or invoice number is missing.' : `Excluded: export marks this bill ${active}.`);
      return;
    }
    const issues = [];
    const readMoney = (column, required = false, signed = false) => {
      const raw = get(row, column), value = cents(raw);
      if ((raw || required) && value == null) issues.push(`${column} is missing or invalid.`);
      if (!signed && value != null && value < 0) issues.push(`${column} is negative; review the source transaction.`);
      return value;
    };
    const readDate = column => {
      const raw = get(row, column), value = dateISO(raw);
      if (raw && !value) issues.push(`${column} is invalid.`);
      return value;
    };
    if (active !== 'Active') issues.push('Active status is not confirmed by this export.');
    const status = get(row, 'Status');
    if (!['Open', 'PaidInFull', 'Scheduled'].includes(status)) issues.push('Bill status is missing or unrecognized.');
    const amount = readMoney('Amount', true), invoiceDate = readDate('Invoice Date');
    if (!invoiceDate) issues.push('Invoice date is not established.');
    const record = {
      id: `bill-native-${sourceRow}`, vendor, invoiceNumber, amount, kind: 'invoice',
      currency: get(row, 'Currency'), status, invoiceDate,
      reportedPaidAmount: readMoney('Paid Amount'), reportedAmountDue: readMoney('Amount Due'),
      reportedCreditAmount: readMoney('Credits Applied'), reportedPaidOn: readDate('Paid On'),
      reportedFullPaymentDate: readDate('Full Payment Date'),
      clearedPaymentAmount: null, scheduledAmount: null, creditAmount: null, paymentDate: '',
      comparisonScope: 'invoice-only', sourceRows: String(sourceRow), sourceIssues: '',
    };
    const entry = { row, record, issues, count: ordinal(get(row, 'Total Line Items')),
      order: ordinal(get(row, 'Bill Line Item Order')), lineAmount: hasLines ? readMoney('Bill Line Item Amount', true, true) : null };
    const key = JSON.stringify([vendorKey(vendor), get(row, 'Vendor Id'), invoiceKey(invoiceNumber), invoiceDate || get(row, 'Invoice Date')]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(entry);
  });
  const records = [];
  const billColumns = ['Active?', 'Vendor Name', 'Vendor Id', 'Invoice #', 'Invoice Date', 'Due Date', 'GL Posting Date',
    'Amount', 'Paid Amount', 'Amount Due', 'Credits Applied', 'Status', 'Paid On', 'Full Payment Date', 'Currency', 'Created', 'Total Line Items'];
  for (const group of groups.values()) {
    const first = group[0], sourceRows = group.map(entry => entry.record.sourceRows).join(',');
    const consistent = billColumns.every(column => new Set(group.map(entry => get(entry.row, column))).size === 1);
    const ordered = [...group].sort((a, b) => a.order - b.order);
    const complete = hasLines && first.count > 0 && first.count === group.length && group.every(entry => entry.count === first.count)
      && ordered.every((entry, index) => entry.order === index);
    const lineSum = group.reduce((sum, entry) => sum + BigInt(entry.lineAmount ?? 0), 0n);
    const sumsAgree = group.every(entry => entry.lineAmount != null) && first.record.amount != null && lineSum === BigInt(first.record.amount);
    const safe = consistent && complete && sumsAgree && group.every(entry => !entry.issues.length);
    if (safe) {
      records.push({ ...first.record, sourceRows });
      summary.collapsedRows += group.length - 1;
      continue;
    }
    let groupIssue = '';
    if (group.length > 1) groupIssue = 'Repeated vendor/reference rows do not establish one complete, consistent bill. Review the candidates.';
    else if (hasLines && (!complete || !sumsAgree)) groupIssue = 'Line-item detail is incomplete or does not agree with the bill total.';
    for (const entry of group) {
      const issues = [...entry.issues, ...(groupIssue ? [groupIssue] : [])];
      entry.record.sourceIssues = [...new Set(issues)].join(' ');
      records.push(entry.record);
      if (entry.record.sourceIssues) report(entry.record.sourceRows, entry.record.sourceIssues);
    }
  }
  if (!records.length) throw Error('No comparison records are available. Bills are inactive, deleted, or missing a vendor/reference. Check export coverage.');
  return { records, summary };
}
