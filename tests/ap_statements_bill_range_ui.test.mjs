import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createBillRangeUI,rangeSelectorHTML,rangeSummaryHTML} from '../app/ap_statements/frontend/bill-range.mjs';
const id=crypto.randomUUID(),workingId=crypto.randomUUID();
const manifest={workingSetId:workingId,workingDigest:'a'.repeat(64),policy:{mode:'last_12_months',asOfDate:'2026-10-30',cutoffDate:'2025-10-30'},fullRecordCount:100,activeCount:12,archivedCount:88,retainedReasonCounts:{recent:10,unsettled:2}};
function fixture({accept=true,dirty=false,handler}={}){
 const calls=[],progress=[],adopted=[];
 let current={importId:id,importVersion:1,workingVersion:0,workingSet:null};
 const shared={state:{capabilities:{billWorkingSets:1},importId:id,importVersion:1,workingVersion:0},async adoptImport(value){adopted.push(value);}};
 const client={async request(action,payload,opts){calls.push({action,payload,opts});if(handler)return handler(action,payload,opts);if(action==='bill_current')return current;if(action==='bill_range_begin')return {job_id:'job',generation:'generation',checkpoint:0,state:'building'};if(action==='bill_range_step')return {job_id:'job',generation:'generation',checkpoint:1,state:'prepared',manifest};if(action==='bill_range_activate')return current={...current,workingVersion:1,workingSet:manifest};if(action==='bill_range_cancel')return {cancelled:true};throw Error(action);}};
 const range=createBillRangeUI({client,shared,hasUnsaved:()=>dirty,onProgress:p=>progress.push(p),confirmApply:async mf=>{assert.deepEqual(mf,manifest);return accept;},delay:async()=>{}});
 return {range,calls,progress,adopted,shared,setCurrent:value=>{current=value;}};
}
test('range selector defaults to last twelve months without changing shared data',()=>{
 const html=rangeSelectorHTML();assert.match(html,/<label[^>]*for="bill-range-mode"/);assert.match(html,/<select[^>]*id="bill-range-mode"/);assert.match(html,/value="last_12_months" selected/);assert.match(html,/All imported dates/);
 assert.match(rangeSelectorHTML('all'),/value="all" selected/);
 const summary=rangeSummaryHTML(manifest);assert.match(summary,/12 active/);assert.match(summary,/88 archived/);assert.match(summary,/2025-10-30/);assert.match(summary,/Unpaid or uncertain/);assert.match(rangeSummaryHTML({...manifest,activeCount:0}),/No bills in this range/);
});
test('saved source range changes publish only after preparation, approval, and activation',async()=>{
 const h=fixture();const result=await h.range.applySaved('last_12_months');
 assert.equal(result.workingSet.workingSetId,workingId);assert.equal(h.adopted.length,1);
 assert.deepEqual(h.calls.map(c=>c.action),['bill_current','bill_range_begin','bill_range_step','bill_range_activate']);
 assert.equal(h.calls[1].payload.mode,'last_12_months');assert.equal(h.progress.find(p=>p.stage==='range_prepared').manifest.activeCount,12);h.range.dispose();
});
test('cancelled summary leaves current source and comparisons untouched',async()=>{
 const h=fixture({accept:false});assert.equal((await h.range.applySaved('all')).cancelled,true);
 assert.equal(h.adopted.length,0);assert.equal(h.progress.at(-1).stage,'cancelled');assert.equal(h.calls.at(-1).action,'bill_range_cancel');assert.equal(h.calls.some(c=>c.action==='bill_range_activate'),false);h.range.dispose();
});
test('unsaved edits and missing migration block range changes',async()=>{
 const h=fixture({dirty:true});await assert.rejects(h.range.applySaved('all'),/Save/);assert.equal(h.calls.length,0);h.range.dispose();
 const old=fixture();old.shared.state.capabilities={};await assert.rejects(old.range.applySaved('all'),/migration/);assert.equal(old.calls.length,0);old.range.dispose();
});
test('same CSV still prepares a new range and hands off its upload job',async()=>{
 const h=fixture();await h.range.prepareUploaded({importId:id,alreadyCurrent:true,job_id:'upload-job'},'all');
 const begin=h.calls.find(c=>c.action==='bill_range_begin');assert.equal(begin.payload.upload_job_id,'upload-job');assert.equal(begin.payload.mode,'all');assert.equal(h.adopted.length,1);h.range.dispose();
});
test('failed activation retries the identical request before any local publication',async()=>{
 let fail=true;const seen=[];
 const h=fixture({handler:async(action,payload,opts)=>{if(action==='bill_current')return {importId:id,importVersion:1,workingVersion:0};if(action==='bill_range_begin')return {job_id:'j',generation:'g',checkpoint:0,state:'prepared',manifest};if(action==='bill_range_activate'){seen.push(opts.requestId);if(fail)throw Error('Connection lost');return {importId:id,importVersion:1,workingVersion:1,workingSet:manifest};}throw Error(action);}});
 let error;try{await h.range.applySaved('all');}catch(e){error=e;}assert.equal(h.adopted.length,0);assert.equal(typeof error.retry,'function');fail=false;await error.retry();assert.equal(seen[0],seen[1]);assert.equal(h.adopted.length,1);h.range.dispose();
});
test('protection refresh keeps acknowledged mode and skips user range-change confirmation',async()=>{
 const h=fixture({accept:false});h.setCurrent({importId:id,importVersion:1,workingVersion:2,workingSet:manifest,protectionsCurrent:false});
 await h.range.refreshProtections();assert.equal(h.calls.find(c=>c.action==='bill_range_begin').payload.refresh,true);assert.equal(h.calls.find(c=>c.action==='bill_range_begin').payload.mode,'last_12_months');assert.equal(h.adopted.length,1);h.range.dispose();
});
test('leaving during range preparation aborts and never publishes a stale callback',async()=>{
 let resolve,started;const held=new Promise(r=>started=r);
 const h=fixture({handler:async action=>action==='bill_current'?{importId:id,importVersion:1,workingVersion:0}:action==='bill_range_begin'?{job_id:'j',generation:'g',checkpoint:0,state:'building'}:action==='bill_range_step'?new Promise(r=>{resolve=r;started();}):{cancelled:true}});
 const pending=h.range.applySaved('all');await held;h.range.dispose();resolve({state:'prepared',manifest});await assert.rejects(pending,/cancelled|left/i);assert.equal(h.adopted.length,0);
});


test('a concurrent source update adopts the acknowledged source without retrying stale activation',async()=>{
 const newer={importId:crypto.randomUUID(),importVersion:2,workingVersion:2,workingSet:manifest};let reads=0;
 const h=fixture({handler:async action=>{if(action==='bill_current')return ++reads===1?{importId:id,importVersion:1,workingVersion:0}:newer;if(action==='bill_range_begin')return {state:'prepared',job_id:'j',generation:'g',checkpoint:0,manifest};if(action==='bill_range_activate')throw Object.assign(Error('Changed source'),{code:'bill_conflict'});if(action==='bill_range_cancel')return {cancelled:true};throw Error(action);}});
 const result=await h.range.applySaved('all');assert.equal(result.superseded,true);assert.equal(h.adopted[0].importId,newer.importId);h.range.dispose();
});

test('the prepared-summary confirmation stays usable while the range update owns the busy guard',()=>{
 const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
 const guard=source.slice(source.indexOf("if(billUpdating&&!"),source.indexOf("if(saveState==='saving'&&!"));
 assert.doesNotThrow(()=>vm.runInNewContext(guard,{billUpdating:true,action:'bill-range-confirm'}));
 assert.throws(()=>vm.runInNewContext(guard,{billUpdating:true,action:'import'}),/Please wait/);
});
