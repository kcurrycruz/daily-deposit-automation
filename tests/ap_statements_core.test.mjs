import test from 'node:test';
import assert from 'node:assert/strict';
import { cents, invoiceKey, reconcile, groupInvoices, totals, parseStatement, importRecords, toCSV } from '../app/ap_statements/frontend/core.mjs';
const row = { id: 'r', invoiceNumber: '00504863', type: 'invoice', amount: 40911, balance: 40911, confidence: 99, page: 1 };
const statement = { id: 's', vendor: 'Vendor One', rows: [row], confirmed: true, statementDate: '2026-10-01' };
const bill = { vendor: 'Vendor One', invoiceNumber: '00504863', amount: 40911 };
const provider = records => ({ loaded: true, records });
test('money values preserve cents and trailing-minus credits', () => {
  assert.equal(cents('1,234.56'), 123456); assert.equal(cents('18.45-'), -1845); assert.equal(cents('($60.00)'), -6000); assert.equal(cents('invalid'), null);
});
test('references preserve leading zeros and significant suffixes', () => {
  assert.notEqual(invoiceKey('00504863'), invoiceKey('504863')); assert.notEqual(invoiceKey('V09651-0A'), invoiceKey('V09651-00'));
});
test('no provider is unavailable, not a missing invoice', () => {
  assert.equal(reconcile(statement, { loaded: false })[0].status, 'unverified'); assert.equal(reconcile(statement, provider([]))[0].status, 'missing');
});
test('exact vendor, reference, amount and cleared balance match', () => assert.equal(reconcile(statement, provider([bill]))[0].status, 'matched'));
test('scheduled payment is not a settled match', () => assert.equal(reconcile(statement, provider([{ ...bill, scheduledAmount: 40911 }]))[0].status, 'scheduled'));
test('paid invoice remains visible as a timing discrepancy', () => assert.equal(reconcile(statement, provider([{ ...bill, clearedPaymentAmount: 40911, paymentDate: '2026-10-03' }]))[0].status, 'paid'));
test('duplicate provider records require candidate review', () => assert.equal(reconcile(statement, provider([bill, bill]))[0].status, 'ambiguous'));
test('invoice, credit and payment rows group without false duplicates', () => {
  const s = { ...statement, rows: [row, { ...row, id: 'c', type: 'credit', amount: -23000, balance: null }, { ...row, id: 'p', type: 'payment', amount: -40911, balance: -23000 }] };
  const grouped = groupInvoices(s); assert.equal(grouped.length, 1); assert.equal(grouped[0].originalAmount, 40911); assert.equal(grouped[0].outstanding, -23000); assert.equal(grouped[0].duplicate, false);
});
test('opening balance and payments reconcile without becoming invoices', () => {
  const s = { ...statement, layout: 'argyle', declaredTotal: 330056, rows: [{ id: 'o', type: 'opening', amount: 328382 }, { ...row, amount: 260694, balance: null }, { id: 'p', type: 'payment', amount: -259020 }] };
  assert.equal(totals(s).difference, 0); assert.equal(groupInvoices(s).find(r => r.kind === 'invoice').outstanding, null);
});
test('unconfirmed or low confidence extraction is never cleared', () => { assert.equal(reconcile({ ...statement, confirmed: false }, provider([bill]))[0].status, 'extraction'); assert.equal(reconcile({ ...statement, rows: [{ ...row, confidence: 60 }] }, provider([bill]))[0].status, 'extraction'); });
test('AIF adapter distinguishes credits and due dates', () => {
  const s = parseStatement([{ page: 1, lines: [{ text: 'Adventure in Food', y: .1 }, { text: 'as of 10/1/26', y: .2 }, { text: '272618 - -$60.00', y: .4 }, { text: '271460 10/3/26 $253.00', y: .5 }, { text: 'Total $193.00', y: .8 }] }]);
  assert.equal(s.rows.length, 2); assert.equal(s.rows[0].type, 'credit'); assert.equal(s.rows[1].date, ''); assert.equal(s.rows[1].dueDate, '2026-10-03'); assert.equal(totals(s).difference, 0);
});
test('CSV validates amounts, handles quoted names and preserves leading zeros', () => { const r = importRecords('vendor,invoiceNumber,amount\r\n"Vendor, One",00504863,409.11'); assert.equal(r[0].invoiceNumber, '00504863'); assert.equal(r[0].amount, 40911); assert.throws(() => importRecords('vendor,invoiceNumber,amount\nVendor,1,bad')); assert.throws(() => importRecords('vendor,invoiceNumber,amount,creditAmount\nVendor,1,3.00,bad')); });
test('CSV export neutralizes spreadsheet formulas', () => assert.equal(toCSV([['=HYPERLINK("evil")', '-1.25']]), '"\'=HYPERLINK(""evil"")","-1.25"'));
test('open-item statement total sums balances, not original invoice amounts', () => {
  const s = { layout: 'bakemark', declaredTotal: 7500, rows: [{ type: 'invoice', amount: 10000, balance: 8000 }, { type: 'invoice', amount: 3000, balance: -500 }] };
  assert.equal(totals(s).difference, 0);
});
