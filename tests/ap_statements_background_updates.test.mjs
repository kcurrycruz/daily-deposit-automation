import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {duplicateSidebarHTML,duplicateViewHTML,createDuplicateReviewDrafts} from '../app/ap_statements/frontend/duplicate-bills-ui.mjs';
import {createDuplicateBills} from '../app/ap_statements/frontend/duplicate-bills.mjs';
import {createHistoryPreview} from '../app/ap_statements/frontend/history-browser.mjs';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');

function fixture(view='vendor-history'){
 const nodes=new Map(),nav={innerHTML:''},slot={innerHTML:''},main={scrollTop:350};
 for(const id of ['vendor-directory-search','statement-table','history-preview-root','pdf-canvas'])nodes.set('#'+id,{value:'Synthetic',selectionStart:3,selectionEnd:6,remove(){nodes.delete('#'+id);}});
 nodes.set('#duplicate-nav-slot',nav);nodes.set('#duplicate-view-slot',slot);
 const document={activeElement:nodes.get('#vendor-directory-search'),querySelector:s=>s==='.main'?main:nodes.get(s)};
 const drafts=createDuplicateReviewDrafts(),dup={source:{importId:'source',capability:1},phase:'running',progress:{state:'running',phase:'packaging',recordsRead:100,totalRecords:100},filters:{}};
 const context={state:{view,selected:null},shared:{state:{ready:true},duplicates:{state:dup}},duplicateSourceKey:JSON.stringify(dup.source),
  duplicateDrafts:drafts,duplicateReturn:null,duplicateSaveAttempt:null,duplicateSearchQuery:null,duplicateSearchTimer:null,clearTimeout(){},historyLoadToken:0,previewTimer:null,previewReturnFocus:null,dirty:new Set(),overlay:{querySelector:()=>null},document,
  app:{querySelector:s=>document.querySelector(s)},duplicateSidebarHTML,duplicateViewHTML,
  duplicateStateForView:()=>({...dup,draft:drafts.get('finding')}),
  render(){for(const id of ['vendor-directory-search','statement-table','history-preview-root','pdf-canvas'])nodes.set('#'+id,{value:'replaced'});},
  renderDrawer(){throw Error('Duplicate event must not rebuild the review');}};
 const start=source.indexOf('function renderDuplicateUpdate(');
 if(start!==-1)vm.runInNewContext(source.slice(start,source.indexOf('function receiveShared(',start)),context);
 vm.runInNewContext(source.slice(source.indexOf('function receiveShared('),source.indexOf('async function startShared(')),context);
 return {context,document,nodes,nav,slot,main,dup,drafts};
}
const snapshot=()=>({provider:{},statements:[],mappings:{},resolutions:{}});

test('duplicate progress preserves vendor typing, statement nodes, history preview and PDF while updating navigation',()=>{
 const f=fixture(),before=new Map(f.nodes);
 f.context.receiveShared(snapshot(),{reason:'duplicates'});
 for(const id of ['vendor-directory-search','statement-table','history-preview-root','pdf-canvas'])assert.equal(f.nodes.get('#'+id),before.get('#'+id),id+' must not be replaced');
 assert.equal(f.document.activeElement.value,'Synthetic');assert.equal(f.document.activeElement.selectionStart,3);
 assert.equal(f.main.scrollTop,350);assert.match(f.nav.innerHTML,/Duplicate bills/);assert.equal(f.slot.innerHTML,'');
});

test('visible duplicate status preserves draft value, focus selection and scroll',()=>{
 const f=fixture('duplicates');f.drafts.update('finding',{note:'Keep my draft',initials:'KC'});
 let focused=false,range;
 const old={id:'duplicate-note',selectionStart:2,selectionEnd:7};
 f.document.activeElement=old;f.nodes.set('#duplicate-note',{focus(){focused=true;},setSelectionRange(...args){range=args;}});
 f.context.receiveShared(snapshot(),{reason:'duplicates'});
 assert.equal(f.drafts.get('finding').note,'Keep my draft');assert.ok(focused);assert.deepEqual(range,[2,7]);
 assert.match(f.slot.innerHTML,/duplicate-workspace/);assert.equal(f.main.scrollTop,350);
});

test('source replacement is not mistaken for a status-only update',()=>{
 const f=fixture(),before=f.nodes.get('#vendor-directory-search');f.dup.source={importId:'new-source',capability:1};
 f.context.receiveShared(snapshot(),{reason:'duplicates'});
 assert.notEqual(f.nodes.get('#vendor-directory-search'),before);
});

test('access denial clears retained evidence even when tagged as a duplicate notification',()=>{
 const f=fixture(),files=new Map([['private',new Uint8Array([1])]]);let hidden=false;
 Object.assign(f.context,{files,historyPage:{items:[{id:'old'}]},historyPreview:{dispose(){hidden=true;}},historicalDetail:{},historySelection:'old',pendingRereview:{}});
 f.context.overlay.innerHTML='private preview';f.context.state.selected='old';
 f.context.receiveShared({...snapshot(),accessDenied:true},{reason:'duplicates'});
 assert.ok(hidden);assert.equal(files.size,0);assert.equal(f.context.historyPage.items.length,0);
 assert.equal(f.context.state.selected,null);assert.equal(f.context.overlay.innerHTML,'');
});

test('duplicate status preserves expanded diagnostics and keyboard focus on an action',()=>{
 const f=fixture('duplicates'),diagnostic={open:true};let focused=false;
 f.slot.querySelector=s=>s==='.duplicate-diagnostics'?diagnostic:s==='[data-action="duplicate-refresh"]'?{focus(){focused=true;}}:null;
 Object.defineProperty(f.slot,'innerHTML',{get(){return '';},set(){diagnostic.open=false;}});
 f.document.activeElement={dataset:{action:'duplicate-refresh'}};
 f.context.receiveShared(snapshot(),{reason:'duplicates'});
 assert.equal(diagnostic.open,true,'inspection must stay expanded during background progress');assert.ok(focused);
});

test('diagnostic summary keyboard focus survives a status patch',()=>{
 const f=fixture('duplicates');let focused=false;
 f.document.activeElement={tagName:'SUMMARY',closest:s=>s==='.duplicate-diagnostics'?{}:null};
 f.slot.querySelector=s=>s==='.duplicate-diagnostics summary'?{focus(){focused=true;}}:null;
 f.context.receiveShared(snapshot(),{reason:'duplicates'});assert.ok(focused);
});

test('a held prior findings reply cannot erase a newer debounced query, even after focus moves',async()=>{
 const f=fixture('duplicates'),timers=new Map();let handler,release,started,lastQuery,n=0;const held=new Promise(r=>started=r);
 f.context.document.addEventListener=(_,fn)=>handler=fn;
 Object.assign(f.context,{duplicateInput:()=>false,setTimeout(fn){timers.set(++n,fn);return n;},clearTimeout(id){timers.delete(id);}});
 vm.runInNewContext(source.slice(source.indexOf('function duplicateStateForView('),source.indexOf('function duplicateInput(')),f.context);
 vm.runInNewContext(source.slice(source.indexOf("document.addEventListener('input'"),source.indexOf("document.addEventListener('change'")),f.context);
 const sourcePin={importId:'source',importVersion:1,capability:1},progress={scanId:'scan',importId:'source',importVersion:1,state:'ready',projectionReady:true,reviewRevision:0,counts:{all:0,unreviewed:0}};
 const controller=createDuplicateBills({async request(action,payload){
  if(action==='duplicate_ensure')return progress;
  lastQuery=payload.filters.search;
  if(lastQuery==='Syn')return new Promise(r=>{release=r;started();});
  return {findings:[],total:0,reviewRevision:0,nextCursor:null};
 }},{schedule:()=>0,cancelSchedule(){},onChange:()=>f.context.receiveShared(snapshot(),{reason:'duplicates'})});
 f.context.shared.duplicates=controller;controller.adoptSource(sourcePin);await controller.retry();
 const prior=controller.load({filters:{search:'Syn'}});await held;
 handler({target:{id:'duplicate-search',value:'Synthetic',selectionStart:9,selectionEnd:9}});
 f.document.activeElement={id:'duplicate-classification'};
 release({findings:[],total:0,reviewRevision:0,nextCursor:null});await prior;
 assert.match(f.slot.innerHTML,/value="Synthetic"/,'pending response must render the current query, not its old filters');
 await [...timers.values()][0]();assert.equal(lastQuery,'Synthetic');
 controller.adoptSource({...sourcePin,importId:'source-b',importVersion:2});
 assert.equal(f.context.duplicateSearchQuery,null);assert.equal(timers.size,0);controller.dispose();
});

test('denial disposes cached private previews and cancels pending preview work',async()=>{
 const f=fixture(),item={id:'event',statementId:'statement'},preview=createHistoryPreview({loadPdf:async()=>new Blob(['synthetic']),paint:async()=> 'data:image/png;base64,cGRm',onChange(){}});
 await preview.show(item);assert.equal(preview.state.phase,'ready');let cancelled=false,removed=false;
 f.nodes.get('#history-preview-root').remove=()=>{removed=true;};
 Object.assign(f.context,{files:new Map(),historyPage:{items:[]},historyPreview:preview,previewTimer:1,duplicateSearchQuery:'private pending search',clearTimeout(id){if(id===1)cancelled=true;},historyLoadToken:4,previewReturnFocus:{},historicalDetail:null,historySelection:null,pendingRereview:null});
 f.context.receiveShared({...snapshot(),accessDenied:true},{reason:'duplicates'});
 await preview.show(item);assert.equal(preview.state.item,null,'a disposed preview cannot reuse its private thumbnail');
 assert.ok(cancelled);assert.ok(removed);assert.equal(f.context.historyLoadToken,5);assert.equal(f.context.historyPreview,null);assert.equal(f.context.previewReturnFocus,null);
 assert.equal(f.context.duplicateSearchQuery,null);
});
