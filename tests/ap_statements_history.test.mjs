import test from 'node:test';
import assert from 'node:assert/strict';
import {completionPayload,historyFilters,historyView,nyTimestamp} from '../app/ap_statements/frontend/history.mjs';
const fixture=()=>({doc:{id:crypto.randomUUID(),confirmed:true,rows:[{id:'r',type:'invoice',invoiceNumber:'001',amount:100,page:1,confidence:99}]},results:[{id:'r',status:'possible'}],resolutions:{r:{decision:'Reviewed — no action needed'}},initials:'kc',notes:'',expectedVersion:2});
test('completion allows blank notes but requires reviewer initials and review decisions',()=>{
  const input=fixture();assert.equal(completionPayload(input).initials,'KC');assert.equal(completionPayload(input).notes,'');
  for(const initials of ['','12','x<script>'])assert.throws(()=>completionPayload({...input,initials}),/initials/i);
  assert.throws(()=>completionPayload({...input,doc:{...input.doc,confirmed:false}}),/extraction/i);
  assert.throws(()=>completionPayload({...input,resolutions:{}}),/decision/i);
});
test('New York dates use DST-aware boundaries rather than the browser timezone',()=>{
  const spring=historyFilters({completedFrom:'2026-03-08',completedTo:'2026-03-08'});assert.equal(spring.completedFrom,'2026-03-08T05:00:00.000Z');assert.equal(spring.completedTo,'2026-03-09T03:59:59.999Z');
  const fall=historyFilters({completedFrom:'2026-11-01',completedTo:'2026-11-01'});assert.equal(fall.completedFrom,'2026-11-01T04:00:00.000Z');assert.equal(fall.completedTo,'2026-11-02T04:59:59.999Z');
  assert.match(nyTimestamp('2026-10-01T02:00:00Z'),/Sep 30/);assert.throws(()=>historyFilters({completedFrom:'2026-02-30'}),/date/i);
});
test('history presentation escapes notes filenames and initials and differentiates follow-up',()=>{
  const html=historyView({items:[{id:'i',statementId:'s',revisionId:'r',vendor:'<script>',filename:'<b>file</b>',initials:'<KC>',notes:'<img src=x>',completedAt:'2026-10-01T12:00:00Z',status:'follow_up',statementDate:'2026-09-30'}],nextCursor:null});
  assert.doesNotMatch(html,/<script>|<img src=x>/);assert.match(html,/&lt;script&gt;/);assert.match(html,/Follow-up/);assert.match(html,/Reviewer initials/);
});
