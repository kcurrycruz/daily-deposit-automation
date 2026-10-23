import test from 'node:test';
import assert from 'node:assert/strict';
import {createDuplicateBills} from '../app/ap_statements/frontend/duplicate-bills.mjs';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
import {duplicateViewHTML} from '../app/ap_statements/frontend/duplicate-bills-ui.mjs';
const source={importId:crypto.randomUUID(),importVersion:1,capability:1};
const key='a'.repeat(64),scanId=crypto.randomUUID(),generation=crypto.randomUUID();
const progress=(changes={})=>({scanId,importId:source.importId,importVersion:1,generation,checkpoint:0,state:'running',phase:'reading',projectionReady:false,counts:null,canStep:true,...changes});
function setup(handler,options={}){
 const calls=[],timers=new Map(),delays=[];let n=0,disposed=0;
 const client={dispose(){disposed++;},async request(action,payload,options){calls.push({action,payload,options});return handler?handler(action,payload,options):action==='duplicate_ensure'?progress():action==='duplicate_step'?progress({state:'ready',checkpoint:1}):action==='duplicate_status'?progress({state:'ready',projectionReady:true,counts:{all:1,reviewed:0,unreviewed:1},reviewRevision:0}):action==='duplicate_findings_page'?{scanId,importId:source.importId,reviewRevision:0,total:1,counts:{all:1,reviewed:0,unreviewed:1},findings:[{key,review:null}],nextCursor:null}:{scanId,importId:source.importId,reviewRevision:0,members:[],finding:{key,review:null},nextCursor:null};}};
 const controller=createDuplicateBills(client,{schedule:(fn,ms)=>{delays.push(ms);timers.set(++n,fn);return n;},cancelSchedule:id=>timers.delete(id),...options});
 async function flush(){const first=timers.entries().next().value;if(first){timers.delete(first[0]);await first[1]();}}
 return {controller,calls,timers,delays,flush,client,get disposed(){return disposed;}};
}
async function finish(h){for(let i=0;i<12&&!h.controller.state.page;i++)await h.flush();}

test('scan observations retain elapsed time until real advancement and reset on generation or source change',async()=>{
 let time=100000,checkpoint=0;const h=setup(()=>progress({checkpoint,canStep:false,updatedAt:'2026-10-23T12:00:00Z',serverNow:'2026-10-23T12:01:00Z'}),{now:()=>time});
 h.controller.adoptSource(source);await h.flush();assert.equal(h.controller.state.observedAt,100000);assert.equal(h.controller.state.lastAdvanceAt,40000);
 time=110000;await h.flush();assert.equal(h.controller.state.observedAt,110000);assert.equal(h.controller.state.lastAdvanceAt,40000);
 checkpoint=1;time=120000;await h.flush();assert.equal(h.controller.state.lastAdvanceAt,120000);
 h.controller.adoptSource({...source,importVersion:2});assert.equal(h.controller.state.lastAdvanceAt,null);h.controller.dispose();
});

test('a stalled scan leaves an idle interval for manual refresh without automatically restarting',async()=>{
 const h=setup(()=>progress({updatedAt:'2026-10-23T12:00:00Z',serverNow:'2026-10-23T12:02:00Z'}),{now:()=>200000});
 h.controller.adoptSource(source);await h.flush();
 assert.equal(h.delays.at(-1),1000);await h.flush();
 assert.equal(h.calls.at(-1).payload.restart,false);h.controller.dispose();
});

test('a restored superseded source can explicitly restart instead of polling forever',async()=>{
 const h=setup(action=>progress({state:action==='duplicate_ensure'?'superseded':'running'}));
 h.controller.adoptSource(source);await h.flush();await h.controller.retry();
 assert.equal(h.calls.at(-1).action,'duplicate_step');assert.equal(h.calls.at(-1).payload.restart,true);h.controller.dispose();
});

test('rapid restart clicks join one recovery request at the current generation and checkpoint',async()=>{
 let release,started;const held=new Promise(r=>started=r);
 const h=setup(action=>action==='duplicate_ensure'?progress({state:'restart_required',checkpoint:8}):new Promise(r=>{release=r;started();}));
 h.controller.adoptSource(source);await h.flush();
 const first=h.controller.retry(),second=h.controller.retry();
 assert.strictEqual(first,second);await held;
 assert.equal(h.calls.filter(c=>c.action==='duplicate_step').length,1);
 assert.deepEqual(h.calls.at(-1).payload,{scan_id:scanId,generation,expected_checkpoint:8,restart:true});
 release(progress({generation:'new-generation',checkpoint:0}));await first;h.controller.dispose();
});

test('initial ensure conflict recovers with a fresh ensure rather than a null scan status',async()=>{
 let attempt=0;const h=setup(()=>{if(++attempt===1)throw Object.assign(Error('Conflict'),{code:'duplicate_conflict'});return progress();});
 h.controller.adoptSource(source);await h.flush();assert.equal(h.controller.state.progress,null);
 await h.controller.retry();
 assert.deepEqual(h.calls.map(c=>c.action),['duplicate_ensure','duplicate_ensure']);
 assert.notEqual(h.calls[0].options.requestId,h.calls[1].options.requestId);
 assert.equal(h.controller.state.error,null);h.controller.dispose();
});

test('recovery from a live foreign-owned scan reads status without restarting',async()=>{
 const h=setup(()=>progress({canStep:false}));h.controller.adoptSource(source);await h.flush();await h.controller.retry();
 assert.equal(h.calls.at(-1).action,'duplicate_status');assert.equal(h.calls.filter(c=>c.action==='duplicate_step').length,0);h.controller.dispose();
});

test('recovery replies from a former source generation cannot restore A-to-B-to-A evidence',async()=>{
 let release,started;const held=new Promise(r=>started=r);
 const h=setup(action=>action==='duplicate_ensure'?progress({state:'restart_required'}):new Promise(r=>{release=r;started();}));
 h.controller.adoptSource(source);await h.flush();const recovery=h.controller.retry();await held;
 h.controller.adoptSource({...source,importId:'source-b',importVersion:2});h.controller.adoptSource({...source,importVersion:3});
 release(progress({state:'ready',projectionReady:true}));await recovery;
 assert.equal(h.controller.state.progress,null);assert.equal(h.controller.state.source.importVersion,3);h.controller.dispose();
});

test('denied recovery clears evidence and cannot retain a retry handle',async()=>{
 const h=setup(action=>{if(action==='duplicate_ensure')return progress();throw Object.assign(Error('locked'),{code:'denied'});});
 h.controller.adoptSource(source);await h.flush();await assert.rejects(h.controller.retry(),/locked/);
 assert.equal(h.controller.state.source,null);assert.equal(h.controller.state.progress,null);
 const n=h.calls.length;await h.controller.retry();assert.equal(h.calls.length,n);
});

test('no capability or no source never starts a scan',async()=>{
 const h=setup();h.controller.adoptSource({...source,capability:0});await h.flush();assert.equal(h.calls.length,0);
 h.controller.adoptSource({...source,importId:null});await h.flush();assert.equal(h.calls.length,0);assert.equal(h.controller.state.phase,'no_source');h.controller.dispose();
});
test('existing source starts automatically, yields, then prepares reviews before listing',async()=>{
 const h=setup();h.controller.adoptSource(source);assert.equal(h.calls.length,0);await finish(h);
 assert.deepEqual(h.calls.map(c=>c.action),['duplicate_ensure','duplicate_step','duplicate_status','duplicate_findings_page']);
 assert.equal(h.controller.state.page.total,1);h.controller.adoptSource(source);await h.flush();assert.equal(h.calls.length,4);h.controller.dispose();
});
test('busy work pauses new steps and only one bounded step can remain outstanding',async()=>{
 let release;const h=setup(async action=>{if(action==='duplicate_ensure')return progress();return new Promise(r=>release=r);});
 h.controller.adoptSource(source);await h.flush();const pending=h.flush();await Promise.resolve();
 h.controller.setBusy(true);await h.flush();assert.equal(h.calls.length,2);release(progress({checkpoint:1}));await pending;
 await h.flush();assert.equal(h.calls.length,2);h.controller.setBusy(false);assert.equal(h.timers.size,1);h.controller.dispose();
});
test('source versions discard late A-to-B-to-A evidence and weekly adoption starts anew',async()=>{
 let release,started;const ready=new Promise(r=>started=r);const h=setup(()=>new Promise(r=>{release=r;started();}));h.controller.adoptSource(source);const pending=h.flush();await ready;
 h.controller.adoptSource({...source,importId:crypto.randomUUID(),importVersion:2});h.controller.adoptSource({...source,importVersion:3});
 release(progress({state:'ready',projectionReady:true}));await pending;assert.equal(h.controller.state.progress,null);
 assert.equal(h.controller.state.source.importVersion,3);assert.equal(h.controller.state.page,null);h.controller.dispose();
});
test('detector failure is local and retry keeps its mutation request identity',async()=>{
 let fail=true;const h=setup(()=>{if(fail)throw Object.assign(Error('scan unavailable'),{code:'duplicate_unavailable'});return progress();});
 h.controller.adoptSource(source);await h.flush();assert.equal(h.controller.state.error.message,'scan unavailable');
 const id=h.calls[0].options.requestId;fail=false;await h.controller.retry();assert.equal(h.calls[1].options.requestId,id);h.controller.dispose();
});

test('packaging errors pause activity and an explicit retry resumes the same checkpoint',async()=>{
 let fail=true,release,started;const held=new Promise(r=>started=r);
 const h=setup(action=>{
  if(action==='duplicate_ensure')return progress({phase:'packaging',recordsRead:223425,totalRecords:223425});
  if(fail)throw Object.assign(Error('Storage unavailable'),{code:'unavailable'});
  return new Promise(resolve=>{release=()=>resolve(progress({state:'ready',phase:'complete',recordsRead:223425,totalRecords:223425}));started();});
 });
 h.controller.adoptSource(source);await h.flush();await h.flush();
 assert.equal(h.timers.size,0);
 assert.match(duplicateViewHTML(h.controller.state),/paused/i);
 assert.doesNotMatch(duplicateViewHTML(h.controller.state),/aria-busy="true"/);
 const failed=h.calls.at(-1);fail=false;
 const retry=h.controller.retry();await held;
 assert.match(duplicateViewHTML(h.controller.state),/aria-busy="true"/);
 release();await retry;
 assert.equal(h.calls.at(-1).options.requestId,failed.options.requestId);
 assert.deepEqual(h.calls.at(-1).payload,failed.payload);
 assert.equal(h.controller.state.error,null);h.controller.dispose();
});
test('review save waits for acknowledgement and keeps a failed retry draft outside statement state',async()=>{
 let fail=true;const h=setup((action,payload)=>{
  if(action==='duplicate_ensure')return progress({state:'ready',projectionReady:true,reviewRevision:0,counts:{all:1,reviewed:0,unreviewed:1}});
  if(action==='duplicate_findings_page')return {scanId,reviewRevision:0,findings:[{key,review:null}],total:1,nextCursor:null};
  if(action==='duplicate_members_page')return {scanId,reviewRevision:0,finding:{key,review:null},members:[],nextCursor:null};
  if(action==='duplicate_review_save'){if(fail)throw Error('offline');return {review:{key,version:1,decision:payload.decision,initials:'KC',note:payload.note,at:'2026-10-22T12:00:00Z'},reviewRevision:1};}
  return progress({state:'ready',projectionReady:false,reviewRevision:1});
 });
 h.controller.adoptSource(source);await finish(h);await h.controller.open(key);
 await assert.rejects(h.controller.save({decision:'not_duplicate',initials:'KC',note:'Keep this note',expectedVersion:0}),/offline/);
 assert.equal(h.controller.state.detail.finding.review,null);assert.equal(h.controller.state.saveState,'not_saved');
 const request=h.calls.at(-1).options.requestId;fail=false;const ack=await h.controller.retry();
 assert.equal(ack.review.version,1);assert.equal(h.calls.at(-1).options.requestId,request);assert.equal(h.controller.state.saveState,'saved');h.controller.dispose();
});
test('dispose clears sensitive evidence and timers without disposing shared client',async()=>{
 const h=setup();h.controller.adoptSource(source);await finish(h);h.controller.dispose();
 assert.equal(h.controller.state.page,null);assert.equal(h.controller.state.detail,null);assert.equal(h.timers.size,0);assert.equal(h.disposed,0);
});
test('opening another finding never displays the previous finding save acknowledgement',async()=>{
 const h=setup();h.controller.adoptSource(source);await finish(h);h.controller.state.saveState='saved';
 await h.controller.open('b'.repeat(64));assert.equal(h.controller.state.saveState,'idle');h.controller.dispose();
});
test('an expired access reply clears financial evidence rather than retaining a stale list',async()=>{
 let denied=false;const h=setup(action=>{if(denied)throw Object.assign(Error('locked'),{code:'denied'});
  if(action==='duplicate_ensure')return progress({state:'ready',projectionReady:true,reviewRevision:0});
  return {scanId,reviewRevision:0,total:1,findings:[{key}],nextCursor:null};});
 h.controller.adoptSource(source);await finish(h);denied=true;
 await assert.rejects(h.controller.open(key),/locked/);assert.equal(h.controller.state.page,null);assert.equal(h.controller.state.source,null);assert.equal(h.timers.size,0);
});
test('a concurrent review conflict refreshes evidence instead of resending a stale save forever',async()=>{
 let reviewed=false;const h=setup((action)=>{
  if(action==='duplicate_ensure'||action==='duplicate_status')return progress({state:'ready',projectionReady:true,reviewRevision:reviewed?1:0});
  if(action==='duplicate_findings_page')return {scanId,reviewRevision:reviewed?1:0,total:1,findings:[{key}],nextCursor:null};
  if(action==='duplicate_members_page')return {scanId,reviewRevision:reviewed?1:0,finding:{key,review:reviewed?{version:1,note:'Colleague'}:null},members:[],nextCursor:null};
  reviewed=true;throw Object.assign(Error('Shared review changed'),{code:'duplicate_conflict'});
 });
 h.controller.adoptSource(source);await finish(h);await h.controller.open(key);
 await assert.rejects(h.controller.save({decision:'not_duplicate',initials:'KC',note:'My draft',expectedVersion:0}));
 await h.controller.retry();for(let i=0;i<8;i++)await h.flush();
 assert.equal(h.controller.state.detail.finding.review.version,1);assert.equal(h.calls.filter(c=>c.action==='duplicate_review_save').length,1);h.controller.dispose();
});
test('shared workspace is ready while the duplicate service is still pending',async()=>{
 const calls=[],statuses=[];let release;
 const client={dispose(){},async request(action){calls.push(action);
  if(action==='bootstrap')return {activeImport:{id:source.importId,metadata:{label:'synthetic.csv'},record_count:1},importVersion:1,capabilities:{duplicateBills:1},mappings:{},statements:[],nextCursor:null};
  if(action==='records_page')return {importId:source.importId,recordCount:1,records:[{id:source.importId+':0',vendor:'Synthetic',invoiceNumber:'1',amount:100}],nextCursor:null};
  if(action==='duplicate_ensure')return new Promise(r=>release=r);
  throw Error(action);
 }};
 const workspace=createSharedWorkspace(client,{onSaveState:s=>statuses.push(s)});await workspace.load();
 assert.equal(workspace.state.ready,true);assert.equal(workspace.state.provider.records.length,1);
 await new Promise(r=>setTimeout(r,25));assert.ok(calls.includes('duplicate_ensure'));
 release(progress({state:'failed',error:'duplicate_limit'}));await new Promise(r=>setTimeout(r,5));
 assert.equal(workspace.state.ready,true);assert.ok(!statuses.includes('not_saved'));workspace.dispose();
});

test('denied background scan locks the entire shared workspace instead of retaining statements',async()=>{
 let disposed=0;const snapshots=[];
 const workspace=createSharedWorkspace({dispose(){disposed++;},async request(action){
  if(action==='bootstrap')return {activeImport:{id:source.importId,metadata:{sourceFormat:'bill-native'}},importVersion:1,capabilities:{duplicateBills:1},mappings:{},statements:[],nextCursor:null};
  if(action==='records_page')return {importId:source.importId,recordCount:1,records:[{id:source.importId+':0',vendor:'Synthetic',invoiceNumber:'1',amount:100}],nextCursor:null};
  throw Object.assign(Error('Access denied'),{code:'denied'});
 }},{onState:s=>snapshots.push({ready:s.ready,denied:s.accessDenied})});
 await workspace.load();assert.equal(workspace.state.ready,true);
 await workspace.duplicates.retry();
 assert.equal(workspace.state.accessDenied,true);assert.equal(workspace.state.ready,false);
 assert.equal(workspace.state.provider.records.length,0);assert.equal(workspace.state.details.size,0);
 assert.equal(disposed,1);assert.ok(snapshots.some(s=>s.denied&&!s.ready));
});
