import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {reconcile,money,statuses} from '../app/ap_statements/frontend/core.mjs';
import {defaultReviewDecision,invoiceFound} from '../app/ap_statements/frontend/simple-flow.mjs';
import * as review from '../app/ap_statements/frontend/reference-review.mjs';
import {completionPayload} from '../app/ap_statements/frontend/history.mjs';
import {createComparisonSource} from '../app/ap_statements/frontend/comparison-source.mjs';
const vendor='Adventure in Food Trading Company';
const doc=(reference='271712',amount=129981)=>({id:'s',vendor,confirmed:true,layout:'aif',statementDate:'2026-10-01',declaredTotal:amount,pageCount:1,rows:[{id:'r',type:'invoice',invoiceNumber:reference,amount,balance:amount,page:1,confidence:99}]});
const bill=(reference='271712X',amount=129981,other={})=>({id:reference,vendor,invoiceNumber:reference,amount,kind:'invoice',comparisonScope:'invoice-only',status:'PaidInFull',...other});
const compare=(statement=doc(),records=[bill()],mappings={})=>reconcile(statement,{loaded:true,simulated:false,records},mappings)[0];

test('Adventure unique trailing-letter reference with equal cents is found automatically and preserves originals',()=>{
  const statement=doc(),records=[bill()],before=structuredClone({statement,records});
  const row=compare(statement,records);
  assert.equal(row.status,'presence');assert.equal(row.matchMethod,'reference');assert.equal(invoiceFound(row),true);
  assert.equal(row.invoiceNumber,'271712');assert.equal(row.candidates[0].invoiceNumber,'271712X');
  assert.match(row.reason,/trailing letter/i);assert.equal(defaultReviewDecision(row),'Reviewed — no action needed');
  assert.deepEqual({statement,records},before);
});
test('Adventure suffix matching works in both directions and ignores letter case without losing leading zeroes',()=>{
  for(const [statement,record,want] of [['271712x','271712','presence'],['271712X','271712Y','presence'],['0271712','271712X','possible']]){
    assert.equal(compare(doc(statement),[bill(record)]).status,want);
  }
});
test('Adventure related reference with a different amount stays an explicit discrepancy, even one cent',()=>{
  for(const reference of ['271712','271712X']){
    const row=compare(doc(),[bill(reference,129980),bill('999999',129981)]);
    assert.equal(row.status,'amount');assert.equal(row.matchMethod,'reference');assert.equal(row.candidates.length,1);
    assert.equal(row.candidates[0].invoiceNumber,reference);assert.equal(invoiceFound(row),false);
    assert.equal(review.invoiceResult(row).label,'Amount discrepancy');
    assert.equal(defaultReviewDecision(row),'Investigate amount difference');
    const html=review.adventureDiscrepancyHTML?.(row)||'';
    assert.match(html,/\$1,299\.81/);assert.match(html,/\$1,299\.80/);assert.match(html,/\$0\.01/);
    assert.match(html,/payment/i);assert.doesNotMatch(html,/was overpaid|was underpaid/i);
  }
});
test('different Adventure invoice digits never become found or an amount discrepancy just from equal amounts',()=>{
  for(const reference of ['271713X','27171X','271712XX','A271712']){
    const row=compare(doc(),[bill(reference)]);
    assert.equal(row.status,'possible');assert.equal(invoiceFound(row),false);
    assert.equal(review.adventureDiscrepancyHTML?.(row)||'','');
  }
});
test('multiple Adventure base-number candidates require a choice even with an exact number or one equal amount',()=>{
  const row=compare(doc(),[bill('271712',129981),bill('271712X',129980)]);
  assert.equal(row.status,'ambiguous');assert.equal(row.matchMethod,'reference');assert.equal(row.candidates.length,2);
  assert.equal(invoiceFound(row),false);assert.equal(defaultReviewDecision(row),'');
});
test('suffix rule requires the resolved Adventure vendor and never applies to another company or credits',()=>{
  for(const name of ['Other Vendor','Adventure in Food Outlet','Unidentified vendor']){
    const statement={...doc(),vendor:name};
    assert.notEqual(compare(statement,[bill('271712X',129981,{vendor:name})]).status,'presence');
  }
  assert.equal(compare({...doc(),vendor:'Adventure in Food'},[bill()]).status,'vendor');
  assert.equal(compare({...doc(),vendor:'Adventure in Food'},[bill()],{'Adventure in Food':vendor}).status,'presence');
  assert.equal(compare(doc(),[bill('271712X',129981,{vendor:'Other Vendor'})],{[vendor]:'Other Vendor'}).status,'possible');
  const credit=doc();credit.rows[0].type='credit';credit.rows[0].amount=-129981;
  assert.notEqual(compare(credit,[bill('271712X',-129981,{kind:'credit'})]).status,'presence');
});
test('uncertain source, currency and PDF reading cannot be bypassed by Adventure suffix matching',()=>{
  assert.equal(compare(doc(),[bill('271712X',129981,{sourceIssues:'Check export'})]).status,'source');
  assert.equal(compare(doc(),[bill('271712X',129981,{currency:'EUR'})]).status,'amount');
  const uncertain=doc();uncertain.rows[0].confidence=20;assert.equal(compare(uncertain).status,'extraction');
  assert.equal(compare({...doc(),confirmed:false}).status,'extraction');
});

test('new Adventure results retain missing-currency warnings and identify scheduled payment without claiming settlement',()=>{
  const found=compare();assert.match(found.reason,/currency.*not verified/i);
  const discrepancy=compare(doc(),[bill('271712X',129980)]);
  assert.match(discrepancy.reason,/currency.*not verified/i);
  assert.match(review.adventureDiscrepancyHTML(discrepancy),/currency.*not verified/i);
  const scheduled=compare(doc(),[bill('271712X',129981,{status:'Scheduled'})]);
  assert.equal(invoiceFound(scheduled),true);assert.equal(review.invoiceResult(scheduled).label,'Invoice found');
  assert.match(scheduled.reason,/scheduled/i);assert.match(scheduled.reason,/settlement.*not verified/i);
});

test('legacy frozen amount reviews retain their original result and decision wording',()=>{
  const legacy=compare(doc(),[bill('271712',129980)]);delete legacy.referenceRule;
  assert.equal(review.invoiceResult(legacy,{decision:'Follow up with vendor'}).label,'Amount differs');
  assert.equal(review.adventureDiscrepancyHTML(legacy),'');
  const options=review.reviewDecisionOptions(legacy);
  assert.ok(options.some(([value,label])=>value==='Follow up with vendor'&&label==='Follow up with vendor'));
  assert.ok(!options.some(([,label])=>label==='Request vendor credit'));
});

test('known Adventure reference discrepancies do not ask for a redundant reference confirmation',()=>{
  const row=compare(doc(),[bill('271712X',129980)]);
  assert.equal(review.referenceReviewHTML(doc(),row),'');
});

test('explicit Adventure follow-up choices preserve notes and record durable intent without issuing financial commands',()=>{
  const row=compare(doc(),[bill('271712X',129980)]);
  assert.equal(typeof review.adventureFollowUp,'function');
  const credit=review.adventureFollowUp(row,'credit','Original note');
  assert.equal(credit.decision,'Follow up with vendor');assert.match(credit.note,/Original note/);
  assert.match(credit.note,/Request vendor credit/);assert.match(credit.note,/271712X/);
  assert.equal(review.adventureFollowUp(row,'credit',credit.note).note,credit.note);
  assert.equal(review.adventureFollowUp(row,'bill').decision,'Request missing invoice');
  assert.match(review.adventureFollowUp(row,'bill').note,/Additional bill needed/);
  assert.equal(review.adventureFollowUp(row,'investigate').decision,'Investigate amount difference');
  assert.throws(()=>review.adventureFollowUp(row,'unknown'),/follow-up/i);
  assert.throws(()=>review.adventureFollowUp(compare(),'credit'),/discrepancy/i);
  assert.doesNotMatch(review.adventureDiscrepancyHTML(row,true),/data-action="adventure-follow-up"/);
});

test('saved comparison snapshots retain the rule marker while legacy data has no invented marker',async()=>{
  const {comparisonSnapshot}=await import('../app/ap_statements/frontend/shared-workspace.mjs');
  const rows=comparisonSnapshot(doc(),{loaded:true,records:[bill('271712X',129980)]},{});
  assert.equal(rows[0].referenceRule,'adventure-trailing-letter-v1');
  assert.equal(review.invoiceResult(rows[0]).label,'Amount discrepancy');
  const legacy={...rows[0]};delete legacy.referenceRule;
  assert.equal(review.invoiceResult(legacy).label,'Amount differs');
});

test('Adventure follow-up button saves the chosen intent and existing note without creating a BILL operation',async()=>{
  const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
  const start=source.indexOf("if(action==='adventure-follow-up')"),end=source.indexOf("if (action === 'resolve')",start);
  const row=compare(doc(),[bill('271712X',129980)]),writes=[];
  const state={selectedRow:row.id,resolutions:{[row.id]:{note:'Existing note'}}};
  const context={...review,action:'adventure-follow-up',target:{dataset:{followup:'bill'}},state,getDoc:()=>doc(),comparisonsFor:()=>[row],
    document:{querySelector:selector=>selector==='#review-note'?{value:'Existing note'}:null},
    persistDoc:async()=>writes.push(structuredClone(state.resolutions[row.id])),render(){},renderDrawer(){},toast(){}};
  await vm.runInNewContext('(async()=>{'+source.slice(start,end)+'})()',context);
  assert.equal(writes.length,1);assert.equal(writes[0].decision,'Request missing invoice');
  assert.match(writes[0].note,/Existing note/);assert.match(writes[0].note,/Additional bill needed/);
  assert.match(writes[0].note,/271712X/);assert.equal(writes[0].at,undefined);
});

test('scoped saved-data lookup retrieves a suffixed reference even when its amount differs',async()=>{
  const importId='00000000-0000-4000-8000-000000000001';
  const directory=[{vendor}],records=[bill('271712X',129980,{id:importId+':0'}),bill('999999',129981,{id:importId+':1'})];
  const vendorDigest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(directory))))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const calls=[];const client={async request(action,payload){
    if(action==='bill_vendors_page')return {importId,vendors:directory,total:1,vendorDigest,nextCursor:null};
    assert.equal(action,'bill_candidates_page');calls.push(payload.query);
    assert.ok(payload.query.references.length+payload.query.amounts.length<=100);
    const matches=records.filter(record=>payload.query.references.some(key=>key.invoiceKey===record.invoiceNumber&&key.kind===record.kind)||payload.query.amounts.some(key=>key.vendorKey===record.vendor.toLowerCase()&&key.kind===record.kind&&key.amount===record.amount));
    return {importId,queryDigest:'a'.repeat(64),total:matches.length,records:matches,afterOrdinal:-1,nextCursor:null};
  }};
  const source=createComparisonSource(client),provider=await source.loadDirectory({id:importId,record_count:2,metadata:{}});
  await source.ensure(doc());const row=reconcile(doc(),provider)[0];
  assert.equal(row.status,'amount');assert.equal(row.candidates[0].invoiceNumber,'271712X');
  assert.ok(calls.some(q=>q.references.some(ref=>ref.invoiceKey==='271712X')));
  source.dispose();
});

test('Adventure discrepancy UI offers credit and additional-bill follow-up without changing validated decision values',()=>{
  const row=compare(doc(),[bill('271712X',129980)]),source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
  const context={...review,defaultReviewDecision,money,statuses,esc:String,icon:()=>'',resultBadge:()=>review.invoiceResult(row).label,
    docDetail:()=>null,reviewDecision:()=>null,pdfPanel:()=>'',state:{provider:{loaded:true},resolutions:{}}};
  vm.runInNewContext(source.slice(source.indexOf('function reportedMoney('),source.indexOf('function toast(')),context);
  vm.runInNewContext(source.slice(source.indexOf('function reviewView('),source.indexOf('function notesView(')),context);
  const html=context.reviewView(doc(),row,[row],false);
  assert.match(html,/Amount discrepancy/);assert.match(html,/Request vendor credit/);assert.match(html,/Additional bill needed/);
  assert.ok(html.indexOf('class="notice amber adventure-discrepancy"')<html.indexOf('class="evidence-grid"'),'Put the discrepancy actions above the long evidence cards');
  assert.match(html,/<option value="Investigate amount difference" selected>Investigate amount difference<\/option>/);
  assert.doesNotMatch(html,/data-action="(?:create-bill|send-credit)/);
  assert.doesNotThrow(()=>completionPayload({doc:doc(),results:[row],resolutions:{[row.id]:{decision:'Check credit application'}},initials:'KC',expectedVersion:1}));
});
