import test from 'node:test';
import assert from 'node:assert/strict';
import {createMailImports} from '../app/ap_statements/frontend/mail-imports.mjs';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
const connection={id:crypto.randomUUID(),generation:1,version:1,paused:false,label:'AP Statements'};
function fixture(extra={}){
 const calls=[],timers=new Map(),changes=[];let timer=0;
 const client={async request(action,payload,options){calls.push([action,payload,options]);
  if(action==='mail_status')return {connection:{...connection},counts:{queued:1}};
  return {items:[{id:'receipt',status:'awaiting_review',statement_id:'new'}],nextCursor:null};}};
 const controller=createMailImports(client,{capability:1,onChange:s=>changes.push(structuredClone(s)),visible:()=>true,
  setTimeoutFn:(fn,ms)=>{timers.set(++timer,{fn,ms});return timer;},clearTimeoutFn:id=>timers.delete(id),...extra});
 return {client,controller,calls,timers,changes};
}
test('no capability means no polling or empty-state flash',async()=>{
 const f=fixture({capability:0});await f.controller.load();assert.equal(f.calls.length,0);assert.equal(f.timers.size,0);f.controller.dispose();
});
test('visible-only thirty-second polling has one flight and backs off',async()=>{
 let visible=true;const f=fixture({visible:()=>visible});await Promise.all([f.controller.load(),f.controller.load()]);
 assert.equal(f.calls.filter(c=>c[0]==='mail_status').length,1);assert.equal([...f.timers.values()][0].ms,30000);
 visible=false;f.controller.visibilityChanged();assert.equal(f.timers.size,0);await f.controller.load();assert.equal(f.calls.length,3);
 f.controller.dispose();assert.equal(f.controller.state.items.length,0);
});
test('late reply after disposal cannot restore private data',async()=>{
 const f=fixture();let release;f.client.request=()=>new Promise(r=>release=r);
 const pending=f.controller.load();await Promise.resolve();f.controller.dispose();release({connection,counts:{}});await pending;
 assert.equal(f.controller.state.connection,null);assert.equal(f.controller.state.items.length,0);assert.equal(f.timers.size,0);
});
test('re-enabling email imports during an old poll starts one fresh authorized poll',async()=>{
 for(const oldDenied of [false,true]){
  const f=fixture();let release,reject;const original=f.client.request;
  f.client.request=(action,payload,options)=>{if(action==='mail_status'&&!release)return new Promise((resolve,fail)=>{release=resolve;reject=fail;});return original(action,payload,options);};
  const old=f.controller.load();await Promise.resolve();f.controller.setCapability(0);f.controller.setCapability(1);
  const resumed=f.controller.load();if(oldDenied)reject(Object.assign(Error('Old request denied'),{code:'denied'}));else release({connection:{...connection,email:'old'},counts:{}});await Promise.all([old,resumed]);
  assert.equal(f.controller.state.loaded,true);assert.notEqual(f.controller.state.connection?.email,'old');assert.equal(f.calls.filter(c=>c[0]==='mail_status').length,1);
  assert.equal(f.timers.size,1);f.controller.dispose();
 }
});
test('new drafts adopt incrementally only when edits are safe',async()=>{
 let dirty=true;const adopted=[];const f=fixture({hasUnsaved:()=>dirty,onImported:ids=>adopted.push(...ids)});
 await f.controller.load();assert.deepEqual(adopted,[]);dirty=false;await f.controller.load();assert.deepEqual(adopted,['new']);
 await f.controller.load();assert.deepEqual(adopted,['new']);f.controller.dispose();
});
test('writes keep one request identity for a lost acknowledgement retry',async()=>{
 const f=fixture();await f.controller.load();let fail=true;
 const original=f.client.request;f.client.request=async(action,payload,options)=>{
  if(action==='mail_pause'){f.calls.push([action,payload,options]);if(fail)throw Object.assign(Error('temporary'),{code:'timeout'});return {saved:true};}
  return original(action,payload,options);
 };
 await assert.rejects(f.controller.pause(true));fail=false;await f.controller.retryLast();
 const writes=f.calls.filter(c=>c[0]==='mail_pause');assert.equal(writes[0][2].requestId,writes[1][2].requestId);f.controller.dispose();
});
test('authorization denial from any email action immediately clears private views',async()=>{
 for(const action of ['mail_pause','mail_preview','mail_list']){
  const f=fixture();await f.controller.load();f.controller.state.evidence={receipt_id:'receipt',rows:[{invoiceNumber:'private'}]};
  const original=f.client.request;f.client.request=async(name,payload,options)=>{if(name===action)throw Object.assign(Error('Locked'),{code:'denied'});return original(name,payload,options);};
  const operation=action==='mail_pause'?()=>f.controller.pause(true):action==='mail_preview'?()=>f.controller.previewOriginal('receipt'):()=>f.controller.more('receipts');
  if(action==='mail_list')f.controller.state.nextCursor={id:'receipt'};
  await assert.rejects(operation());assert.equal(f.controller.state.enabled,false,action);assert.equal(f.controller.state.evidence,null,action);assert.deepEqual(f.controller.state.items,[],action);assert.equal(f.timers.size,0,action);f.controller.dispose();
 }
});
test('loading older imports adopts their drafts and polling retains the expanded list',async()=>{
 const adopted=[],f=fixture({onImported:ids=>adopted.push(...ids)});const original=f.client.request;
 f.client.request=async(action,payload,options)=>{
  if(action==='mail_list')return payload.cursor?{items:[{id:'older',status:'awaiting_review',statement_id:'older-statement'}],nextCursor:null}:
   {items:[{id:'receipt',status:'awaiting_review',statement_id:'new'}],nextCursor:{id:'receipt',discovered_at:'2026-11-04T12:00:00Z'}};
  return original(action,payload,options);
 };
 await f.controller.load();await f.controller.more('receipts');assert.deepEqual(adopted,['new','older-statement']);
 await f.controller.load();assert.equal(f.controller.state.items.length,2);f.controller.dispose();
});
test('fresh server versions replace cached head and already-loaded older receipt rows',async()=>{
 const f=fixture();let version=1;const calls=[],original=f.client.request;
 f.client.request=async(action,payload,options)=>{
  calls.push([action,payload]);
  const row=id=>({id,version,status:version===1?'queued':'awaiting_review',statement_id:version===1?null:id+'-statement'});
  if(action==='mail_list')return payload.cursor?{items:[row('older')],nextCursor:null}:{items:[row('head')],nextCursor:{id:'head',discovered_at:'2026-11-04T12:00:00Z'}};
  if(action==='mail_receipt_updates')return {items:payload.receipt_ids.map(row),nextCursor:null};
  return original(action,payload,options);
 };
 await f.controller.load();await f.controller.more('receipts');version=2;await f.controller.load();
 for(const row of f.controller.state.items){assert.equal(row.version,2);assert.equal(row.status,'awaiting_review');}
 const refresh=calls.find(([action])=>action==='mail_receipt_updates');assert.deepEqual(refresh[1].receipt_ids,['older']);f.controller.dispose();
});
test('incremental workspace adoption retains current dirty document and review decisions',async()=>{
 const existing={id:'existing',confirmed:false,rows:[]};const incoming={id:'new',confirmed:false,rows:[]};const events=[];
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){assert.equal(action,'statement');return {doc:incoming,resolutions:{},completed:false,archived:false};}},
  {onState:(s,change)=>events.push(change)});
 workspace.state.ready=true;workspace.state.details.set('existing',{doc:existing});workspace.state.statements=[existing];workspace.state.resolutions.keep={note:'Typing'};
 await workspace.adoptMailStatements(['new','existing']);
 assert.equal(workspace.state.statements[0],existing);assert.equal(workspace.state.resolutions.keep.note,'Typing');
 assert.equal(workspace.state.statements.length,2);assert.equal(events[0].reason,'mail_imported');workspace.dispose();
});

test('preliminary evidence uses a fresh receipt version and pages one saved comparison',async()=>{
 const f=fixture();let version=2;const original=f.client.request;
 f.client.request=async(action,payload,options)=>{
  if(action==='mail_receipt_updates')return {items:[{id:'receipt',version,status:'awaiting_review'}]};
  if(action==='mail_evidence'){
   assert.equal(payload.expected_version,2);
   if(version!==2)throw Object.assign(Error('Comparison changed'),{code:'conflict'});
   return {receipt_id:'receipt',receipt_version:2,rows:[{invoiceNumber:payload.cursor?'second':'first',status:'amount'}],nextCursor:payload.cursor?null:50,total:2};
  }
  return original(action,payload,options);
 };
 await f.controller.load();await f.controller.openEvidence({id:'receipt',version:1});
 assert.equal(f.controller.state.items[0].version,2);assert.equal(f.controller.state.evidence.rows[0].status,'amount');
 await f.controller.moreEvidence();assert.deepEqual(f.controller.state.evidence.rows.map(r=>r.invoiceNumber),['first','second']);
 f.controller.state.evidence.nextCursor=100;version=3;await f.controller.moreEvidence();
 assert.equal(f.controller.state.evidence.stale,true);assert.equal(f.controller.state.evidence.rows.length,2);f.controller.dispose();
});
test('closing preliminary evidence discards delayed replies, and lock clears saved results',async()=>{
 const f=fixture();const original=f.client.request;let release;
 f.client.request=async(action,payload,options)=>{
  if(action==='mail_receipt_updates')return {items:[{id:'receipt',version:1}]};
  if(action==='mail_evidence')return new Promise(r=>release=r);
  return original(action,payload,options);
 };
 await f.controller.load();const pending=f.controller.openEvidence({id:'receipt'});await Promise.resolve();await Promise.resolve();
 f.controller.closeEvidence();release({receipt_id:'receipt',rows:[{invoiceNumber:'private'}]});await pending;
 assert.equal(f.controller.state.evidence,null);assert.equal(f.controller.state.evidenceBusy,false);
 f.client.request=async(action,payload,options)=>action==='mail_evidence'?{receipt_id:'receipt',receipt_version:1,rows:[{invoiceNumber:'private'}],nextCursor:null}:action==='mail_receipt_updates'?{items:[{id:'receipt',version:1}]}:original(action,payload,options);
 await f.controller.openEvidence({id:'receipt'});assert.equal(f.controller.state.evidence.rows.length,1);
 f.client.request=async()=>{throw Object.assign(Error('Locked'),{code:'denied'});};
 await f.controller.load();assert.equal(f.controller.state.enabled,false);assert.equal(f.controller.state.evidence,null);assert.deepEqual(f.controller.state.items,[]);f.controller.dispose();
});
