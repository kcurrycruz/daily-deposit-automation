import test from 'node:test';
import assert from 'node:assert/strict';
import * as review from '../app/ap_statements/frontend/reference-review.mjs';
import {invoiceFound} from '../app/ap_statements/frontend/simple-flow.mjs';
import {statementOverviewHTML} from '../app/ap_statements/frontend/simple-flow-view.mjs';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const bill=(id,reference)=>({id,vendor:'Adventure in Food',invoiceNumber:reference,amount:129981,kind:'invoice',currency:'USD',comparisonScope:'invoice-only'});
const row=()=>({id:'r',kind:'invoice',invoiceNumber:'271712',originalAmount:129981,status:'possible',matchMethod:'amount',candidates:[bill('b1','271712X')]});
const stamp=value=>({...value,at:'2026-10-21T16:00:00Z'});
test('explicit acknowledged confirmation changes the visible badge and found count without changing comparison evidence',()=>{
  const r=row(),before=structuredClone(r),saved=stamp(review.confirmReferenceReview({confirmed:true},r));
  assert.equal(invoiceFound(r,saved),true);
  const html=statementOverviewHTML({confirmed:true,rows:[],declaredTotal:0},[r],false,{r:saved});
  assert.match(html,/1 found in BILL/);assert.match(html,/badge green[^>]*>Invoice found/);assert.doesNotMatch(html,/Possible match/);
  assert.deepEqual(r,before);
});
test('multiple matches require an explicit unique candidate choice and preserve that selected record',()=>{
  assert.equal(typeof review.confirmInvoiceCandidate,'function');
  const r={...row(),status:'ambiguous',candidates:[bill('b1','271712X'),bill('b2','271712Y')]};
  assert.throws(()=>review.confirmInvoiceCandidate({confirmed:true},r,null),/choose|candidate/i);
  const saved=stamp(review.confirmInvoiceCandidate({confirmed:true},r,1));
  assert.equal(invoiceFound(r,saved),true);assert.equal(review.confirmedInvoiceCandidate(r,saved).id,'b2');
  assert.match(saved.note,/271712Y/);assert.equal(r.status,'ambiguous');assert.equal(r.candidates.length,2);
});
test('candidate confirmation controls identify a choice and are absent from frozen or preliminary evidence',()=>{
  assert.equal(typeof review.candidateConfirmationHTML,'function');const r={...row(),status:'ambiguous',candidates:[bill('b1','271712X'),bill('b2','271712Y')]};
  assert.match(review.candidateConfirmationHTML({confirmed:true},r,1),/data-action="confirm-candidate" data-candidate="1"/);
  assert.equal(review.candidateConfirmationHTML({confirmed:true},r,1,true),'');assert.equal(review.candidateConfirmationHTML({confirmed:false},r,1),'');
});
test('opening a row, generic no-action review, follow-up and unacknowledged saves never turn suggestions green',()=>{
  const r=row();assert.equal(invoiceFound(r),false);assert.equal(invoiceFound(r,{decision:'Reviewed — no action needed',at:'2026-10-21T16:00:00Z'}),false);
  const confirmation=review.confirmReferenceReview({confirmed:true},r);
  assert.equal(invoiceFound(r,confirmation),false);
  assert.equal(invoiceFound(r,stamp({...confirmation,decision:'Follow up with vendor'})),false);
});
test('changed statement values, candidate evidence or source safety invalidate a confirmation',()=>{
  const r=row(),saved=stamp(review.confirmReferenceReview({confirmed:true},r));
  assert.equal(invoiceFound(r,saved),true);
  for(const changed of [{...r,invoiceNumber:'different'},{...r,originalAmount:129980},{...r,preview:true},{...r,simulated:true},{...r,status:'vendor'},{...r,candidates:[{...r.candidates[0],amount:100}]},{...r,candidates:[{...r.candidates[0],sourceIssues:'Unreadable'}]}])assert.equal(invoiceFound(changed,saved),false);
  assert.equal(invoiceFound(r,{}),false);
});
test('amount discrepancies and unsafe or indistinguishable candidates cannot be counted as found',()=>{
  assert.equal(typeof review.confirmInvoiceCandidate,'function');const r=row();
  const different={...r,status:'amount',candidates:[{...r.candidates[0],amount:100}]};
  const saved=stamp(review.confirmInvoiceCandidate({confirmed:true},different,0));assert.equal(saved.decision,'Investigate amount difference');assert.equal(invoiceFound(different,saved),false);
  for(const candidate of [{...r.candidates[0],currency:'CAD'},{...r.candidates[0],sourceIssues:'Unreadable'},{...r.candidates[0],kind:'credit'}])assert.throws(()=>review.confirmInvoiceCandidate({confirmed:true},{...r,candidates:[candidate]},0),/candidate|review/i);
  assert.throws(()=>review.confirmInvoiceCandidate({confirmed:false},r,0),/review/i);
  assert.throws(()=>review.confirmInvoiceCandidate({confirmed:true},{...r,status:'ambiguous',candidates:[r.candidates[0],r.candidates[0]]},0),/candidate|review/i);
});
test('an exact reference with an amount discrepancy is not described as a different reference',()=>{
  const r={...row(),status:'amount',matchMethod:'reference',candidates:[bill('b1','271712')]};r.candidates[0].amount=100;
  assert.equal(review.referenceReviewHTML({confirmed:true},r),'');
});
test('candidate action saves the requested record and only counts it after acknowledged readback',async()=>{
  const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
  const block=source.slice(source.indexOf("if(action==='confirm-reference'||"),source.indexOf("if (action === 'resolve')"));
  const r={...row(),status:'ambiguous',candidates:[bill('b1','271712X'),bill('b2','271712Y')]};
  let writes=0,pendingFound;
  const context={action:'confirm-candidate',target:{dataset:{candidate:'1'}},state:{selectedRow:'r',resolutions:{}},getDoc:()=>({id:'s',confirmed:true}),docDetail:()=>({readOnly:false}),comparisonsFor:()=>[r],...review,document:{querySelector:()=>null},render(){},renderDrawer(){},toast(){},async persistDoc(){writes++;pendingFound=invoiceFound(r,context.state.resolutions.r);context.state.resolutions.r=stamp(context.state.resolutions.r);}};
  await vm.runInNewContext('(async()=>{'+block+'})()',context);
  assert.equal(writes,1);assert.equal(pendingFound,false);assert.equal(invoiceFound(r,context.state.resolutions.r),true);assert.equal(context.state.resolutions.r.confirmedMatch.candidate.id,'b2');
  context.state.resolutions={};context.persistDoc=async()=>{throw Error('No acknowledgement');};
  await assert.rejects(vm.runInNewContext('(async()=>{'+block+'})()',context),/acknowledgement/);assert.equal(invoiceFound(r,context.state.resolutions.r),false);
  context.docDetail=()=>({readOnly:true});await assert.rejects(vm.runInNewContext('(async()=>{'+block+'})()',context),/read-only/);
});
test('global extraction save invalidates a prior confirmation while retaining the user note',async()=>{
  const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
  const r=row(),doc={id:'s',confirmed:true};let saved=false;
  const context={action:'save-session',state:{selected:'s',drawerTab:'extraction',statements:[doc],resolutions:{r:stamp({...review.confirmReferenceReview(doc,r),note:'Retain follow-up context'})}},ready(){},getDoc:()=>doc,groupInvoices:()=>[r],collectDoc:value=>value.confirmed=false,render(){},renderDrawer(){},toast(){},async persistDoc(){assert.equal(context.state.resolutions.r.confirmedMatch,undefined);assert.equal(context.state.resolutions.r.decision,undefined);saved=true;}};
  vm.runInNewContext(source.slice(source.indexOf('function invalidateReviewDecisions('),source.indexOf('function stats(')),context);
  const block=source.slice(source.indexOf("if (action === 'save-session')"),source.indexOf("if (action === 'disconnect')"));
  await vm.runInNewContext('(async()=>{'+block+'})()',context);assert.equal(saved,true);assert.equal(context.state.resolutions.r.note,'Retain follow-up context');
});
