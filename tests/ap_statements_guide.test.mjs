import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createDemo } from './fixtures/legacy_ap_demo.mjs';
import { saveSession, loadSession } from '../app/ap_statements/frontend/session.mjs';

const source = fs.readFileSync(new URL('../app/ap_statements/frontend/app.mjs', import.meta.url), 'utf8');
async function module() {
  const loaded = await import('../app/ap_statements/frontend/guide.mjs').catch(() => null);
  assert.ok(loaded, 'The guided AP start workflow must exist');
  return loaded;
}
const doc = (overrides = {}) => ({ id: 'doc1', vendor: 'Example Vendor', filename: 'sample.pdf',
  rows: [{ id: 'r1', invoiceNumber: '000123', type: 'invoice', amount: 10000, balance: 10000, page: 1, confidence: 99 }],
  warnings: [], confirmed: true, demo: false, declaredTotal: 10000, ...overrides });
const provider = (overrides = {}) => ({ loaded: true, simulated: false, records: [
  { vendor: 'Example Vendor', invoiceNumber: '000123', amount: 10000, currency: 'USD' }
], ...overrides });
const workspace = (overrides = {}) => ({ statements: [doc()], provider: provider(), mappings: {}, resolutions: {}, ...overrides });

test('new workspace has no fictional vendors or accounting source', async () => {
  const { emptyWorkspace } = await module();
  const context = { emptyWorkspace, createDemo };
  vm.runInNewContext(source.slice(source.indexOf('const initial ='), source.indexOf('const files =')), context);
  const state = vm.runInNewContext('state', context);
  assert.equal(state.statements.length, 0);
  assert.equal(state.provider.loaded, false);
  assert.equal(state.provider.simulated, false);
});

test('saved statements, provider, and notes survive the new initial state', async () => {
  const { emptyWorkspace } = await module();
  const session = { version: 1, ...workspace({ resolutions: { r1: { note: 'Retain this note' } } }) };
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  assert.equal(saveSession(storage, session).ok, true);
  const context = { emptyWorkspace, createDemo, loadSession, browserStorage: () => storage };
  vm.runInNewContext(source.slice(source.indexOf('const initial ='), source.indexOf('const files =')), context);
  vm.runInNewContext(source.slice(source.indexOf('const saved ='), source.indexOf('const savedMappings =')), context);
  const state = vm.runInNewContext('state', context);
  assert.equal(state.statements[0].id, 'doc1');
  assert.equal(state.provider.records[0].invoiceNumber, '000123');
  assert.equal(state.resolutions.r1.note, 'Retain this note');
});

test('empty workspace recommends PDF upload rather than a sample dashboard', async () => {
  const { workflowGuide, emptyWorkspace } = await module();
  const guide = workflowGuide(emptyWorkspace());
  assert.equal(guide.current, 'upload');
  assert.equal(guide.action, 'upload');
  assert.deepEqual(guide.steps.map(s => s.complete), [false, false, false, false]);
});

test('unconfirmed or mismatched statement recommends checking extraction', async () => {
  const { workflowGuide } = await module();
  for (const statement of [doc({ confirmed: false }), doc({ declaredTotal: 15000 }), doc({ rows: [] }), doc({ vendor: 'Unidentified vendor' })]) {
    const guide = workflowGuide(workspace({ statements: [statement] }));
    assert.equal(guide.current, 'extraction');
    assert.equal(guide.documentId, 'doc1');
    assert.equal(guide.steps[1].complete, false);
  }
});

test('low confidence and duplicate invoice evidence still recommends extraction review', async () => {
  const { workflowGuide } = await module();
  const low = doc(); low.rows[0].confidence = 50;
  const duplicate = doc(); duplicate.rows.push({ ...duplicate.rows[0], id: 'r2' }); duplicate.declaredTotal = 20000;
  for (const statement of [low, duplicate])
    assert.equal(workflowGuide(workspace({ statements: [statement] })).current, 'extraction');
});

test('a disconnected source cannot look like completed BILL comparison', async () => {
  const { workflowGuide } = await module();
  const guide = workflowGuide(workspace({ provider: provider({ loaded: false, records: [] }) }));
  assert.equal(guide.current, 'source');
  assert.equal(guide.action, 'source');
  assert.equal(guide.steps[2].complete, false);
});

test('legacy simulated sources never complete real BILL comparison', async () => {
  const { workflowGuide } = await module();
  const guide = workflowGuide({ ...createDemo(), mappings: {}, resolutions: {} });
  assert.equal(guide.current, 'source');
  assert.equal(guide.simulated, true);
  assert.equal(guide.steps[2].complete, false);
});

test('notes alone do not complete an exception review', async () => {
  const { workflowGuide } = await module();
  const guide = workflowGuide(workspace({ provider: provider({ records: [] }), resolutions: { r1: { note: 'Need to check' } } }));
  assert.equal(guide.current, 'review');
  assert.equal(guide.action, 'review');
  assert.equal(guide.attention, 1);
  assert.equal(guide.steps[3].complete, false);
});

test('matched or explicitly reviewed rows recommend export without claiming they were saved', async () => {
  const { workflowGuide } = await module();
  const matched = workflowGuide(workspace());
  const reviewed = workflowGuide(workspace({ provider: provider({ records: [] }), resolutions: { r1: { decision: 'Follow up with vendor', note: 'Recorded follow up' } } }));
  for (const guide of [matched, reviewed]) {
    assert.equal(guide.action, 'export');
    assert.equal(guide.current, 'review');
    assert.equal(guide.steps[3].complete, false);
    assert.equal(guide.attention, 0);
  }
});

test('guide recommendations never mutate financial evidence or review decisions', async () => {
  const { workflowGuide } = await module();
  const state = workspace({ resolutions: { r1: { note: 'Preserve' } } });
  const before = structuredClone(state);
  workflowGuide(state);
  assert.deepEqual(state, before);
});

test('guide opens the unchecked statement once and retains focus inside the dialog', async () => {
  const { workflowGuide } = await module();
  const state = workspace({ statements: [doc(), doc({ id: 'doc2', confirmed: false })] });
  const document = { activeElement: { name: 'guide button' } };
  let closeButton;
  let renders = 0;
  const context = { state, workflowGuide, document, priorFocus: null,
    overlay: { querySelector: () => closeButton },
    renderDrawer: () => {
      renders++;
      if (document.activeElement === closeButton) document.activeElement = { name: 'body' };
      closeButton = { focus() { document.activeElement = this; } };
    }
  };
  vm.runInNewContext(source.slice(source.indexOf('function openDoc('), source.indexOf('function renderDrawer(')), context);
  vm.runInNewContext(source.slice(source.indexOf('function goToGuideStep('), source.indexOf('function metrics(')), context);
  vm.runInNewContext("goToGuideStep('extraction')", context);
  assert.equal(document.activeElement, closeButton, 'Focus must remain on a current dialog control');
  assert.equal(renders, 1);
  assert.equal(state.selected, 'doc2');
  assert.equal(state.drawerTab, 'extraction');
  assert.equal(state.statements[1].confirmed, false);
});

test('first PDF extraction updates the visible guide progress status', () => {
  const status = { textContent: 'Reading your PDFs…' };
  const context = { state: {}, i: 0, pdfs: [{}], file: { name: 'first.pdf' },
    esc: value => value, document: { querySelector: selector => selector === '.guide-progress' ? status : null } };
  const start = source.indexOf('progress => { state.progress =');
  const end = source.indexOf(' });', start);
  assert.ok(start >= 0 && end > start);
  vm.runInNewContext(`const callback = ${source.slice(start, end + 2)}; callback({page: 2, total: 4, stage: 'OCR', fraction: 0.5});`, context);
  assert.match(status.textContent, /first.pdf.*page 2\/4.*OCR/);
});

test('source guide action opens existing CSV import view without changing financial data', async () => {
  const { workflowGuide } = await module();
  const state = workspace();
  let rendered = 0;
  const before = structuredClone(state);
  const context = { state, workflowGuide, render: () => rendered++ };
  vm.runInNewContext(source.slice(source.indexOf('function goToGuideStep('), source.indexOf('function metrics(')), context);
  vm.runInNewContext("goToGuideStep('source')", context);
  assert.equal(state.view, 'connection');
  assert.equal(rendered, 1);
  assert.deepEqual({ ...state, view: undefined }, { ...before, view: undefined });
});
