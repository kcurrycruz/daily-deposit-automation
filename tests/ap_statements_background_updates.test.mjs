import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {duplicateSidebarHTML,duplicateViewHTML,createDuplicateReviewDrafts} from '../app/ap_statements/frontend/duplicate-bills-ui.mjs';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');

function fixture(view='vendor-history'){
 const nodes=new Map(),nav={innerHTML:''},slot={innerHTML:''},main={scrollTop:350};
 for(const id of ['vendor-directory-search','statement-table','history-preview-root','pdf-canvas'])nodes.set('#'+id,{value:'Synthetic',selectionStart:3,selectionEnd:6});
 nodes.set('#duplicate-nav-slot',nav);nodes.set('#duplicate-view-slot',slot);
 const document={activeElement:nodes.get('#vendor-directory-search'),querySelector:s=>s==='.main'?main:nodes.get(s)};
 const drafts=createDuplicateReviewDrafts(),dup={source:{importId:'source',capability:1},phase:'running',progress:{state:'running',phase:'packaging',recordsRead:100,totalRecords:100},filters:{}};
 const context={state:{view,selected:null},shared:{state:{ready:true},duplicates:{state:dup}},duplicateSourceKey:JSON.stringify(dup.source),
  duplicateDrafts:drafts,duplicateReturn:null,duplicateSaveAttempt:null,dirty:new Set(),overlay:{querySelector:()=>null},document,
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
 Object.assign(f.context,{files,historyPage:{items:[{id:'old'}]},historyPreview:{hide(){hidden=true;}},historicalDetail:{},historySelection:'old',pendingRereview:{}});
 f.context.overlay.innerHTML='private preview';f.context.state.selected='old';
 f.context.receiveShared({...snapshot(),accessDenied:true},{reason:'duplicates'});
 assert.ok(hidden);assert.equal(files.size,0);assert.equal(f.context.historyPage.items.length,0);
 assert.equal(f.context.state.selected,null);assert.equal(f.context.overlay.innerHTML,'');
});
