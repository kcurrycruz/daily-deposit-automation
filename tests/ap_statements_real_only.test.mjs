import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as core from '../app/ap_statements/frontend/core.mjs';
import * as session from '../app/ap_statements/frontend/session.mjs';
import * as guide from '../app/ap_statements/frontend/guide.mjs';
import * as simpleFlow from '../app/ap_statements/frontend/simple-flow.mjs';
import * as simpleView from '../app/ap_statements/frontend/simple-flow-view.mjs';
import * as billUI from '../app/ap_statements/frontend/bill-update-ui.mjs';
import * as billWarningsView from '../app/ap_statements/frontend/bill-warnings.mjs';
const billTutorial=await import('../app/ap_statements/frontend/bill-export-guide.mjs').catch(()=>({}));
import { createDemo, simulateRecords } from './fixtures/legacy_ap_demo.mjs';
import { importBillSource } from '../app/ap_statements/frontend/bill-import.mjs';
import { backButtonHtml, requestProgramHub } from '../app/ap_statements/frontend/navigation.mjs';
import * as historyBrowser from '../app/ap_statements/frontend/history-browser.mjs';
import * as duplicates from '../app/ap_statements/frontend/statement-duplicates.mjs';

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
  const context = { ...core, ...session, ...guide, ...simpleFlow, ...simpleView, ...billTutorial,...billUI,...billWarningsView,...historyBrowser,...duplicates,
    createBillUpdateUI:options=>billUI.createBillUpdateUI({...options,importer:async()=>({importId:'synthetic',recordCount:1,metadata:{label:'Synthetic worker acknowledgement'}})}),importBillSource, createDemo, simulateRecords, backButtonHtml, requestProgramHub,
    window: { localStorage,addEventListener(){} }, document: { activeElement: null,querySelectorAll:()=>[], querySelector: selector => nodes[selector] ?? null,
      addEventListener: (event, handler) => { events[event] = handler; } }, setTimeout() {}, clearTimeout() {} };
  vm.runInNewContext(source.replace(/^import .*;\r?\n/gm, ''), context);
  // Tests of controls supply an acknowledged synthetic shared snapshot,
  // never an implicit localStorage restore.
  if(data){context.fixtureSession=session.loadSession(localStorage).session;vm.runInNewContext('Object.assign(state,fixtureSession)',context);}
  context.cloud={state:{ready:true,capabilities:{billSnapshots:2},details:new Map()},async adoptImport(result){const current=vm.runInNewContext('state',context);current.provider={loaded:true,records:[],recordCount:result.recordCount,label:result.metadata.label};},extractionOnly(){const current=vm.runInNewContext('state',context);current.provider={loaded:false,records:[]};current.resolutions=session.reviewNotesOnly(current.resolutions);}};
  vm.runInNewContext('shared=cloud',context);
  return { nodes, context, events, state: vm.runInNewContext('state', context) };
}

function scrollableApp(data) {
  const app=browserApp(data);let markup='',main=null;
  Object.defineProperty(app.nodes['#app'],'innerHTML',{
    get:()=>markup,
    set:value=>{markup=value;main={dataset:{workspaceView:app.state.view},scrollTop:0};}
  });
  app.nodes['#app'].querySelector=selector=>selector==='.main'?main:null;
  return {...app,main:()=>main};
}

const actionEvent=(action,extra={})=>({target:{classList:{contains:()=>false},closest:()=>({dataset:{action,...extra}})}});

test('native snapshot warnings are accessible through BILL data without embedded importNotes',async()=>{
 const app=browserApp();app.state.view='connection';app.state.provider={loaded:true,records:[],importId:'source',label:'Weekly.csv',sourceFormat:'bill-native',sourceIssueCount:1};
 const calls=[];app.context.window.hwfcSharedClient={async request(action,payload){calls.push({action,payload});return {importId:'source',total:1,warnings:[{rows:'88',reason:'Missing vendor'}],nextCursor:null};}};
 app.context.render();assert.match(app.nodes['#app'].innerHTML,/data-action="bill-warnings"/);
 await app.events.click(actionEvent('bill-warnings'));
 assert.equal(calls[0].action,'bill_warnings_page');assert.equal(calls[0].payload.import_id,'source');assert.match(app.nodes['#app'].innerHTML,/Missing vendor/);
});

test('Update BILL data opens the export guide without opening a file picker',async()=>{
  const app=browserApp(realSession());let picked=0;
  app.nodes['#csv-input'].click=()=>picked++;
  const before=JSON.stringify(app.state);
  await app.events.click(actionEvent('import'));
  assert.match(app.nodes['#overlay-root'].innerHTML,/Step 1 of 4/);
  assert.equal(picked,0);assert.equal(JSON.stringify(app.state),before);
});

test('guide Next and Back display the requested screenshot step',async()=>{
  const app=browserApp(realSession());
  await app.events.click(actionEvent('import'));
  await app.events.click(actionEvent('bill-guide-step',{step:'1'}));
  assert.match(app.nodes['#overlay-root'].innerHTML,/Legacy Import\/Export/);
  await app.events.click(actionEvent('bill-guide-step',{step:'0'}));
  assert.match(app.nodes['#overlay-root'].innerHTML,/Step 1 of 4/);
});

test('already-have-CSV and final upload keep the existing file import path',async()=>{
  const app=browserApp(realSession());let picked=0;
  app.nodes['#csv-input'].click=()=>picked++;
  await app.events.click(actionEvent('import'));
  picked=0;
  await app.events.click(actionEvent('bill-guide-upload'));
  assert.equal(picked,1);assert.equal(app.nodes['#overlay-root'].innerHTML,'');
  assert.equal(app.state.provider.records.length,1);
});

test('opening the export guide cannot discard unsaved statement corrections',async()=>{
  const app=browserApp(realSession());
  vm.runInNewContext("state.selected='real-doc';dirty.add('real-doc')",app.context);
  app.nodes['#overlay-root'].innerHTML='unsaved statement editor';
  app.nodes['#csv-input'].click=()=>{};
  await app.events.click(actionEvent('import'));
  assert.equal(app.nodes['#overlay-root'].innerHTML,'unsaved statement editor');
  assert.match(String(app.nodes['#toast'].textContent||''),/Save.*before/i);
});

test('rerendering the same workspace preserves the list scroll position',()=>{
  const app=scrollableApp(realSession());vm.runInNewContext('render()',app.context);
  app.main().scrollTop=350;app.state.filter='presence';vm.runInNewContext('render()',app.context);
  assert.equal(app.main().scrollTop,350);
});

test('switching workspace views starts the new view at the top',()=>{
  const app=scrollableApp(realSession());vm.runInNewContext('render()',app.context);
  app.main().scrollTop=350;app.state.view='connection';vm.runInNewContext('render()',app.context);
  assert.equal(app.main().scrollTop,0);
});

test('arriving statements reuse the saved BILL source in a single upload and results workspace',()=>{
  const app=browserApp(realSession());vm.runInNewContext('render()',app.context);
  const html=app.nodes['#app'].innerHTML;
  assert.equal((html.match(/id="dropzone"/g)||[]).length,1);
  assert.match(html,/Update BILL data/);assert.match(html,/Last updated/);
  assert.doesNotMatch(html,/Step \d of 4|data-step="source"/);
  assert.equal(app.state.provider.records[0].invoiceNumber,'000123');
});

test('opening a readable statement starts at its comparison results rather than extraction setup',()=>{
  const sourceBlock=source.slice(source.indexOf('function openDoc('),source.indexOf('function renderDrawer('));
  const state={};const d=realDoc();const context={state,dirty:new Set(),shared:null,historicalDetail:null,document:{activeElement:null},getDoc:()=>d,comparisonsFor:()=>[],reconcile:()=>[],renderDrawer(){},overlay:{querySelector:()=>null}};
  vm.runInNewContext(sourceBlock,context);context.openDoc(d.id);
  assert.equal(state.drawerTab,'review');
});

test('previous work does not render BILL setup instructions behind its history list',()=>{
  const app=browserApp(realSession());app.state.view='history';vm.runInNewContext('render()',app.context);
  assert.doesNotMatch(app.nodes['#app'].innerHTML,/class="panel wide-panel bill-settings"/);
});

test('BILL data explains the disconnected API and CSV comparison limits',()=>{
  const app=browserApp(realSession());app.state.view='connection';vm.runInNewContext('render()',app.context);
  assert.match(app.nodes['#app'].innerHTML,/BILL API is not connected/);
  assert.match(app.nodes['#app'].innerHTML,/CSV/);
  assert.match(app.nodes['#app'].innerHTML,/QuickBooks sync/);
});

test('statement and exception workspaces keep API status notices inside BILL data',()=>{
  const app=browserApp(realSession());
  for(const view of ['statements','exceptions','history']){
    app.state.view=view;vm.runInNewContext('render()',app.context);
    assert.doesNotMatch(app.nodes['#app'].innerHTML,/BILL API (?:is )?(?:offline|disconnected|not connected)/i);
  }
});
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
  const context = { ...historyBrowser,...duplicates,state,files,promptStatementSimilarity:async()=> 'continue',extractor: { extractPDF: async file => ({ ...realDoc(),id:file.name,filename:file.name,rows:[{...realDoc().rows[0],invoiceNumber:file.name}] }), stopOCR: async () => {} },
    document: { querySelector: selector => selector === '#pdf-input' ? input : null }, render() {}, toast() {} };
  context.pendingAttachment=null;context.ready=()=>{};context.shared={state:{details:new Map()},history:async()=>({items:[],nextCursor:null}),async uploadStatement(file,extract){const doc=await extract(file);state.statements.push(doc);this.state.details.set(doc.id,{doc});return {doc};}};
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
