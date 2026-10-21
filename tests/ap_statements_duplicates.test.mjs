import test from 'node:test';
import assert from 'node:assert/strict';
const module=await import('../app/ap_statements/frontend/statement-duplicates.mjs').catch(()=>null);
function assess(...args){assert.ok(module,'Statement content duplicate checks must exist');return module.assessStatement(...args);}
const row=(invoiceNumber,amount=13800,overrides={})=>({id:invoiceNumber,type:'invoice',invoiceNumber,amount,balance:amount,confidence:99,...overrides});
const doc=(rows,overrides={})=>({id:crypto.randomUUID(),vendor:'Alpha',statementDate:'2026-10-21',declaredTotal:rows.reduce((n,r)=>n+r.amount,0),rows,...overrides});
const prior=value=>({doc:value,detail:{doc:value,completed:true,readOnly:true},event:{id:'completed',statementId:value.id,revisionId:'revision'}});

test('same vendor date invoice numbers and amounts reuse saved statement despite new filename and row order',()=>{
  const old=doc([row('001'),row('002',2500)]),input=doc([row('002',2500),row(' 001 ')],{filename:'different.pdf'}),before=structuredClone(old);
  const result=assess(input,[prior(old)]);assert.equal(result.kind,'duplicate');assert.equal(result.match.doc.id,old.id);assert.deepEqual(old,before);
});
test('later statement with repeated and new invoices remains a new document',()=>{
  const old=doc([row('001')]),input=doc([row('001'),row('002')],{statementDate:'2026-10-28'});
  const result=assess(input,[prior(old)]);assert.equal(result.kind,'overlap');assert.equal(result.repeated,1);assert.equal(result.added,1);
});
test('same amount cannot identify an invoice or cross vendor boundaries',()=>{
  const old=doc([row('001')]);assert.equal(assess(doc([row('002')]),[prior(old)]).kind,'new');
  assert.equal(assess(doc([row('001')],{vendor:'Beta'}),[prior(old)]).kind,'new');
  assert.equal(assess(doc([row('001')],{vendor:'Unidentified vendor'}),[prior(doc([row('001')],{vendor:'Unidentified vendor'}))]).kind,'new');
});
test('changed amount date balance or uncertain scan warns instead of silently rejecting',()=>{
  const old=doc([row('001')]);
  for(const input of [doc([row('001',14000)]),doc([row('001')],{statementDate:'2026-10-28'}),doc([row('001',13800,{balance:1000})]),doc([row('001',13800,{confidence:60})]),doc([row('001')],{statementDate:''})])assert.equal(assess(input,[prior(old)]).kind,'similar');
});
test('duplicate checks retain meaningful invoice zeros and allow remembered vendor mappings',()=>{
  const old=doc([row('001')],{vendor:'Alpha Co.'});
  assert.equal(assess(doc([row('1')],{vendor:'Alpha Co.'}),[prior(old)]).kind,'new');
  assert.equal(assess(doc([row('001')]),[prior(old)],{'Alpha':'Alpha Co.'}).kind,'duplicate');
});
test('a partial statement is not mistaken for an identical full statement',()=>{
  assert.equal(assess(doc([row('001')]),[prior(doc([row('001'),row('002')]))]).kind,'similar');
});
test('similar legal names cannot silently reuse a statement from another vendor',()=>{
  const old=doc([row('001')],{vendor:'Alpha Inc'});
  assert.equal(assess(doc([row('001')],{vendor:'Alpha LLC'}),[prior(old)]).kind,'new');
});
test('unreadable omitted rows and extraction warnings cannot qualify for automatic duplicate reuse',()=>{
  const old=doc([row('001')],{declaredTotal:null});
  for(const input of [doc([row('001'),row('',100,{confidence:40})],{declaredTotal:null}),doc([row('001')],{declaredTotal:null,warnings:['An unreadable invoice row was skipped.']})])assert.equal(assess(input,[prior(old)]).kind,'similar');
});
test('duplicate preflight never uploads an identical copy or cancelled similarity',async()=>{
  assert.ok(module,'Statement content duplicate checks must exist');let uploads=0;
  const old=doc([row('001')]),file=new Blob(['synthetic']);
  const options={file,extract:async()=>doc([row('001')]),findCandidates:async()=>[prior(old)],upload:async()=>{uploads++;},choose:async()=> 'cancel'};
  assert.equal((await module.prepareStatementUpload(options)).kind,'duplicate');assert.equal(uploads,0);
  options.extract=async()=>doc([row('001')],{statementDate:'2026-10-28'});
  assert.equal((await module.prepareStatementUpload(options)).kind,'cancelled');assert.equal(uploads,0);
  options.choose=async()=> 'continue';await module.prepareStatementUpload(options);assert.equal(uploads,1);
});
test('OCR failure still uses the original-preserving upload flow; history failure cannot silently bypass the check',async()=>{
  assert.ok(module,'Statement content duplicate checks must exist');let originalKept=false;
  const result=await module.prepareStatementUpload({file:new Blob(['synthetic']),extract:async()=>{throw Error('OCR unavailable');},findCandidates:async()=>{throw Error('Should not be called');},upload:async(file,extract)=>{originalKept=true;await assert.rejects(extract(),/OCR unavailable/);return {doc:{id:'kept'}};}});
  assert.equal(originalKept,true);assert.equal(result.saved.doc.id,'kept');
  await assert.rejects(module.prepareStatementUpload({file:new Blob(['synthetic']),extract:async()=>doc([row('001')]),findCandidates:async()=>{throw Error('History offline');},upload:async()=>assert.fail('Must not bypass lookup')}),/History offline/);
});
test('shared PDF size limit is checked before duplicate extraction starts',async()=>{
  assert.ok(module,'Statement content duplicate checks must exist');let extracted=false;
  await assert.rejects(module.prepareStatementUpload({file:{size:21*1024*1024},extract:async()=>{extracted=true;throw Error('Wrong branch');},upload:async()=>({})}),/20 MiB/);
  assert.equal(extracted,false);
});
