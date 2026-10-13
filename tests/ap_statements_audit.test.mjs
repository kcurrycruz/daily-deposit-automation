import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { cents, dateISO, importRecords, reconcile, groupInvoices, vendorKey, parseStatement, totals } from '../app/ap_statements/frontend/core.mjs';
import { saveSession, loadSession } from '../app/ap_statements/frontend/session.mjs';

const source = readFileSync(new URL('../app/ap_statements/frontend/app.mjs', import.meta.url), 'utf8');
const statement = () => ({ id: 's', vendor: 'A&B Supply', layout: 'demo', statementDate: '2026-10-01',
  pageCount: 1, declaredTotal: 10000, confirmed: true, notes: 'Keep statement context',
  rows: [{ id: 'r', invoiceNumber: 'INV123', type: 'invoice', amount: 10000, balance: 10000, page: 1, confidence: 99 }] });
const record = vendor => ({ vendor, invoiceNumber: 'INV123', amount: 10000 });

test('distinct punctuated vendors cannot match automatically', () => {
  const result = reconcile(statement(), { loaded: true, records: [record('AB Supply')] })[0];
  assert.equal(result.status, 'vendor');
  assert.equal(result.candidates[0].vendor, 'AB Supply');
});

test('vendor identity supports case and repeated whitespace plus explicit aliases', () => {
  const doc = { ...statement(), vendor: '  A&B   Supply  ' };
  assert.equal(reconcile(doc, { loaded: true, records: [record('a&b supply')] })[0].status, 'matched');
  assert.equal(reconcile(statement(), { loaded: true, records: [record('AB Supply')] }, { 'A&B Supply': 'AB Supply' })[0].status, 'matched');
});

test('money rejects malformed signs and unbalanced accounting parentheses', () => {
  for (const value of ['1-2.00', '--12.00', '(12.00', '12.00)', '+-12.00', '12,34.00', '12$00'])
    assert.equal(cents(value), null, value);
});

test('money rejects overflow and preserves the largest safe cents value', () => {
  assert.equal(cents('9'.repeat(400)), null);
  assert.equal(cents('90071992547409.93'), null);
  assert.equal(cents('90071992547409.91'), 9007199254740991);
  assert.equal(cents(Number.MAX_VALUE), null);
  assert.throws(() => importRecords('vendor,invoiceNumber,amount\nV,I,' + '9'.repeat(400)), /amount/i);
});

test('valid money notation keeps exact signed cents', () => {
  for (const [value, expected] of [['1,234.56', 123456], ['18.45-', -1845], ['($60.00)', -6000],
    ['-$ 60.00', -6000], ['$-60.00', -6000], ['+$12.5', 1250], ['0', 0], ['12.00', 1200]])
    assert.equal(cents(value), expected, value);
});

test('statement extraction preserves valid dollar accounting credits', () => {
  const doc = parseStatement([{ page: 1, lines: [{ text: 'Adventure in Food', y: .1 },
    { text: 'INV123 - ($60.00)', y: .5 }] }]);
  assert.equal(doc.rows.length, 1);
  assert.equal(doc.rows[0].type, 'credit');
  assert.equal(doc.rows[0].amount, -6000);
});

test('ISO dates reject impossible calendar days just like slash dates', () => {
  for (const value of ['2026-02-30', '2026-13-01', '2026-00-01', '2026-04-31', '2025-02-29'])
    assert.equal(dateISO(value), '', value);
  assert.equal(dateISO('2024-02-29'), '2024-02-29');
  assert.equal(dateISO('2/29/24'), '2024-02-29');
});

test('CSV rejects supplied invalid payment dates instead of dropping timing evidence', () => {
  for (const value of ['2026-13-01', '2/30/26', 'not-a-date'])
    assert.throws(() => importRecords('vendor,invoiceNumber,amount,paymentDate\nV,I,100.00,' + value), /paymentDate.*row 2/i);
  assert.equal(importRecords('vendor,invoiceNumber,amount,paymentDate\nV,I,100.00,2026-10-02')[0].paymentDate, '2026-10-02');
  assert.equal(importRecords('vendor,invoiceNumber,amount,paymentDate\nV,I,100.00,')[0].paymentDate, '');
});

function deletionFixture(remainingAmount = '100.00', action = 'delete-row') {
  const doc = statement();
  if (action === 'delete-row') doc.rows.push({ id: 'blank', type: 'invoice', invoiceNumber: '', amount: 0, balance: null, page: 1 });
  const tr = (id, reference, amount) => ({ dataset: { row: id }, querySelector: selector => ({
    value: { reference, amount, balance: '', type: 'invoice', page: '1' }[selector.match(/name="(.*?)"/)[1]]
  }) });
  const state = { page: 1, statements: [doc], mappings: {}, provider: { loaded: true, records: [record(doc.vendor)] }, resolutions: {
    r: { decision: 'Reviewed — no action needed', note: 'Reviewed original $100 evidence', at: '2026-10-01' },
    unrelated: { decision: 'Follow up with vendor', note: 'Other document review', at: '2026-10-01' }
  } };
  const context = { cents, groupInvoices, reconcile, totals, state, uid: () => 'added',
    overlay: { querySelectorAll: () => [tr('r', 'INV123', remainingAmount), ...(action === 'delete-row' ? [tr('blank', '', '0.00')] : [])] },
    document: { querySelector: selector => ({ value: { '#doc-vendor': 'A&B Supply', '#doc-date': '2026-10-01', '#doc-total': '100.00' }[selector] }) },
    action, target: { dataset: { id: 'blank' } }, getDoc: () => doc, render() {}, renderDrawer() {} };
  vm.runInNewContext(source.slice(source.indexOf('const results ='), source.indexOf('const badge =')), context);
  vm.runInNewContext(source.slice(source.indexOf('function collectRows('), source.indexOf('async function uploadPDFs')), context);
  const run = () => vm.runInNewContext(source.slice(source.indexOf(`if (action === '${action}'`),
    source.indexOf(action === 'delete-row' ? "if (action === 'save-notes'" : "if (action === 'delete-row'")), context);
  return { doc, state, context, run };
}

test('discarding a blank added invoice validates only rows being kept', () => {
  const { doc, run } = deletionFixture();
  run();
  assert.deepEqual(Array.from(doc.rows, row => row.id), ['r']);
  assert.equal(doc.confirmed, false);
});

test('discarding a row still rejects invalid kept edits atomically', () => {
  const { doc, state, run } = deletionFixture('invalid');
  const before = structuredClone(doc);
  const reviews = structuredClone(state.resolutions);
  assert.throws(run, /valid amounts/i);
  assert.deepEqual(doc, before);
  assert.deepEqual(state.resolutions, reviews);
});

for (const action of ['delete-row', 'add-row']) {
  test(`${action} reopens edited retained invoices while preserving notes and unrelated reviews`, () => {
    const { doc, state, context, run } = deletionFixture('200.00', action);
    run();
    assert.equal(doc.rows[0].amount, 20000);
    assert.equal(state.resolutions.r.decision, undefined);
    assert.equal(state.resolutions.r.at, undefined);
    assert.equal(state.resolutions.r.note, 'Reviewed original $100 evidence');
    assert.equal(state.resolutions.unrelated.decision, 'Follow up with vendor');
    context.attentionRow = reconcile(doc, { loaded: true, records: [record(doc.vendor)] })[0];
    assert.equal(context.attentionRow.status, 'extraction');
    assert.equal(vm.runInNewContext('isAttention(attentionRow)', context), true);
  });

  test(`${action} refreshes displayed workspace counts after reopening reviews`, () => {
    const { doc, context, run } = deletionFixture('200.00', action);
    if (action === 'delete-row') doc.rows[1].invoiceNumber = 'EXTRA';
    let displayed;
    context.render = () => {
      const data = vm.runInNewContext('stats()', context);
      displayed = { attention: data.attention, reviewed: data.reviewed };
    };
    context.render();
    assert.equal(displayed.reviewed, 1);
    run();
    assert.deepEqual(displayed, { attention: action === 'add-row' ? 2 : 1, reviewed: 0 });
  });
}

test('confirmation retains reopened notes without reusing the old review decision', async () => {
  const { doc, state, context } = deletionFixture('200.00', 'add-row');
  context.action = 'confirm-extraction';
  context.render = context.toast = () => {};
  context.persistDoc=async()=>{};
  await vm.runInNewContext('(async()=>{'+source.slice(source.indexOf("if (action === 'save-extraction'"), source.indexOf("if (action === 'add-row'"))+'})()', context);
  assert.equal(doc.confirmed, true);
  assert.equal(state.resolutions.r?.note, 'Reviewed original $100 evidence');
  assert.equal(state.resolutions.r?.decision, undefined);
  assert.equal(state.resolutions.unrelated.decision, 'Follow up with vendor');
});

test('changing a vendor mapping reopens changed evidence while retaining review notes', async () => {
  const doc = statement();
  const state = { statements: [doc], mappings: {}, resolutions: {
    r: { decision: 'Reviewed — no action needed', note: 'Prior vendor comparison', at: '2026-10-01' },
    unrelated: { decision: 'Follow up with vendor', note: 'Keep other review', at: '2026-10-01' }
  } };
  const context = { state, groupInvoices, vendorKey, action: 'mapping', target: { dataset: { vendor: doc.vendor, input: 'mapping-0' } },
    document: { getElementById: () => ({ value: 'Other vendor' }) }, saveVendorMappings: () => ({ ok: true }),
    browserStorage() {}, render() {}, toast() {} };
  vm.runInNewContext(source.slice(source.indexOf('const reviewDecision ='), source.indexOf('function stats()')), context);
  context.ready=()=>{};context.shared={state:{mappingVersions:{}},saveMapping:async()=>({version:1})};
  await vm.runInNewContext('(async()=>{'+source.slice(source.indexOf("if (action === 'mapping'"), source.indexOf("if (action === 'save-session'"))+'})()', context);
  assert.equal(state.resolutions.r.note, 'Prior vendor comparison');
  assert.equal(state.resolutions.r.decision, undefined);
  assert.equal(state.resolutions.r.at, undefined);
  assert.equal(state.resolutions.unrelated.decision, 'Follow up with vendor');
  assert.equal(doc.notes, 'Keep statement context');
  assert.equal(vm.runInNewContext("isAttention({ id: 'r', status: 'amount' })", context), true);
});

test('saving equivalent vendor spelling retains the existing review decision', async () => {
  const doc = statement();
  const prior = { decision: 'Follow up with vendor', note: 'Current evidence', at: '2026-10-01' };
  const state = { statements: [doc], mappings: {}, resolutions: { r: prior } };
  const context = { state, groupInvoices, vendorKey, action: 'mapping', target: { dataset: { vendor: doc.vendor, input: 'mapping-0' } },
    document: { getElementById: () => ({ value: ' a&b   supply ' }) }, saveVendorMappings: () => ({ ok: true }),
    browserStorage() {}, render() {}, toast() {} };
  vm.runInNewContext(source.slice(source.indexOf('const reviewDecision ='), source.indexOf('function stats()')), context);
  context.ready=()=>{};context.shared={state:{mappingVersions:{}},saveMapping:async()=>({version:1})};
  await vm.runInNewContext('(async()=>{'+source.slice(source.indexOf("if (action === 'mapping'"), source.indexOf("if (action === 'save-session'"))+'})()', context);
  assert.deepEqual(state.resolutions.r, prior);
});

test('retained review drafts survive explicit browser save without becoming decisions', () => {
  const doc = { ...statement(), filename: 'synthetic.pdf', warnings: [] };
  const values = new Map();
  const storage = { setItem: (key, value) => values.set(key, value), getItem: key => values.get(key) ?? null };
  assert.equal(saveSession(storage, { version: 1, statements: [doc], provider: { loaded: false, simulated: false, records: [] },
    resolutions: { r: { note: 'Prior comparison context' } } }).ok, true);
  const restored = loadSession(storage).session.resolutions.r;
  assert.equal(restored.note, 'Prior comparison context');
  assert.equal(restored.decision, undefined);
});
