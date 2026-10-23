import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as referenceReview from '../app/ap_statements/frontend/reference-review.mjs';
import {completionReviews,confirmVendor} from '../app/ap_statements/frontend/simple-flow.mjs';
import * as simpleFlow from '../app/ap_statements/frontend/simple-flow.mjs';
import {completionPayload} from '../app/ap_statements/frontend/history.mjs';
import {MATCH_RULE_VERSION} from '../app/ap_statements/frontend/core.mjs';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');

test('clear reference matches preselect no action without creating a saved review',()=>{
  const resolutions={},context={...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,docDetail:()=>null,defaultReviewDecision:simpleFlow.defaultReviewDecision,billEvidence:()=>[],reviewDecision:()=>null,money:String,esc:String,icon:()=>'',badge:()=>'',pdfPanel:()=>'',state:{provider:{loaded:true},resolutions},statuses:{presence:{label:'Invoice found'}}};
  vm.runInNewContext(source.slice(source.indexOf('function creditExportLimitationHTML('),source.indexOf('function connectionPanel(')),context);
  vm.runInNewContext(source.slice(source.indexOf('function reviewView('),source.indexOf('function notesView(')),context);
  const row={id:'r',status:'presence',matchMethod:'reference',candidates:[{vendor:'Alpha',invoiceNumber:'00042',amount:18400}],activity:[]};
  const html=context.reviewView({confirmed:true},row,[row]);
  assert.match(html,/<option value="Reviewed — no action needed" selected>Reviewed — no action needed<\/option>/);
  assert.deepEqual(resolutions,{});
  context.docDetail=()=>({readOnly:true});
  assert.doesNotMatch(context.reviewView({confirmed:true},row,[row]),/<option selected>Reviewed — no action needed/);
  context.docDetail=()=>null;row.status='unverified';context.statuses.unverified={label:'Not checked'};
  assert.match(context.reviewView({confirmed:true},row,[row]),/<option value="" selected>Choose a review decision/);
});

test('automatic comparison updates redraw the open statement without overwriting unsaved input',()=>{
  let renders=0;const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,state:{selected:'s'},dirty:new Set(),overlay:{querySelector:()=>({})},render(){},renderDrawer(){renders++;}};
  vm.runInNewContext(source.slice(source.indexOf('function receiveShared('),source.indexOf('async function startShared(')),context);
  context.receiveShared({provider:{label:'Latest'},statements:[],mappings:{},resolutions:{}});assert.equal(renders,1);
  context.dirty.add('s');context.receiveShared({provider:{label:'Latest'},statements:[],mappings:{},resolutions:{}});assert.equal(renders,1);
});

test('automatic redraw preserves keyboard focus and the statement scroll position',()=>{
  const document={activeElement:null};let drawer={scrollTop:340,contains:()=>true};
  let close={id:'',dataset:{action:'close'},focus(){document.activeElement=this;}};document.activeElement=close;
  const overlay={querySelector(selector){return selector==='.drawer'?drawer:selector==='.close'?close:null;},querySelectorAll(){return [close];}};
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,state:{selected:'s'},dirty:new Set(),document,overlay,render(){},renderDrawer(){drawer={scrollTop:0,contains:()=>true};close={id:'',dataset:{action:'close'},focus(){document.activeElement=this;}};}};
  vm.runInNewContext(source.slice(source.indexOf('function receiveShared('),source.indexOf('async function startShared(')),context);
  context.receiveShared({provider:{},statements:[],mappings:{},resolutions:{}});
  assert.equal(drawer.scrollTop,340);assert.equal(document.activeElement,close);
});

test('changing the review dropdown protects the unsaved choice from comparison redraws',()=>{
  let changed;const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,saveState:'saved',state:{selected:'s'},dirty:new Set(),sharedStatus(){},document:{addEventListener(type,handler){if(type==='change')changed=handler;}}};
  vm.runInNewContext(source.slice(source.indexOf('function markDirty('),source.indexOf('function decorateSharedUi(')),context);
  vm.runInNewContext(source.slice(source.indexOf("document.addEventListener('change'"),source.indexOf("document.addEventListener('click'")),context);
  changed({target:{id:'review-decision',value:'Follow up with vendor'}});
  assert.equal(context.dirty.has('s'),true);
});

test('top Save changes retains the selected review decision as well as the note',async()=>{
  const doc={id:'s',confirmed:true},saved=[];
  const nodes={'#review-note':{value:'Keep my follow-up'},'#review-decision':{value:'Check payment timing'}};
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,action:'save-session',state:{selected:'s',selectedRow:'r',drawerTab:'review',statements:[doc],resolutions:{}},getDoc:()=>doc,comparisonsFor:()=>[{id:'r',status:'presence'}],document:{querySelector:s=>nodes[s]},ready(){},render(){},renderDrawer(){},toast(){},async persistDoc(){saved.push(structuredClone(context.state.resolutions));}};
  const block=source.slice(source.indexOf("if (action === 'save-session')"),source.indexOf("if (action === 'disconnect')"));
  await vm.runInNewContext('(async()=>{'+block+'})()',context);
  assert.equal(saved[0].r.decision,'Check payment timing');assert.equal(saved[0].r.note,'Keep my follow-up');
});

test('finish dialog acknowledges confirmed invoice presence together without silently saving reviews',async()=>{
  const doc={id:'s',confirmed:true,rows:[{id:'r'}]},resolutions={r:{note:'Keep this'}};
  let opened=false;const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,action:'complete-dialog',getDoc:()=>doc,dirty:new Set(),completionReviews,completionPayload,
    comparisonsFor:()=>[{id:'r',status:'presence'}],state:{resolutions},shared:{state:{details:new Map([['s',{version:4}]])}},modal(){opened=true;},esc:String};
  const block=source.slice(source.indexOf("if(action==='complete-dialog')"),source.indexOf("if(action==='complete-statement')"));
  await vm.runInNewContext('(async()=>{'+block+'})()',context);
  assert.equal(opened,true);assert.equal(resolutions.r.decision,undefined);
});

test('inline vendor confirmation refuses to discard unsaved edits',async()=>{
  const doc={id:'s',vendor:'Rinella'};let saved=0;
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,action:'vendor-confirm',getDoc:()=>doc,dirty:new Set(['s']),target:{dataset:{vendor:'A.J. Rinella'}},confirmVendor:async()=>{saved++;},ready(){},state:{},shared:{},persistDoc(){},render(){},renderDrawer(){},toast(){}};
  const start=source.indexOf("if(action==='vendor-confirm'");
  assert.ok(start>=0,'The inline choice must have an application handler');
  const block=source.slice(start,source.indexOf("if(action==='confirm-reading')",start));
  await assert.rejects(vm.runInNewContext('(async()=>{'+block+'})()',context),/Save.*before/i);
  assert.equal(saved,0);
});

test('preliminary results cannot invite saved review decisions before the PDF is confirmed',()=>{
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,docDetail:()=>null,defaultReviewDecision:simpleFlow.defaultReviewDecision,reviewDecision:()=>null,money:String,esc:String,icon:()=>'',badge:()=>'',pdfPanel:()=>'',state:{provider:{loaded:true},resolutions:{}},statuses:{presence:{label:'Invoice found'}}};
  vm.runInNewContext(source.slice(source.indexOf('function creditExportLimitationHTML('),source.indexOf('function connectionPanel(')),context);
  vm.runInNewContext(source.slice(source.indexOf('function reviewView('),source.indexOf('function notesView(')),context);
  const doc={confirmed:false},row={id:'r',status:'presence',candidates:[],activity:[]};
  assert.doesNotMatch(context.reviewView(doc,row,[row]),/data-action="resolve"|id="review-note"/);
  doc.confirmed=true;assert.match(context.reviewView(doc,row,[row]),/data-action="resolve"/);
});

test('invoice details can render beneath the overview without duplicating the original PDF',()=>{
  let previews=0;const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,docDetail:()=>null,defaultReviewDecision:simpleFlow.defaultReviewDecision,reviewDecision:()=>null,money:String,esc:String,icon:()=>'',badge:()=>'',pdfPanel:()=>{previews++;return '<canvas></canvas>';},state:{provider:{loaded:true},resolutions:{}},statuses:{presence:{label:'Invoice found'}}};
  vm.runInNewContext(source.slice(source.indexOf('function creditExportLimitationHTML('),source.indexOf('function connectionPanel(')),context);
  vm.runInNewContext(source.slice(source.indexOf('function reviewView('),source.indexOf('function notesView(')),context);
  const row={id:'r',status:'presence',candidates:[],activity:[]};
  context.reviewView({confirmed:true},row,[row],false);assert.equal(previews,0);
});
test('a frozen history revision uses its own original-PDF availability',()=>{
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,icon:()=>'',files:new Map(),shared:{state:{details:new Map()}},docDetail:()=>({readOnly:true,originalAvailable:true}),state:{page:1}};
  vm.runInNewContext(source.slice(source.indexOf('function pdfPanel('),source.indexOf('function reviewView(')),context);
  assert.match(context.pdfPanel({id:'completed',pageCount:1}),/<canvas/);
});

test('closing a statement cannot destroy unsaved optional notes',()=>{
  const state={selected:'s',selectedRow:'r'},overlay={innerHTML:'unsaved note editor',querySelector:()=>({})};
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,state,overlay,dirty:new Set(['s']),toast(){},historicalDetail:null,priorFocus:null,renderToken:0};
  vm.runInNewContext(source.slice(source.indexOf('function closeOverlay('),source.indexOf('function getDoc(')),context);
  context.closeOverlay();assert.equal(overlay.innerHTML,'unsaved note editor');assert.equal(state.selected,'s');
});

test('invoice selection cannot rebuild editable controls during a pending save',()=>{
  let renders=0;const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,saveState:'saving',dirty:new Set(),state:{selected:'s',selectedRow:'one'},e:{target:{id:'row-select',value:'two'}},toast(){},comparisonsFor:()=>[],getDoc:()=>({}),renderDrawer(){renders++;}};
  const block=source.slice(source.indexOf("if (e.target.id === 'row-select')"),source.indexOf("if (e.target.id === 'provider-date')"));
  vm.runInNewContext('(function(){'+block+'})()',context);
  assert.equal(context.state.selectedRow,'one');assert.equal(context.e.target.value,'one');assert.equal(renders,0);
});
test('save acknowledgements re-enable controls disabled during a shared write',()=>{
  const button={disabled:true};const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,docDetail:()=>null,saveState:'saving',sharedError:null,retryOperation:null,shared:{state:{ready:true,details:new Map()}},state:{selected:null},overlay:{querySelectorAll:()=>[]},document:{querySelector:()=>null,querySelectorAll:()=>[button]}};
  vm.runInNewContext(source.slice(source.indexOf('function sharedStatus('),source.indexOf('function receiveShared(')),context);
  context.sharedStatus('saved');assert.equal(button.disabled,false);context.sharedStatus('saving');assert.equal(button.disabled,true);
});
test('shared UI decoration does not duplicate navigation and save status on errors',()=>{
  let navAdds=0,statusAdds=0;const nav={querySelector:()=>navAdds?{}:null,insertAdjacentHTML(){navAdds++;}},actions={insertAdjacentHTML(){statusAdds++;}};
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,billUpdateProgress:null,saveState:'saved',sharedError:null,shared:{state:{ready:true}},state:{view:'statements',statements:[]},icon:()=>'',esc:String,
    document:{querySelector:selector=>selector==='.nav'?nav:selector==='.top-actions'?actions:selector==='#shared-save-status'&&statusAdds?{}:null,querySelectorAll:()=>[]}};
  vm.runInNewContext(source.slice(source.indexOf('function decorateSharedUi('),source.indexOf('function historyPanel(')),context);
  context.decorateSharedUi();context.decorateSharedUi();assert.equal(navAdds,1);assert.equal(statusAdds,1);
});
test('startup retry assembles the entire workspace rather than returning a raw bootstrap reply',async()=>{
  let fail=true;const client={};const workspace={state:{ready:false},async load(){if(fail)throw Object.assign(Error('offline'),{retry:async()=>({activeImport:null})});this.state.ready=true;return this.state;}};
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,shared:null,window:{hwfcSharedClient:client},createSharedWorkspace:()=>workspace,receiveShared(){},sharedError:null,retryOperation:null,render(){},sharedStatus(status,error){context.status=status;context.retryOperation=error?.retry||null;}};
  vm.runInNewContext(source.slice(source.indexOf('async function startShared('),source.indexOf("window.addEventListener('hwfc:shared-ready'")),context);
  await context.startShared();fail=false;await context.retryOperation();assert.equal(workspace.state.ready,true);assert.equal(context.status,'saved');
});
test('opening an old completion does not substitute current draft fields or change draft decisions',async()=>{
  const id=crypto.randomUUID(),draft={id,vendor:'Edited vendor',notes:'Unsaved draft notes'},frozen={id,vendor:'Old vendor',notes:'Old completed notes'};
  const details=new Map([[id,{doc:draft,version:8}]]),current={note:'Draft review',decision:'Follow up with vendor'};
  const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,closeQuickPreview(){},historicalDetail:null,historySelection:null,historyPage:{items:[{id:'event',statementId:id,revisionId:'revision'}]},state:{selected:id,statements:[draft],resolutions:{r:current}},shared:{state:{details},statement:async()=>({doc:frozen,resolutions:{r:{decision:'Reviewed — no action needed'}},results:[],readOnly:true})},target:{dataset:{event:'event'}},action:'history-open',openDoc(){}};
  const action=source.slice(source.indexOf("if(action==='history-open')"),source.indexOf("if(action==='complete-dialog')"));
  await vm.runInNewContext('(async()=>{'+action+'})()',context);
  vm.runInNewContext(source.slice(source.indexOf('function getDoc('),source.indexOf('function openDoc(')),context);
  assert.equal(context.getDoc().vendor,'Old vendor');assert.equal(context.getDoc().notes,'Old completed notes');assert.equal(details.get(id).doc,draft);assert.equal(context.state.resolutions.r,current);
});
test('export of a selected historical revision uses only that revision evidence and notes',()=>{
  const doc={id:'s',vendor:'Old vendor',filename:'old.pdf',statementDate:'2026-09-01',notes:'Old notes'},row={id:'r',statementId:'s',vendor:'Old vendor',invoiceNumber:'001',kind:'invoice',originalAmount:18400,outstanding:18400,status:'possible',reason:'Old reason'};
  const detail={doc,results:[row],resolutions:{r:{decision:'Reviewed — no action needed',note:'Old review note'}},readOnly:true,importId:'old-import',importLabel:'old.csv',ruleVersion:'ap-match-v2'};
  let exported;const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row).label,state:{selected:'s',statements:[{...doc,filename:'new.pdf'}],resolutions:{r:{note:'New draft note'}},provider:{label:'new.csv'}},shared:{state:{details:new Map([['s',{doc:{...doc,filename:'new.pdf'},readOnly:false}]])}},historicalDetail:detail,historySelection:{initials:'KC',completedAt:'2026-09-01T12:00:00Z'},docDetail:()=>detail,getDoc:()=>doc,comparisonsFor:()=>[row],results:()=>[],reviewDecision:()=>detail.resolutions.r,statuses:{possible:{label:'Possible match'}},toCSV:rows=>rows,download:(name,rows)=>{exported=rows;},toast(){},action:'export'};
  vm.runInNewContext(source.slice(source.indexOf("if (action === 'export')"),source.indexOf('} catch(error)',source.indexOf("if (action === 'export')"))),context);
  assert.ok(exported[1]);assert.ok(exported[1].includes('old.pdf'));assert.ok(exported[1].includes('Old review note'));assert.ok(exported[1].includes('old-import'));assert.ok(!JSON.stringify(exported).includes('new.pdf'));
});

test('export of an older editable draft labels its pinned source rather than the latest weekly export',()=>{
  const doc={id:'s',vendor:'Synthetic',filename:'draft.pdf',statementDate:'2026-10-01',notes:''},row={id:'r',statementId:'s',vendor:'Synthetic',status:'possible'};
  const detail={doc,readOnly:false,importId:'old-import',importInfo:{metadata:{label:'pinned.csv'}}};
  let exported;const context={shared:null,duplicateInput:()=>false,duplicateSourceKey:'',duplicateReturn:null,duplicateDrafts:{clear(){}},...referenceReview,MATCH_RULE_VERSION,resultBadge:row=>referenceReview.invoiceResult(row).label,state:{statements:[doc],resolutions:{},provider:{label:'latest.csv'}},shared:{state:{details:new Map([['s',detail]])}},historicalDetail:null,docDetail:()=>detail,results:()=>[row],reviewDecision:()=>null,statuses:{possible:{label:'Possible'}},toCSV:rows=>rows,download:(name,rows)=>exported=rows,toast(){},action:'export'};
  vm.runInNewContext(source.slice(source.indexOf("if (action === 'export')"),source.indexOf('} catch(error)',source.indexOf("if (action === 'export')"))),context);
  assert.ok(exported[1].includes('pinned.csv'));assert.ok(!exported[1].includes('latest.csv'));
});
