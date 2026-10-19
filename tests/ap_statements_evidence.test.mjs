import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {reconcile,money,statuses} from '../app/ap_statements/frontend/core.mjs';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const doc=()=>({id:'s',vendor:'Example Supplier',statementDate:'2026-07-03',layout:'rinella',confirmed:true,rows:[{id:'r',type:'invoice',invoiceNumber:'261601',amount:13800,balance:13800,page:1,confidence:99}]});
const bill=(invoiceNumber,id=invoiceNumber)=>({id,vendor:'Example Supplier',invoiceNumber,amount:13800,comparisonScope:'invoice-only',status:'PaidInFull'});
function render(row,statement=doc()){
  const context={reviewDecision:()=>null,money,esc,icon:()=>'',badge:()=>'',pdfPanel:()=>'',state:{provider:{loaded:true},resolutions:{}},statuses};
  vm.runInNewContext(source.slice(source.indexOf('function reportedMoney('),source.indexOf('function toast(')),context);
  vm.runInNewContext(source.slice(source.indexOf('function reviewView('),source.indexOf('function notesView(')),context);
  return context.reviewView(statement,row,[row],false);
}
function compare(records){return reconcile(doc(),{loaded:true,records})[0];}

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
