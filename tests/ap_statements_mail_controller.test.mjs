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
test('incremental workspace adoption retains current dirty document and review decisions',async()=>{
 const existing={id:'existing',confirmed:false,rows:[]};const incoming={id:'new',confirmed:false,rows:[]};const events=[];
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){assert.equal(action,'statement');return {doc:incoming,resolutions:{},completed:false,archived:false};}},
  {onState:(s,change)=>events.push(change)});
 workspace.state.ready=true;workspace.state.details.set('existing',{doc:existing});workspace.state.statements=[existing];workspace.state.resolutions.keep={note:'Typing'};
 await workspace.adoptMailStatements(['new','existing']);
 assert.equal(workspace.state.statements[0],existing);assert.equal(workspace.state.resolutions.keep.note,'Typing');
 assert.equal(workspace.state.statements.length,2);assert.equal(events[0].reason,'mail_imported');workspace.dispose();
});
