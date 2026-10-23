import test from 'node:test';
import assert from 'node:assert/strict';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
import {invoiceResult} from '../app/ap_statements/frontend/reference-review.mjs';
const manual=await import('../app/ap_statements/frontend/manual-review.mjs').catch(()=>null);
const clone=value=>structuredClone(value);
function fixture(){
 const id=crypto.randomUUID(),row=crypto.randomUUID(),old=crypto.randomUUID(),current=crypto.randomUUID();
 const doc={id,vendor:'Alpha',filename:'statement.pdf',statementDate:'2026-10-01',confirmed:true,pageCount:1,notes:'Keep statement notes',warnings:[],rows:[{id:row,invoiceNumber:'00042',type:'invoice',amount:13800,balance:13800,page:1,confidence:99}]};
 const result={id:row,invoiceNumber:'00042',kind:'invoice',originalAmount:13800,outstanding:13800,vendor:'Alpha',statementId:id,status:'missing',reason:'Not in old export',candidates:[]};
 return {id,row,old,current,doc,result,detail:{doc,resolutions:{[row]:{decision:'Follow up with vendor',note:'Keep invoice note',at:'2026-10-01T12:00:00Z'}},version:1,revisionVersion:1,revisionId:crypto.randomUUID(),importId:old,importLabel:'Old.csv',mappingSnapshot:{Alpha:'Old Alpha'},ruleVersion:'ap-match-v3',results:[result],originalAvailable:true,completed:true,archived:false}};
}
async function harness({draft=false,capability=true,source=true}={}){
 const f=fixture(),calls=[],cache=new Map(),revisions=new Map(),vendors=[{vendor:'Alpha'}];
 const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(vendors))))].map(v=>v.toString(16).padStart(2,'0')).join('');
 const h={...f,calls,failCandidates:false,loseReopen:false,failRead:false,current:f.current,version:1};
 let head=clone(f.detail);if(draft){head.completed=false;head.doc.reviewMode='manual';}
 const client={dispose(){},async request(action,payload={},options={}){
  calls.push({action,payload:clone(payload),requestId:options.requestId});
  if(action==='bootstrap')return {activeImport:source?{id:h.current,metadata:{label:'Latest.csv',sourceFormat:'bill-native'},record_count:1,storage_format:'snapshot-v2',vendorDigest:digest}:null,importVersion:h.version,capabilities:{billSnapshots:2,...(capability?{statementRereview:1}:{})},mappings:{Alpha:'Alpha'},mappingVersions:{},statements:draft?[{id:f.id}]:[],nextCursor:null};
  if(action==='bill_current')return {importId:h.current,importVersion:h.version,recordCount:1,storageFormat:'snapshot-v2',metadata:{label:'Latest.csv',sourceFormat:'bill-native'}};
  if(action==='bill_vendors_page')return {importId:payload.import_id,vendors,total:1,vendorDigest:digest,nextCursor:null};
  if(action==='bill_candidates_page'){
   if(h.beforeCandidates)await h.beforeCandidates();
   if(h.failCandidates)throw Error('Candidate lookup offline');
   return {importId:payload.query.importId,queryDigest:'a'.repeat(64),total:1,records:[{id:payload.query.importId+':0',vendor:'Alpha',invoiceNumber:'00042',amount:13800,currency:'USD',kind:'invoice'}],nextCursor:null,afterOrdinal:-1};
  }
  if(action==='statement'){
   if(h.failRead)throw Error('Readback offline');
   const detail=clone(payload.revision_id?revisions.get(payload.revision_id)||head:head);
   detail.version=head.version;return detail;
  }
  if(action==='save_mapping')return {version:1};
  if(cache.has(options.requestId))return clone(cache.get(options.requestId));
  if(action==='reopen_statement'){
   assert.equal(payload.expected_version,head.version);assert.equal(head.completed,true);
   head={...head,doc:{...head.doc,reviewMode:payload.review_mode},completed:false,version:head.version+1,revisionVersion:head.version+1,revisionId:crypto.randomUUID()};
   if(payload.review_mode==='latest')head.resolutions=Object.fromEntries(Object.entries(head.resolutions).map(([id,r])=>[id,{note:r.note}]));
   revisions.set(head.revisionId,clone(head));
   const reply={statement_id:f.id,version:head.version,revision_id:head.revisionId};cache.set(options.requestId,reply);
   if(h.loseReopen){h.loseReopen=false;throw Error('Lost reopen acknowledgement');}return clone(reply);
  }
  if(action==='save_revision'){
   assert.equal(payload.expected_version,head.version);
   head={...head,doc:clone(payload.doc),resolutions:clone(payload.resolutions),results:clone(payload.results),importId:payload.import_id,mappingSnapshot:clone(payload.mapping_snapshot),ruleVersion:payload.rule_version,version:head.version+1,revisionVersion:head.version+1,revisionId:crypto.randomUUID()};
   for(const r of Object.values(head.resolutions))if(r.decision)r.at='2026-10-23T15:00:00Z';
   revisions.set(head.revisionId,clone(head));
   const reply={statement_id:f.id,version:head.version,revision_id:head.revisionId};cache.set(options.requestId,reply);return clone(reply);
  }
  if(action==='complete_revision'){head.completed=true;head.version++;return {statement_id:f.id,version:head.version};}
  throw Error('Unexpected action '+action);
 }};
 h.workspace=createSharedWorkspace(client);h.head=()=>head;await h.workspace.load();return h;
}

test('an explicit acknowledged manual check labels the review method without claiming an imported match',()=>{
 assert.ok(manual,'Manual check helpers must exist');const f=fixture(),before=clone(f.result);
 const resolution=manual.createManualCheck(f.doc,f.result,{initials:' kc ',decision:'Reviewed — no action needed',note:'Checked in BILL'});
 assert.equal(resolution.manualCheck.initials,'KC');assert.equal(manual.manualCheckFor(f.result,resolution),null);
 resolution.at='2026-10-23T15:00:00Z';assert.equal(manual.manualCheckFor(f.result,resolution).initials,'KC');
 const result=invoiceResult(f.result,resolution);assert.equal(result.checkedManually,true);assert.equal(result.found,false);assert.equal(result.label,'Checked manually in BILL');assert.deepEqual(f.result,before);
 for(const changes of [{invoiceNumber:'42'},{originalAmount:13801},{vendor:'Beta'},{kind:'credit'}])assert.equal(manual.manualCheckFor({...f.result,...changes},resolution),null);
 for(const initials of ['','123','A'.repeat(11)])assert.throws(()=>manual.createManualCheck(f.doc,f.result,{initials,decision:'Reviewed — no action needed'}),/initials/i);
 assert.throws(()=>manual.createManualCheck(f.doc,f.result,{initials:'KC',decision:''}),/decision/i);
});

test('mode-aware reopen uses exact readback and keeps its mutation identity after lost acknowledgement',async()=>{
 const h=await harness();h.loseReopen=true;let error;
 try{await h.workspace.reopenStatement(h.id,1,{mode:'manual'});}catch(e){error=e;}
 assert.ok(error);const saved=await error.retry();
 assert.equal(saved.doc.reviewMode,'manual');assert.equal(saved.resolutions[h.row].note,'Keep invoice note');
 const calls=h.calls.filter(c=>c.action==='reopen_statement');assert.equal(calls[0].requestId,calls[1].requestId);
 assert.equal(calls[0].payload.review_mode,'manual');
 assert.equal(h.calls.at(-1).payload.revision_id,saved.revisionId);h.workspace.dispose();
});

test('an existing editable draft is reused without overwriting local notes or review decisions',async()=>{
 const h=await harness({draft:true}),doc=h.workspace.state.statements[0];doc.notes='Unsaved local note';
 const existing=h.workspace.state.details.get(h.id),before=h.calls.length;
 const opened=await h.workspace.reopenStatement(h.id,1,{mode:'latest'});
 assert.equal(opened,existing);assert.equal(doc.notes,'Unsaved local note');assert.equal(h.calls.length,before);h.workspace.dispose();
});

test('manual drafts keep all pinned evidence through startup, prepare, weekly updates, save and completion',async()=>{
 const h=await harness({draft:true}),w=h.workspace,doc=w.state.statements[0];
 assert.equal(w.state.resolutions[h.row].decision,'Follow up with vendor');
 const calls=h.calls.length;await w.prepareStatement(doc);await w.ensureComparisons(doc);assert.equal(h.calls.length,calls);
 h.current=crypto.randomUUID();h.version++;await w.adoptImport({});await Promise.resolve();
 assert.equal(w.state.details.get(h.id).importId,h.old);assert.equal(w.state.resolutions[h.row].decision,'Follow up with vendor');
 await w.saveMapping({vendor:'Alpha',bill_vendor:'New Alpha'},0);
 assert.equal(w.state.resolutions[h.row].decision,'Follow up with vendor');
 doc.notes='Manual note';await w.saveStatement(doc,1);
 const payload=h.calls.find(c=>c.action==='save_revision').payload;
 assert.equal(payload.import_id,h.old);assert.equal(payload.rule_version,'ap-match-v3');assert.deepEqual(payload.mapping_snapshot,{Alpha:'Old Alpha'});assert.deepEqual(payload.results,[h.result]);
 await w.completeStatement({statement_id:h.id,expected_version:2,initials:'KC',notes:''});
 assert.equal(w.state.details.get(h.id).completed,true);assert.deepEqual(w.state.details.get(h.id).results,[h.result]);w.dispose();
});

test('a manual draft still loads with no current BILL source and retains its saved decisions',async()=>{
 const h=await harness({draft:true,source:false});assert.equal(h.workspace.state.ready,true);
 assert.equal(h.workspace.state.resolutions[h.row].decision,'Follow up with vendor');
 assert.equal(h.calls.filter(c=>c.action==='bill_candidates_page').length,0);h.workspace.dispose();
});

test('latest-data re-review retains notes but replaces prior decisions with fresh comparisons',async()=>{
 const h=await harness(),w=h.workspace;const opened=await w.reopenStatement(h.id,1,{mode:'latest'});
 assert.deepEqual(w.state.resolutions[h.row],{note:'Keep invoice note'});
 await w.prepareStatement(opened.doc);await w.saveStatement(opened.doc,opened.version);
 const saved=h.calls.find(c=>c.action==='save_revision').payload;
 assert.equal(saved.import_id,h.current);assert.notEqual(saved.results[0].status,'missing');assert.equal(saved.rule_version,'ap-match-v4');w.dispose();
});

test('failed explicit latest recheck restores the manual draft source, results and decisions',async()=>{
 const h=await harness({draft:true}),w=h.workspace;h.failCandidates=true;
 const before=clone(w.state.details.get(h.id));
 await assert.rejects(w.refreshComparisons(h.id),/offline/);
 assert.equal(w.state.statements[0].reviewMode,'manual');assert.equal(w.state.details.get(h.id).importId,h.old);
 assert.deepEqual(w.state.details.get(h.id).results,before.results);
 assert.deepEqual(w.state.resolutions[h.row],before.resolutions[h.row]);w.dispose();
});

test('explicit latest recheck succeeds without changing historical evidence and clears old decisions only',async()=>{
 const h=await harness({draft:true}),w=h.workspace;await w.refreshComparisons(h.id);
 assert.equal(w.state.statements[0].reviewMode,'latest');assert.deepEqual(w.state.resolutions[h.row],{note:'Keep invoice note'});
 assert.equal(h.detail.doc.reviewMode,undefined);assert.equal(h.detail.results[0].status,'missing');w.dispose();
});

test('unsupported schema blocks mode-aware mutations and disposing clears manual financial evidence',async()=>{
 const h=await harness({capability:false});await assert.rejects(h.workspace.reopenStatement(h.id,1,{mode:'manual'}),/setup|unavailable/i);
 assert.equal(h.calls.some(c=>c.action==='reopen_statement'),false);h.workspace.dispose();
 assert.equal(h.workspace.state.details.size,0);assert.deepEqual(h.workspace.state.resolutions,{});
});

test('a newer server head after lost reopen readback cannot replace the current local state',async()=>{
 const h=await harness();h.failRead=true;let failure;
 try{await h.workspace.reopenStatement(h.id,1,{mode:'manual'});}catch(error){failure=error;}
 h.failRead=false;h.head().version++;
 await assert.rejects(failure.retry(),/changed|reload/i);
 assert.equal(h.workspace.state.statements.length,0);
 assert.equal(h.calls.filter(c=>c.action==='reopen_statement').length,1);h.workspace.dispose();
});

test('a draft opened during reopen readback failure keeps its newer local notes on retry',async()=>{
 const h=await harness();h.failRead=true;let failure;
 try{await h.workspace.reopenStatement(h.id,1,{mode:'manual'});}catch(error){failure=error;}
 const local=clone(h.head());local.doc.notes='Local changes after lost readback';h.workspace.adopt(local);
 h.failRead=false;await assert.rejects(failure.retry(),/draft.*open|local edits/i);
 assert.equal(h.workspace.state.statements[0].notes,'Local changes after lost readback');h.workspace.dispose();
});

test('failed recheck preserves notes and decisions entered while its request was outstanding',async()=>{
 const h=await harness({draft:true});let reject,started;
 const pending=new Promise(resolve=>started=resolve);
 h.beforeCandidates=()=>{started();return new Promise((_,fail)=>reject=fail);};
 const work=h.workspace.refreshComparisons(h.id);await pending;
 h.workspace.state.resolutions[h.row]={decision:'Check payment timing',note:'New local note while waiting'};
 reject(Error('offline'));await assert.rejects(work,/offline/);
 assert.equal(h.workspace.state.statements[0].reviewMode,'manual');
 assert.equal(h.workspace.state.resolutions[h.row].note,'New local note while waiting');h.workspace.dispose();
});

test('access disposal during recheck cannot restore pinned private data after a late failure',async()=>{
 const h=await harness({draft:true});let reject,started;
 const pending=new Promise(resolve=>started=resolve);
 h.beforeCandidates=()=>{started();return new Promise((_,fail)=>reject=fail);};
 const work=h.workspace.refreshComparisons(h.id);await pending;h.workspace.dispose();reject(Error('access expired'));
 await assert.rejects(work);assert.equal(h.workspace.state.details.size,0);assert.deepEqual(h.workspace.state.resolutions,{});
});

test('explicit latest recheck with no saved BILL source retains the manual review instead of clearing it',async()=>{
 const h=await harness({draft:true});h.current=null;h.version++;
 await assert.rejects(h.workspace.refreshComparisons(h.id),/BILL data.*unavailable/i);
 assert.equal(h.workspace.state.statements[0].reviewMode,'manual');
 assert.equal(h.workspace.state.resolutions[h.row].decision,'Follow up with vendor');h.workspace.dispose();
});
