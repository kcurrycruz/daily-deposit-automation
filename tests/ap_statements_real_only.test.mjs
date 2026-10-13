import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as core from '../app/ap_statements/frontend/core.mjs';
import * as session from '../app/ap_statements/frontend/session.mjs';
import * as guide from '../app/ap_statements/frontend/guide.mjs';
import { createDemo, simulateRecords } from './fixtures/legacy_ap_demo.mjs';
import { importBillSource } from '../app/ap_statements/frontend/bill-import.mjs';
import { backButtonHtml, requestProgramHub } from '../app/ap_statements/frontend/navigation.mjs';

const KEY = 'hwfc-ap-statements-session-v1';
const source = fs.readFileSync(new URL('../app/ap_statements/frontend/app.mjs', import.meta.url), 'utf8');
const realDoc = () => ({ id: 'real-doc', vendor: 'Example Vendor', filename: 'actual.pdf', layout: 'generic', demo: false, confirmed: true, warnings: [], notes: 'Keep vendor follow-up', pageCount: 1,
  rows: [{ id: 'real-row', invoiceNumber: '000123', type: 'invoice', amount: 10000, balance: null, page: 1, confidence: 99 }] });
const realProvider = () => ({ loaded: true, simulated: false, label: 'BILL.csv', sourceFormat: 'bill-native', asOf: '2026-10-13', records: [{ id: 'csv-1', vendor: 'Example Vendor', invoiceNumber: '000123', amount: 10000, comparisonScope: 'invoice-only', status: 'Open' }] });
const realSession = () => ({ version: 1, statements: [realDoc()], provider: realProvider(), resolutions: { 'real-row': { note: 'Keep the note', decision: 'Follow up with vendor', at: '2026-10-13' } } });
function storage(data) {
  const values = new Map(data ? [[KEY, JSON.stringify(data)]] : []);
  return { values, getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
}

test('old sample documents do not restore alongside a real BILL import', () => {
  const data = realSession(), demo = createDemo();
  data.statements.push(demo.statements[0]);
  data.resolutions[demo.statements[0].rows[0].id] = { note: 'Sample note', decision: 'Sample decision' };
  const store = storage(data), original = store.getItem(KEY);
  const restored = session.loadSession(store);
  assert.equal(restored.session.statements.length, 1);
  assert.equal(restored.session.statements[0].id, 'real-doc');
  assert.deepEqual(restored.session.provider, data.provider);
  assert.deepEqual(restored.session.resolutions, { 'real-row': data.resolutions['real-row'] });
  assert.ok(restored.notice);
  assert.equal(store.getItem(KEY), original, 'Loading must not silently overwrite the saved session');
});
test('simulated comparison records cannot restore as real invoice evidence', () => {
  const data = realSession(); data.provider = simulateRecords(data.statements);
  const restored = session.loadSession(storage(data));
  assert.equal(restored.session.statements[0].notes, 'Keep vendor follow-up');
  assert.equal(restored.session.provider.loaded, false);
  assert.equal(restored.session.provider.simulated, false);
  assert.equal(restored.session.provider.records.length, 0);
  assert.deepEqual(restored.session.resolutions['real-row'], { note: 'Keep the note' });
  assert.ok(restored.notice);
});
test('a saved all-demo workspace restores empty without fictional vendors', () => {
  const data = { version: 1, ...createDemo(), resolutions: {} };
  const restored = session.loadSession(storage(data)).session;
  assert.equal(restored.statements.length, 0);
  assert.equal(restored.provider.records.length, 0);
  assert.equal(restored.provider.loaded, false);
});
test('ordinary saved work is unchanged, even for a vendor sharing a former sample name', () => {
  const data = realSession(); data.statements[0].vendor = 'Northfield Produce';
  const restored = session.loadSession(storage(data));
  assert.deepEqual(restored.session, data);
  assert.equal(restored.notice ?? null, null);
});
test('explicit Save session cannot reintroduce sample documents or simulated records', () => {
  const data = realSession(); data.statements.push(createDemo().statements[0]); data.provider = simulateRecords(data.statements);
  const store = storage();
  assert.equal(session.saveSession(store, data).ok, true);
  const saved = JSON.parse(store.getItem(KEY));
  assert.equal(saved.statements.length, 1);
  assert.equal(saved.provider.records.length, 0);
  assert.equal(saved.provider.loaded, false);
  assert.equal(saved.resolutions['real-row'].note, 'Keep the note');
  assert.equal(saved.resolutions['real-row'].decision, undefined);
});

function browserApp(data) {
  const localStorage = storage(data), events = {}, nodes = {};
  for (const id of ['app', 'overlay-root', 'toast', 'pdf-input', 'csv-input']) nodes[`#${id}`] = { innerHTML: '', style: {}, value: '', handlers: {}, addEventListener(event, handler) { this.handlers[event] = handler; }, querySelector() { return null; } };
  const context = { ...core, ...session, ...guide, importBillSource, createDemo, simulateRecords, backButtonHtml, requestProgramHub,
    window: { localStorage,addEventListener(){} }, document: { activeElement: null,querySelectorAll:()=>[], querySelector: selector => nodes[selector] ?? null,
      addEventListener: (event, handler) => { events[event] = handler; } }, setTimeout() {}, clearTimeout() {} };
  vm.runInNewContext(source.replace(/^import .*;\r?\n/gm, ''), context);
  // Tests of controls supply an acknowledged synthetic shared snapshot,
  // never an implicit localStorage restore.
  if(data){context.fixtureSession=session.loadSession(localStorage).session;vm.runInNewContext('Object.assign(state,fixtureSession)',context);}
  context.cloud={state:{ready:true},async importBills(file,provider){const current=vm.runInNewContext('state',context);current.provider=provider;current.resolutions=session.reviewNotesOnly(current.resolutions);},extractionOnly(){const current=vm.runInNewContext('state',context);current.provider={loaded:false,records:[]};current.resolutions=session.reviewNotesOnly(current.resolutions);}};
  vm.runInNewContext('shared=cloud',context);
  return { nodes, context, events, state: vm.runInNewContext('state', context) };
}
test('the rendered workspace and connection page offer no sample or simulation actions', () => {
  const app = browserApp();
  for (const view of ['statements', 'connection', 'exceptions']) {
    app.state.view = view; vm.runInNewContext('render()', app.context);
    assert.doesNotMatch(app.nodes['#app'].innerHTML, /data-action="(?:demo|simulate|confirm-demo|confirm-simulate)"/);
  }
});
test('legacy demo action names cannot generate data or replace imported BILL records', async () => {
  const app = browserApp(realSession());
  const before = JSON.stringify(app.state);
  for (const action of ['demo', 'confirm-demo', 'simulate', 'confirm-simulate']) {
    await app.events.click({ target: { classList: { contains: () => false }, closest: () => ({ dataset: { action } }) } });
    assert.equal(JSON.stringify(app.state), before);
    assert.equal(app.nodes['#overlay-root'].innerHTML, '');
  }
});
test('actual initialization never restores legacy data or demos without explicit migration', () => {
  const data = realSession(); data.statements.push(createDemo().statements[0]);
  const app = browserApp();
  assert.equal(app.state.statements.length, 0);
  assert.equal(app.state.provider.loaded, false);
  assert.doesNotMatch(app.nodes['#app'].innerHTML, /Northfield Produce/);
});
test('multi-PDF upload continues to retain the imported BILL source and existing real notes', async () => {
  const state = { ...realSession(), busy: false };
  const files = new Map(), input = { value: 'selected' };
  const context = { state, files, extractor: { extractPDF: async file => ({ ...realDoc(), id: file.name, filename: file.name }), stopOCR: async () => {} },
    document: { querySelector: selector => selector === '#pdf-input' ? input : null }, render() {}, toast() {} };
  context.pendingAttachment=null;context.ready=()=>{};context.shared={async uploadStatement(file,extract){const doc=await extract(file);state.statements.push(doc);return {doc};}};
  vm.runInNewContext(source.slice(source.indexOf('async function uploadPDFs('), source.indexOf('function bindDropzone(')), context);
  await vm.runInNewContext("uploadPDFs([{name:'vendor-a.pdf',size:1,lastModified:1},{name:'vendor-b.pdf',size:2,lastModified:2}])", context);
  assert.equal(state.statements.length, 3);
  assert.equal(files.size, 2);
  assert.equal(state.statements[0].notes, 'Keep vendor follow-up');
  assert.equal(state.provider.records[0].invoiceNumber, '000123');
  assert.equal(state.resolutions['real-row'].note, 'Keep the note');
});
test('the downloadable template contains headers only, not a fictional invoice', async () => {
  const app = browserApp(); app.context.downloads = [];
  vm.runInNewContext('download = (name, text) => downloads.push(text)', app.context);
  await app.events.click({ target: { classList: { contains: () => false }, closest: () => ({ dataset: { action: 'template' } }) } });
  assert.equal(core.parseCSV(app.context.downloads[0]).length, 1);
});
test('an unfilled template cannot replace actual BILL records with an empty comparison dataset', () => {
  assert.throws(() => importBillSource('vendor,invoiceNumber,amount\n'), /no.*records|empty/i);
});
test('importing real BILL records after migration retains the reopened invoice notes', async () => {
  const data = realSession(); data.provider = simulateRecords(data.statements);
  const app = browserApp(data);
  await app.nodes['#csv-input'].handlers.change({ target: { files: [{ name: 'real-records.csv', text: async () => 'vendor,invoiceNumber,amount\nExample Vendor,000123,100.00' }], value: 'selected' } });
  assert.equal(app.state.resolutions['real-row']?.note, 'Keep the note');
  assert.equal(app.state.resolutions['real-row']?.decision, undefined);
  assert.equal(app.state.statements[0].notes, 'Keep vendor follow-up');
  assert.equal(app.state.provider.loaded, true);
});
test('extraction-only mode reopens decisions without erasing real invoice notes', async () => {
  const app = browserApp(realSession());
  await app.events.click({ target: { classList: { contains: () => false }, closest: () => ({ dataset: { action: 'disconnect' } }) } });
  assert.equal(app.state.resolutions['real-row']?.note, 'Keep the note');
  assert.equal(app.state.resolutions['real-row']?.decision, undefined);
  assert.equal(app.state.provider.loaded, false);
});
