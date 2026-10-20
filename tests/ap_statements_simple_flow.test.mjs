import test from 'node:test';
import assert from 'node:assert/strict';
import {reconcile} from '../app/ap_statements/frontend/core.mjs';
const doc=()=>({id:'s',vendor:'A.J. Rinella',filename:'statement.pdf',layout:'generic',confirmed:true,statementDate:'2026-10-01',declaredTotal:18400,warnings:[],rows:[{id:'r',type:'invoice',invoiceNumber:'00042',amount:18400,balance:18400,page:1,confidence:99}]});
const bill=(vendor='A.J. Rinella & Co., Inc.')=>({id:'b',vendor,invoiceNumber:'00042',amount:18400,currency:'USD'});
const provider=(records=[bill()])=>({loaded:true,simulated:false,label:'Bills.csv',refreshedAt:'2026-10-01T12:00:00Z',records});
async function flow(){const m=await import('../app/ap_statements/frontend/simple-flow.mjs').catch(()=>null);assert.ok(m,'The upload-and-review flow must exist');return m;}
async function view(){const m=await import('../app/ap_statements/frontend/simple-flow-view.mjs').catch(()=>null);assert.ok(m,'The simplified flow presentation must exist');return m;}

test('a unique legal-suffix and punctuation variation matches without manual mapping',()=>{
  assert.equal(reconcile(doc(),provider())[0].status,'matched');
});
test('similar legal names that collide in the saved source require a human choice',()=>{
  const d={...doc(),vendor:'Acme'};
  assert.equal(reconcile(d,provider([bill('Acme Inc.'),bill('Acme LLC')]))[0].status,'vendor');
});
test('a repeated reference alone never establishes vendor identity',()=>{
  assert.equal(reconcile({...doc(),vendor:'Unidentified vendor'},provider([bill('Completely Different Vendor')]))[0].status,'vendor');
});
test('vendor choices prioritize name suggestions but allow choosing another saved vendor',async()=>{
  const {resolveStatementVendor}=await import('../app/ap_statements/frontend/vendor-identity.mjs').catch(()=>({}));
  assert.equal(typeof resolveStatementVendor,'function');
  const choice=resolveStatementVendor('Rinella',[bill(),bill('Other Vendor')],{});
  assert.equal(choice.status,'confirm');assert.equal(choice.candidates[0],'A.J. Rinella & Co., Inc.');
  assert.ok(choice.choices.includes('Other Vendor'));
});
test('an explicit remembered choice takes priority over automatic name recognition',async()=>{
  assert.equal(reconcile(doc(),provider([bill(),bill('Chosen Vendor')]),{'A.J. Rinella':'Chosen Vendor'})[0].candidates[0].vendor,'Chosen Vendor');
});
test('automatic comparisons are preliminary until reading is confirmed and never mutate the statement',async()=>{
  const {statementComparisons}=await flow(),d={...doc(),confirmed:false},before=structuredClone(d);
  const row=statementComparisons(d,provider(),{})[0];
  assert.equal(row.status,'presence');assert.equal(row.preview,true);assert.match(row.reason,/preliminary/i);
  assert.deepEqual(d,before);assert.equal(reconcile(d,provider())[0].status,'extraction');
});
test('unclear OCR remains flagged rather than becoming an automatic invoice match',async()=>{
  const {statementComparisons}=await flow(),d=doc();d.confirmed=false;d.rows[0].confidence=45;
  assert.equal(statementComparisons(d,provider(),{})[0].status,'extraction');
});
test('weekly BILL refresh is a reminder not a barrier to checking arriving statements',async()=>{
  const {billDataSummary}=await flow();
  const summary=billDataSummary(provider(),new Date('2026-10-09T12:00:00Z'));
  assert.equal(summary.ready,true);assert.equal(summary.updateDue,true);assert.equal(summary.count,1);
  assert.equal(billDataSummary({...provider(),refreshedAt:'bad'},new Date()).dateKnown,false);
});
test('inline vendor question offers confirmation and another choice without a separate mapping screen',async()=>{
  const {vendorQuestionHTML}=await view();
  const html=vendorQuestionHTML({...doc(),vendor:'Rinella'},provider(),{});
  assert.match(html,/same vendor/i);assert.match(html,/Yes/);assert.match(html,/Choose another/);
  assert.match(html,/vendor-confirm/);assert.doesNotMatch(html,/save a vendor mapping/i);
});
test('saved BILL status is reusable while statement upload stays the primary workflow',async()=>{
  const {billDataHTML,uploadReviewHTML}=await view();
  const html=billDataHTML(provider(),new Date('2026-10-02T12:00:00Z'))+uploadReviewHTML({statements:[doc()],provider:provider(),errors:[],busy:false});
  assert.match(html,/Update BILL data/);assert.match(html,/Upload statements/);
  assert.match(html,/Last updated/);assert.doesNotMatch(html,/Step \d of 4|guide-step|vendor mapping/);
});
test('finishing can acknowledge found invoices together but never unresolved differences or existing follow-up',async()=>{
  const {completionReviews}=await flow();
  const original={r:{note:'Keep note'},a:{decision:'Follow up with vendor',note:'Already flagged'}};
  const rows=[{id:'r',status:'presence'},{id:'a',status:'presence'},{id:'missing',status:'missing'},{id:'p',status:'presence',preview:true}];
  const proposed=completionReviews(rows,original);
  assert.equal(proposed.r.decision,'Reviewed — no action needed');assert.equal(proposed.r.note,'Keep note');
  assert.equal(proposed.a.decision,'Follow up with vendor');assert.equal(proposed.missing,undefined);assert.equal(proposed.p,undefined);
  assert.equal(original.r.decision,undefined);
});

test('confirming an alias remembers the selected saved vendor with its current mapping version',async()=>{
  const {confirmVendor}=await flow();const d=doc(),calls=[];
  const shared={state:{provider:provider(),mappingVersions:{'A.J. Rinella':3}},async saveMapping(value,version){calls.push([value,version]);}};
  await confirmVendor(d,'A.J. Rinella & Co., Inc.',shared,async()=>{throw Error('Should not edit the original vendor');});
  assert.deepEqual(calls,[[{vendor:'A.J. Rinella',bill_vendor:'A.J. Rinella & Co., Inc.'},3]]);
});
test('unidentified vendors are corrected for this document without a global unknown alias',async()=>{
  const {confirmVendor}=await flow();const d={...doc(),vendor:'Unidentified vendor'},saved=[];
  const shared={state:{provider:provider(),mappingVersions:{}},async saveMapping(){throw Error('Unsafe unknown alias');}};
  await confirmVendor(d,'A.J. Rinella & Co., Inc.',shared,async document=>saved.push(structuredClone(document)));
  assert.equal(saved[0].vendor,'A.J. Rinella & Co., Inc.');assert.equal(saved[0].confirmed,false);
  await assert.rejects(confirmVendor(d,'Not in saved records',shared,async()=>{}),/saved BILL/i);
});

test('a reference under another vendor cannot block same-vendor amount suggestions',()=>{
  const d=doc();const own={...bill(),invoiceNumber:'different'},other={...bill('Other Vendor'),amount:99900};
  const row=reconcile(d,provider([own,other]))[0];
  assert.equal(row.status,'possible');assert.equal(row.matchMethod,'amount');assert.equal(row.candidates[0].vendor,'A.J. Rinella & Co., Inc.');
});

test('default review decisions accept only clear reference matches and preserve user choices',async()=>{
  const {defaultReviewDecision}=await flow();
  const exact=reconcile(doc(),provider())[0];
  assert.equal(defaultReviewDecision(exact),'Reviewed — no action needed');
  assert.equal(defaultReviewDecision({...exact,status:'presence'}),'Reviewed — no action needed');
  assert.equal(defaultReviewDecision(exact,{decision:'Check payment timing'}),'Check payment timing');
  for(const status of ['ambiguous','possible','missing','vendor','amount','balance','scheduled','source','unverified','extraction'])
    assert.equal(defaultReviewDecision({...exact,status}),'');
  assert.equal(defaultReviewDecision({...exact,preview:true}),'');
  assert.equal(defaultReviewDecision({...exact,matchMethod:'amount'}),'');
  assert.equal(defaultReviewDecision({...exact,simulated:true}),'');
  assert.equal(defaultReviewDecision({...exact,candidates:[bill(),bill()]}),'');
});
