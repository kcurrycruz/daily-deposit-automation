import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const list=await import('../app/ap_statements/frontend/statement-list.mjs').catch(()=>null);
const api=()=>{assert.ok(list,'Statement list helpers must exist');return list;};

test('statement date order is newest first, reversible, immutable and undated last',()=>{
  const items=[{id:'old',statementDate:'2026-01-01',completedAt:'2026-10-21'},
    {id:'unknown'},{id:'invalid',statementDate:'2026-02-30'},
    {id:'new',statementDate:'2026-10-01',completedAt:'2026-10-20'}];
  const before=structuredClone(items);
  assert.deepEqual(api().sortStatements(items).map(i=>i.id),['new','old','unknown','invalid']);
  assert.deepEqual(api().sortStatements(items,'asc').map(i=>i.id),['old','new','unknown','invalid']);
  assert.deepEqual(items,before);
});
test('tied statement dates use completion time then id for stable ordering',()=>{
  const items=['a','b','c'].map(id=>({id,statementDate:'2026-10-01',completedAt:id==='a'?'2026-10-20':'2026-10-21'}));
  assert.deepEqual(api().sortStatements(items).map(i=>i.id),['c','b','a']);
  assert.deepEqual(api().sortStatements(items,'asc').map(i=>i.id),['c','b','a']);
});
test('work progress counts clear matches and no-action decisions, but explicit follow-up wins',()=>{
  const rows=[{id:'a',status:'matched'},{id:'b',status:'presence'},{id:'c',status:'ambiguous'}, {id:'d',status:'missing'}];
  const resolutions={a:{decision:'Follow up with vendor'},c:{decision:'Reviewed — no action needed'}};
  assert.deepEqual(api().reviewProgress(rows,resolutions,true),{resolved:2,total:4});
  assert.equal(api().reviewProgress(rows,resolutions,false),null);
  assert.equal(api().reviewProgress([],{},true),null);
  assert.equal(api().reviewProgress([{oops:1}],{},true),null);
  assert.equal(api().reviewProgress([{id:'x',status:'presence',preview:true}],{},true)?.resolved,0);
});
test('saved reviewed and completed statuses are green without claiming payment settlement',()=>{
  for(const [status,label] of [['reviewed','Reviewed'],['reconciled','Completed']]){
    const html=api().reviewStatusHTML(status,{resolved:8,total:10});
    assert.match(html,/badge green/);assert.match(html,new RegExp(label));
    assert.match(html,/8 of 10 items resolved/);assert.doesNotMatch(html,/Paid|settled/);
  }
});
test('follow-up is yellow at exactly half, red below half and unknown progress stays yellow',()=>{
  assert.match(api().reviewStatusHTML('follow_up',{resolved:5,total:10}),/badge amber/);
  assert.match(api().reviewStatusHTML('follow_up',{resolved:4,total:10}),/badge red/);
  for(const progress of [null,{resolved:0,total:0},{resolved:11,total:10},{resolved:'5',total:10}]){
    const html=api().reviewStatusHTML('follow_up',progress);
    assert.match(html,/badge amber/);assert.match(html,/Progress unavailable/);
  }
});
test('date header exposes native keyboard action and accessible direction',()=>{
  assert.match(api().statementDateHeader('desc','history'),/aria-sort="descending"/);
  assert.match(api().statementDateHeader('asc','statements'),/aria-sort="ascending"/);
  assert.match(api().statementDateHeader('desc','history'),/data-action="statement-date-sort" data-list="history"/);
  assert.match(api().statementDateHeader('desc','history'),/<button.*Statement Date/);
});
test('live statement table sorts and shares the date-toggle handler with history',()=>{
  const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
  assert.match(source,/sortStatements\(state\.statements\.filter/);
  assert.match(source,/statementDateHeader\(statementDateSort,'statements'\)/);
  assert.match(source,/if\(action==='statement-date-sort'\)/);
  assert.match(source,/historyDateSort=historyDateSort==='desc'\?'asc':'desc'/);
  assert.match(source,/statementDateSort=statementDateSort==='desc'\?'asc':'desc'/);
});
