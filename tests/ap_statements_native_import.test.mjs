import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { reconcile, toCSV, importRecords } from '../app/ap_statements/frontend/core.mjs';
import { saveSession, loadSession, reviewNotesOnly } from '../app/ap_statements/frontend/session.mjs';

async function importer() {
  const module = await import('../app/ap_statements/frontend/bill-import.mjs').catch(() => null);
  assert.ok(module, 'Native BILL export adapter must exist');
  return module.importBillSource;
}
const header = ['Active?', 'Vendor Name', 'Vendor Id', 'Invoice #', 'Invoice Date', 'Amount', 'Paid Amount', 'Amount Due', 'Credits Applied', 'Status', 'Paid On', 'Full Payment Date', 'Bill Line Item Amount', 'Bill Line Item Order', 'Total Line Items', 'Description'];
const row = (values = {}) => ({ 'Active?': 'Active', 'Vendor Name': 'Example Vendor', 'Vendor Id': '', 'Invoice #': '000123-A', 'Invoice Date': '10/01/2026', Amount: '100.00', 'Paid Amount': '', 'Amount Due': '', 'Credits Applied': '0.00', Status: 'Open', 'Paid On': '', 'Full Payment Date': '', 'Bill Line Item Amount': '100.00', 'Bill Line Item Order': '0', 'Total Line Items': '1', Description: 'Do not retain internal details', ...values });
const csv = (rows, columns = header) => toCSV([columns, ...rows.map(r => columns.map(k => r[k] ?? ''))]);
const statement = { id: 's1', vendor: 'Example Vendor', confirmed: true, layout: 'generic', statementDate: '2026-10-01', rows: [{ id: 'r1', invoiceNumber: '000123-A', type: 'invoice', amount: 10000, balance: 10000, confidence: 99, page: 1 }] };
const compare = records => reconcile(statement, { loaded: true, simulated: false, records })[0];

test('native columns preserve invoice text and compare existence without assuming settled balances', async () => {
  const result = (await importer())(csv([row()]));
  assert.equal(result.records[0].vendor, 'Example Vendor');
  assert.equal(result.records[0].invoiceNumber, '000123-A');
  assert.equal(result.records[0].amount, 10000);
  assert.equal(result.records[0].reportedPaidAmount, null);
  assert.equal(result.records[0].reportedAmountDue, null);
  assert.equal(compare(result.records).status, 'presence');
  assert.match(compare(result.records).reason, /not verified/i);
});
test('complete consistent zero-based line items produce one bill, never the sum of repeated bill totals', async () => {
  const result = (await importer())(csv([row({ 'Total Line Items': '2', 'Bill Line Item Amount': '40.00' }), row({ 'Total Line Items': '2', 'Bill Line Item Amount': '60.00', 'Bill Line Item Order': '1' })]));
  assert.equal(result.records.length, 1);
  assert.equal(result.records[0].amount, 10000);
  assert.equal(result.summary.collapsedRows, 1);
  assert.equal(result.records[0].sourceRows, '2,3');
});
test('signed discount line items can establish one positive bill when their total agrees exactly', async () => {
  const result = (await importer())(csv([row({ 'Total Line Items': '2', 'Bill Line Item Amount': '140.00' }), row({ 'Total Line Items': '2', 'Bill Line Item Amount': '-40.00', 'Bill Line Item Order': '1' })]));
  assert.equal(result.records.length, 1);
  assert.equal(result.records[0].amount, 10000);
  assert.equal(compare(result.records).status, 'presence');
});
test('separate dates with the same vendor reference remain multiple candidates', async () => {
  const result = (await importer())(csv([row(), row({ 'Invoice Date': '10/02/2026' })]));
  assert.equal(result.records.length, 2);
  assert.equal(compare(result.records).status, 'ambiguous');
});
test('identical single-line duplicate bills are not silently deduplicated', async () => {
  const result = (await importer())(csv([row(), row()]));
  assert.equal(result.records.length, 2);
  assert.equal(compare(result.records).status, 'ambiguous');
});
test('repeated bills without complete line-item evidence stay ambiguous', async () => {
  const columns = header.filter(h => !h.startsWith('Bill Line Item') && h !== 'Total Line Items');
  const result = (await importer())(csv([row(), row()], columns));
  assert.equal(result.records.length, 2);
  assert.equal(compare(result.records).status, 'ambiguous');
});
test('conflicting bill totals or payment metadata cannot collapse into one match', async () => {
  for (const change of [{ Amount: '101.00' }, { 'Paid Amount': '25.00' }, { Status: 'PaidInFull' }]) {
    const result = (await importer())(csv([row({ 'Total Line Items': '2', 'Bill Line Item Amount': '40.00' }), row({ 'Total Line Items': '2', 'Bill Line Item Order': '1', 'Bill Line Item Amount': '60.00', ...change })]));
    assert.equal(result.records.length, 2);
    assert.equal(compare(result.records).status, 'ambiguous');
  }
});
test('missing, repeated, or inconsistent line-item orders never establish a safe group', async () => {
  for (const order of ['', '0', '2']) {
    const result = (await importer())(csv([row({ 'Total Line Items': '2', 'Bill Line Item Amount': '40.00' }), row({ 'Total Line Items': '2', 'Bill Line Item Order': order, 'Bill Line Item Amount': '60.00' })]));
    assert.equal(result.records.length, 2);
    assert.equal(compare(result.records).status, 'ambiguous');
  }
});
test('incomplete line detail and inconsistent line totals require source review', async () => {
  for (const rows of [[row({ 'Total Line Items': '2' })], [row({ 'Total Line Items': '2', 'Bill Line Item Amount': '45.00' }), row({ 'Total Line Items': '2', 'Bill Line Item Order': '1', 'Bill Line Item Amount': '60.00' })]]) {
    const result = (await importer())(csv(rows));
    assert.ok(result.summary.issues.length > 0);
    assert.notEqual(compare(result.records).status, 'matched');
    assert.notEqual(compare(result.records).status, 'presence');
  }
});
test('missing or malformed amount remains review evidence, never zero or an amount-only match', async () => {
  for (const Amount of ['', 'invalid', '-100.00', '90071992547410.00']) {
    const result = (await importer())(csv([row({ Amount })]));
    assert.equal(result.records.length, 1);
    assert.equal(compare(result.records).status, 'source');
  }
});
test('inactive and deleted rows are excluded and their source rows are reported', async () => {
  const result = (await importer())(csv([row(), row({ 'Active?': 'Inactive' }), row({ 'Active?': 'DraftDeleted' })]));
  assert.equal(result.records.length, 1);
  assert.equal(result.summary.excludedRows, 2);
  assert.ok(result.summary.issues.some(issue => issue.rows === '3'));
  assert.ok(result.summary.issues.some(issue => issue.rows === '4'));
});
test('missing vendor or reference is reported as excluded instead of losing valid invoices', async () => {
  const result = (await importer())(csv([row(), row({ 'Invoice #': '' }), row({ 'Vendor Name': '' })]));
  assert.equal(result.records.length, 1);
  assert.equal(result.summary.excludedRows, 2);
});
test('unknown active flag, status, or invalid invoice date cannot be cleared', async () => {
  for (const values of [{ 'Active?': '' }, { Status: 'Unexpected' }, { 'Invoice Date': '02/30/2026' }]) {
    assert.equal(compare((await importer())(csv([row(values)])).records).status, 'source');
  }
});
test('paid and scheduled export statuses never become verified settled balances', async () => {
  const imported = await importer();
  const paid = imported(csv([row({ Status: 'PaidInFull', 'Paid Amount': '100.00', 'Amount Due': '0.00', 'Full Payment Date': '10/02/2026' })]));
  assert.equal(compare(paid.records).status, 'presence');
  assert.equal(paid.records[0].clearedPaymentAmount, null);
  assert.equal(paid.records[0].reportedPaidAmount, 10000);
  const scheduled = imported(csv([row({ Status: 'Scheduled' })]));
  assert.equal(compare(scheduled.records).status, 'scheduled');
});
test('native original amount mismatch remains an amount exception', async () => {
  const result = (await importer())(csv([row({ Amount: '101.00', 'Bill Line Item Amount': '101.00' })]));
  assert.equal(compare(result.records).status, 'amount');
});
test('native import rejects ambiguous headers and structurally broken rows', async () => {
  const imported = await importer();
  assert.throws(() => imported(csv([row()], [...header, 'Amount'])), /duplicate/i);
  assert.throws(() => imported(toCSV([header, ['Active', 'Example Vendor']])), /column|row/i);
});
test('a vendor directory is not accepted as invoice data', async () => {
  const imported = await importer();
  assert.throws(() => imported('Active?,Vendor Name,Tax ID\nActive,Example Vendor,private'), /vendor.*bills/i);
});
test('template CSV retains existing reconciliation behavior', async () => {
  const text = 'vendor,invoiceNumber,amount\nExample Vendor,000123-A,100.00';
  const result = (await importer())(text);
  assert.deepEqual(result.records, importRecords(text));
  assert.equal(compare(result.records).status, 'matched');
});
test('native evidence survives session save without retaining extra source columns', async () => {
  const result = (await importer())(csv([row({ Status: 'PaidInFull', 'Paid Amount': '100.00' })]));
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const provider = { loaded: true, simulated: false, records: result.records, sourceFormat: result.summary.format, importNotes: 'Source row 2 needs review' };
  const original = { ...statement, filename: 'test.pdf', warnings: [] };
  assert.equal(saveSession(storage, { version: 1, statements: [original], provider, resolutions: {} }).ok, true);
  const saved = loadSession(storage).session;
  assert.equal(saved.provider.importNotes, 'Source row 2 needs review');
  assert.equal(saved.provider.records[0].reportedPaidAmount, 10000);
  assert.equal(compare(saved.provider.records).status, 'presence');
  assert.ok(!JSON.stringify(saved).includes('Do not retain internal details'));
});

test('actual import control applies native evidence and resets reviews only after successful parsing', async () => {
  const importBillSource = await importer();
  const source = fs.readFileSync(new URL('../app/ap_statements/frontend/app.mjs', import.meta.url), 'utf8');
  const block = source.slice(source.indexOf("document.querySelector('#csv-input').addEventListener"), source.indexOf("document.addEventListener('input'"));
  const state = { statements: [statement], resolutions: { r1: { decision: 'Preserve on failure' } }, provider: { label: 'old' } };
  let handler;
  const input = { addEventListener: (_, callback) => { handler = callback; } };
  const context = { state, importBillSource, importRecords, reviewNotesOnly, document: { querySelector: selector => selector === '#csv-input' ? input : null }, render() {}, toast() {} };
  vm.runInNewContext(block, context);
  await handler({ target: { files: [{ name: 'BILL.csv', text: async () => csv([row()]) }], value: 'BILL.csv' } });
  assert.equal(state.provider.sourceFormat, 'bill-native');
  assert.equal(state.provider.records[0].invoiceNumber, '000123-A');
  assert.equal(state.provider.importedRowCount, 1);
  assert.equal(Object.keys(state.resolutions).length, 0);
  assert.equal(state.statements[0], statement);
  state.resolutions.r1 = { decision: 'Keep' };
  const previous = state.provider;
  await handler({ target: { files: [{ name: 'bad.csv', text: async () => 'bad csv' }], value: 'bad.csv' } });
  assert.equal(state.provider, previous);
  assert.equal(state.resolutions.r1.decision, 'Keep');
});

test('an import with zero usable bills cannot replace the current comparison source', async () => {
  const imported = await importer();
  assert.throws(() => imported(csv([row({ 'Active?': 'DraftDeleted' })])), /no comparison records/i);
});

test('unknown native currency is disclosed when original numeric amounts differ', async () => {
  const result = (await importer())(csv([row({ Amount: '101.00', 'Bill Line Item Amount': '101.00' })]));
  assert.match(compare(result.records).reason, /currency not supplied/i);
});
test('multiple native candidates never acquire a USD symbol when currency is absent or foreign', () => {
  const source = fs.readFileSync(new URL('../app/ap_statements/frontend/app.mjs', import.meta.url), 'utf8');
  const context = {};
  vm.runInNewContext(source.slice(source.indexOf('function reportedMoney('), source.indexOf('function toast(')), context);
  assert.equal(typeof context.candidateSummary, 'function', 'Candidate summaries must use the reported currency');
  for (const currency of ['', 'EUR']) {
    const text = context.candidateSummary({ id: 'native-2', comparisonScope: 'invoice-only', amount: 10000, currency });
    assert.match(text, /100\.00/);
    assert.doesNotMatch(text, /\$/);
    assert.match(text, currency ? /EUR/ : /not supplied/i);
  }
});
