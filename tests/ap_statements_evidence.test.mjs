import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as referenceReview from '../app/ap_statements/frontend/reference-review.mjs';
import {reconcile,money,statuses} from '../app/ap_statements/frontend/core.mjs';
import {defaultReviewDecision} from '../app/ap_statements/frontend/simple-flow.mjs';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const doc=()=>({id:'s',vendor:'Example Supplier',statementDate:'2026-07-03',layout:'rinella',confirmed:true,rows:[{id:'r',type:'invoice',invoiceNumber:'261601',amount:13800,balance:13800,page:1,confidence:99}]});
const bill=(invoiceNumber,id=invoiceNumber)=>({id,vendor:'Example Supplier',invoiceNumber,amount:13800,comparisonScope:'invoice-only',status:'PaidInFull'});
function render(row,statement=doc(),resolution=null){
  const context={...referenceReview,resultBadge:row=>referenceReview.invoiceResult(row,resolution).label,docDetail:()=>null,defaultReviewDecision,reviewDecision:()=>resolution,money,esc,icon:()=>'',badge:()=>'',pdfPanel:()=>'',state:{provider:{loaded:true},resolutions:resolution?{[row.id]:resolution}:{}},statuses};
  vm.runInNewContext(source.slice(source.indexOf('function reportedMoney('),source.indexOf('function toast(')),context);
  vm.runInNewContext(source.slice(source.indexOf('function reviewView('),source.indexOf('function notesView(')),context);
  return context.reviewView(statement,row,[row],false);
}
function compare(records){return reconcile(doc(),{loaded:true,records})[0];}

test('manual confirmation shows the selected invoice while keeping the old unselected reason in collapsed evidence',()=>{
  const row=compare([bill('261768'),bill('261874')]);
  const saved={...referenceReview.confirmInvoiceCandidate(doc(),row,1),at:'2026-10-21T16:00:00Z'};
  const html=render(row,doc(),saved);
  assert.match(html,/<summary>Original comparison: Multiple matches<\/summary>/);
  assert.match(html,/<h3>Confirmed BILL invoice<\/h3>/);assert.match(html,/You confirmed BILL invoice/);
});

test('same-amount invoices are an unselected list, never a first-record comparison',()=>{
  const row=compare(['261768','261874','261673'].map(ref=>bill(ref)));
  const before=structuredClone(row),html=render(row);
  assert.equal(row.status,'ambiguous');assert.equal(row.invoiceNumber,'261601');
  assert.match(html,/<h3>Possible BILL matches<\/h3>/);
  assert.doesNotMatch(html,/<h3>Imported BILL record<\/h3>/);
  assert.equal((html.match(/class="bill-candidate"/g)||[]).length,3);
  for(const ref of ['261768','261874','261673'])assert.match(html,new RegExp('<summary[^>]*>[^<]*'+ref));
  assert.match(html,/No invoice has been selected/i);
  assert.deepEqual(row,before);
});

test('an exact same-vendor reference takes priority over other equal amounts',()=>{
  const row=compare([bill('261768'),bill('261601'),bill('261874')]),html=render(row);
  assert.equal(row.matchMethod,'reference');assert.equal(row.status,'presence');
  assert.match(html,/<h3>Imported BILL record<\/h3>/);
  assert.match(html,/261601/);assert.doesNotMatch(html,/261768|261874|bill-candidate/);
});

test('even one amount-only suggestion stays unselected with its different reference',()=>{
  const row=compare([bill('261768')]),html=render(row);
  assert.equal(row.status,'possible');
  assert.match(html,/<h3>Possible BILL matches<\/h3>/);
  assert.match(html,/261601/);assert.match(html,/261768/);
  assert.doesNotMatch(html,/<h3>Imported BILL record<\/h3>/);
});

test('duplicate exact references do not silently select the first export record',()=>{
  const row=compare([bill('261601','one'),bill('261601','two')]),html=render(row);
  assert.equal(row.matchMethod,'reference');assert.equal(row.status,'ambiguous');
  assert.equal((html.match(/class="bill-candidate"/g)||[]).length,2);
  assert.match(html,/No invoice has been selected/i);
  assert.doesNotMatch(html,/Invoice number was not found|No exact reference/i);
});

test('a source-warning amount fallback is still a suggestion, not a selected invoice',()=>{
  const row=compare([{...bill('261768'),sourceIssues:'Unreadable amount evidence'}]),html=render(row);
  assert.equal(row.status,'source');assert.equal(row.matchMethod,'amount');
  assert.match(html,/<h3>Possible BILL matches<\/h3>/);
  assert.doesNotMatch(html,/<h3>Imported BILL record<\/h3>/);
});

test('unresolved-vendor reference candidates are not displayed as confirmed BILL records',()=>{
  const statement={...doc(),vendor:'Unidentified vendor'};
  const row=reconcile(statement,{loaded:true,records:[bill('261601')]})[0],html=render(row,statement);
  assert.equal(row.status,'vendor');assert.match(html,/<h3>Possible BILL matches<\/h3>/);
  assert.doesNotMatch(html,/<h3>Imported BILL record<\/h3>/);
});

test('candidate text is escaped and an empty result has no suggestion list',()=>{
  const row=compare([bill('<script>bad</script>')]),html=render(row);
  assert.match(html,/&lt;script&gt;bad&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>/);
  const missing=render(compare([]));
  assert.doesNotMatch(missing,/bill-candidate/);assert.match(missing,/No matching record/);
});

test('a low-confidence scan says matching is pending verification rather than invoice missing',()=>{
  const statement=doc();statement.rows[0].confidence=65;
  const row=reconcile(statement,{loaded:true,records:[bill('261601')]})[0];
  const before=structuredClone(row),html=render(row,statement);
  assert.equal(row.status,'extraction');assert.equal(row.candidates.length,0);
  assert.match(html,/Matching pending PDF verification/);
  assert.match(html,/data-action="drawer-tab" data-tab="extraction"/);
  assert.match(html,/>Check PDF<\/button>/);
  assert.doesNotMatch(html,/No matching record|not found|<h3>Imported BILL record/);
  assert.deepEqual(row,before);assert.equal(statement.rows[0].confidence,65);
});

test('unavailable BILL comparisons never claim the reference is absent',()=>{
  const statement=doc(),row=reconcile(statement,{loaded:false,records:[]})[0];
  const html=render(row,statement);
  assert.equal(row.status,'unverified');
  assert.match(html,/not ready|unavailable/i);
  assert.doesNotMatch(html,/No matching record|not found/);
});

test('confirming accurate scan values allows the exact invoice record to appear',()=>{
  const statement=doc();statement.rows[0].confidence=65;
  assert.equal(reconcile(statement,{loaded:true,records:[bill('261601')]})[0].status,'extraction');
  statement.confirmed=true;statement.rows[0].confidence=99;
  const row=reconcile(statement,{loaded:true,records:[bill('261601')]})[0],html=render(row,statement);
  assert.equal(row.status,'presence');assert.equal(row.matchMethod,'reference');
  assert.match(html,/<h3>Imported BILL record<\/h3>/);
  assert.doesNotMatch(html,/Matching pending PDF verification/);
});
