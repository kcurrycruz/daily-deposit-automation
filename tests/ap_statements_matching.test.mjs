import test from 'node:test';
import assert from 'node:assert/strict';
import { reconcile, money, statuses, toCSV } from '../app/ap_statements/frontend/core.mjs';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const row = {id:'row', invoiceNumber:'00042', type:'invoice', amount:18400, balance:18400, confidence:99, page:1};
const doc = {id:'doc', vendor:'Alpha', rows:[row], confirmed:true, statementDate:'2026-10-01'};
const bill = {id:'bill', vendor:'Alpha', invoiceNumber:'00042', amount:18400};
const run = (records, statement=doc, mappings={}) => reconcile(statement,{loaded:true,simulated:false,records},mappings)[0];

test('same-vendor exact reference retains normal checks and reference evidence', () => {
  const result = run([bill]); assert.equal(result.status,'matched'); assert.equal(result.matchMethod,'reference');
});
test('exact reference under another vendor requests vendor verification', () => {
  const result = run([{...bill,vendor:'Beta'}]); assert.equal(result.status,'vendor'); assert.equal(result.candidates[0].vendor,'Beta');
});
test('unresolved vendor does not select a repeated reference across vendors', () => {
  assert.equal(run([bill,{...bill,vendor:'Beta'}],{...doc,vendor:'Unknown'}).status,'vendor');
});
test('vendor mapping allows a same-vendor exact reference', () => {
  assert.equal(run([bill],{...doc,vendor:'A'}, {'A':'Alpha'}).status,'matched');
});
test('exact reference amount disagreement does not trigger another invoice fallback', () => {
  const result=run([{...bill,amount:18000},{...bill,invoiceNumber:'00043'}]);
  assert.equal(result.status,'amount'); assert.deepEqual(result.candidates.map(r=>r.invoiceNumber),['00042']);
});
test('absent number suggests an equal individual amount only within the same vendor', () => {
  const result=run([{...bill,invoiceNumber:'00043'},{...bill,vendor:'Beta',invoiceNumber:'00044'}]);
  assert.equal(result.status,'possible'); assert.equal(result.matchMethod,'amount');
  assert.equal(result.invoiceNumber,'00042'); assert.deepEqual(result.candidates.map(r=>r.invoiceNumber),['00043']);
});
test('equal amounts repeated within a vendor remain ambiguous', () => {
  const result=run([{...bill,invoiceNumber:'00043'},{...bill,invoiceNumber:'00044'}]);
  assert.equal(result.status,'ambiguous'); assert.equal(result.candidates.length,2); assert.equal(result.matchMethod,'amount');
});
test('equal amount does not cross vendors when no reference is found', () => {
  const result=run([{...bill,vendor:'Beta',invoiceNumber:'00043'}]); assert.equal(result.status,'vendor'); assert.equal(result.candidates.length,0);
});
test('leading-zero reference is preserved while amount evidence remains only a suggestion', () => {
  assert.equal(run([{...bill,invoiceNumber:'42'}]).status,'possible');
});
test('transaction kind must agree for reference and amount lookup', () => {
  assert.equal(run([{...bill,kind:'credit'}]).status,'missing');
});
test('null and non-integer source amounts cannot become amount suggestions', () => {
  assert.equal(run([{...bill,invoiceNumber:'43',amount:null}]).status,'missing');
  assert.equal(run([{...bill,invoiceNumber:'43',amount:18400.5}]).status,'missing');
});
test('uncertain source and foreign currency amount candidates stay reviewable', () => {
  for(const extra of [{sourceIssues:'Incomplete export'},{currency:'EUR'}]) {
    const result=run([{...bill,invoiceNumber:'43',...extra}]); assert.notEqual(result.status,'matched'); assert.equal(result.candidates.length,1);
  }
});
test('unconfirmed and low-confidence rows do not produce suggestions', () => {
  assert.equal(run([{...bill,invoiceNumber:'43'}],{...doc,confirmed:false}).status,'extraction');
  assert.equal(run([{...bill,invoiceNumber:'43'}],{...doc,rows:[{...row,confidence:50}]}).status,'extraction');
});
test('native-export exact reference remains invoice presence only', () => {
  assert.equal(run([{...bill,comparisonScope:'invoice-only',status:'PaidInFull'}]).status,'presence');
});
test('no provider remains unverified rather than missing', () => {
  assert.equal(reconcile(doc,{loaded:false,records:[bill]})[0].status,'unverified');
});
test('candidate evidence shows the vendor and reference rather than a database ID alone', () => {
  const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
  const functions=source.slice(source.indexOf('function reportedMoney('),source.indexOf('function toast('));
  const evidence=vm.runInNewContext(functions+'; ({candidateSummary,billEvidence})',{money,Intl});
  assert.match(evidence.candidateSummary(bill), /Alpha.*00042.*184/);
  for (const candidate of [bill,{...bill,comparisonScope:'invoice-only'}]) {
    assert.equal(evidence.billEvidence(candidate).find(([label])=>label==='Vendor')?.[1],'Alpha');
  }
});
test('amount-only report labels do not claim a verified invoice or balance', () => {
  const result=run([{...bill,invoiceNumber:'43'}]);
  const report=toCSV([[result.invoiceNumber,statuses[result.status].label,result.reason]]);
  assert.match(report,/Possible match/); assert.match(report,/suggestion, not a verified/);
});
