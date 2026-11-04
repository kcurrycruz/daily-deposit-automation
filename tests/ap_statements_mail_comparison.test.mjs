import test from 'node:test';
import assert from 'node:assert/strict';
import * as core from '../app/ap_statements/frontend/core.mjs';
const doc=(changes={})=>({id:'statement-1',vendor:'Adventure in Food',layout:'aif',confirmed:false,
 statementDate:'2026-11-01',pageCount:1,warnings:[],rows:[{id:'row-1',type:'invoice',invoiceNumber:'271712',amount:129981,date:'2026-10-01',page:1,confidence:99}],...changes});
const record=(changes={})=>({id:'import:0',vendor:'Adventure in Food Trading Company',invoiceNumber:'271712X',amount:129981,
 kind:'invoice',comparisonScope:'invoice-only',status:'PaidInFull',...changes});
const provider=records=>({loaded:true,simulated:false,records});
const map={'Adventure in Food':'Adventure in Food Trading Company'};

test('preliminary matching never confirms a document or changes human review state',()=>{
 assert.equal(typeof core.preliminaryReconcile,'function');
 const statement=doc(),before=structuredClone(statement),reviews={};
 assert.equal(core.reconcile(statement,provider([record()]),map)[0].status,'extraction');
 const preview=core.preliminaryReconcile(statement,provider([record()]),map);
 assert.equal(preview[0].status,'presence');assert.equal(preview[0].referenceRule,'adventure-trailing-letter-v1');
 assert.deepEqual(statement,before);assert.deepEqual(reviews,{});
 assert.equal(core.reconcile(statement,provider([record()]),map)[0].status,'extraction');
});

test('preliminary results preserve reference, amount, currency, credit, confidence and ambiguity rules',()=>{
 assert.equal(typeof core.preliminaryReconcile,'function');
 const cases=[
  {statement:doc(),records:[record()],want:'presence'},
  {statement:doc(),records:[record({amount:129980})],want:'amount'},
  {statement:doc(),records:[record({currency:'EUR'})],want:'amount'},
  {statement:doc(),records:[record({sourceIssues:'Source rows conflict',sourceRows:'2,3'})],want:'source'},
  {statement:doc(),records:[record(),record({id:'import:1'})],want:'ambiguous'},
  {statement:doc({rows:[{...doc().rows[0],confidence:79}]}),records:[record()],want:'extraction'},
  {statement:doc({vendor:'Unknown company'}),records:[record({invoiceNumber:'271712'})],want:'vendor'},
  {statement:doc({rows:[{...doc().rows[0],invoiceNumber:'C100',type:'credit',amount:-500}]}),
   records:[record({invoiceNumber:'C100',kind:'credit',amount:-500})],want:'credit'},
 ];
 for(const {statement,records,want} of cases){
  const preview=core.preliminaryReconcile(statement,provider(records),map);
  assert.equal(preview[0].status,want);
  assert.deepEqual(preview,core.reconcile({...statement,confirmed:true},provider(records),map));
 }
});

test('unloaded or incomplete source and excluded range cannot become preliminary Missing',()=>{
 assert.equal(typeof core.preliminaryReconcile,'function');
 const statement=doc();
 assert.equal(core.preliminaryReconcile(statement,{loaded:false,records:[]},map)[0].status,'unverified');
 const workingSet={workingSetId:'working-1',policy:{mode:'last_12_months',cutoffDate:'2026-10-01'}};
 const scope={inputKey:core.comparisonInputKey(statement,map),complete:false,directoryComplete:false,records:[],workingSet};
 const source={loaded:true,records:[],workingSet,scopes:{[statement.id]:scope}};
 assert.equal(core.preliminaryReconcile(statement,source,map)[0].status,'unverified');
 Object.assign(scope,{complete:true,directoryComplete:true,vendorDirectory:[{vendor:'Adventure in Food Trading Company'}]});
 assert.equal(core.preliminaryReconcile(statement,source,map)[0].status,'range');
});
