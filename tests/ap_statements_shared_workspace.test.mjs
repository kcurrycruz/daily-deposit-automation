import test from 'node:test';
import assert from 'node:assert/strict';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
const importId=crypto.randomUUID();
const doc=()=>({id:crypto.randomUUID(),vendor:'Alpha',filename:'statement.pdf',layout:'generic',statementDate:'2026-10-01',declaredTotal:18400,confirmed:true,pageCount:1,notes:'Keep this note',warnings:[],rows:[{id:crypto.randomUUID(),invoiceNumber:'00042',type:'invoice',amount:18400,balance:18400,page:1,confidence:99}]});
const snapshot=()=>({activeImport:{id:importId,metadata:{label:'Bills.csv',asOf:'2026-10-01',sourceFormat:'bill-native'},record_count:5610},mappings:{},mappingVersions:{},statements:[],nextCursor:null});

test('adoption rechecks the active version and rejects a late older directory response',async()=>{
 const a=crypto.randomUUID(),b=crypto.randomUUID(),vendors=[{vendor:'Alpha'}];
 const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(vendors))))].map(b=>b.toString(16).padStart(2,'0')).join('');
 let current={importId:a,importVersion:1,recordCount:1,metadata:{label:'A.csv'}},release,started;
 const held=new Promise(r=>started=r);
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){
  if(action==='bill_current')return structuredClone(current);
  if(action==='bill_vendors_page'){if(payload.import_id===a){started();await new Promise(r=>release=r);}return {importId:payload.import_id,vendors,total:1,vendorDigest:digest,nextCursor:null};}
  throw Error(action);
 }});
 const old=workspace.adoptImport({importId:a,recordCount:1,metadata:{label:'Old acknowledgement'}});await held;
 current={importId:b,importVersion:2,recordCount:1,metadata:{label:'B.csv'}};
 await workspace.adoptImport(current);release();await assert.rejects(old,/changed|newer/i);
 assert.equal(workspace.state.importId,b);assert.equal(workspace.state.provider.label,'B.csv');workspace.dispose();
});

test('retrying directory readback after a newer activation adopts the fresh source, not cached acknowledgement',async()=>{
 const a=crypto.randomUUID(),b=crypto.randomUUID(),vendors=[{vendor:'Alpha'}],digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(vendors))))].map(b=>b.toString(16).padStart(2,'0')).join('');
 let current={importId:a,importVersion:1,recordCount:1,metadata:{label:'A.csv'}},offline=true;
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){if(action==='bill_current')return current;if(action==='bill_vendors_page'){if(offline)throw Error('offline');return {importId:payload.import_id,vendors,total:1,vendorDigest:digest,nextCursor:null};}throw Error(action);}});
 const ack={importId:a,recordCount:1,metadata:{label:'A.csv'}};await assert.rejects(workspace.adoptImport(ack),/offline/);
 offline=false;current={importId:b,importVersion:2,recordCount:1,metadata:{label:'B.csv'}};
 await workspace.adoptImport(ack);assert.equal(workspace.state.importId,b);assert.equal(workspace.state.provider.label,'B.csv');workspace.dispose();
});

test('snapshot capability uses metadata and complete scopes, preserving pinned draft source until explicit refresh',async()=>{
  const oldId=crypto.randomUUID(),directory=[{vendor:'Alpha'}],digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(directory))))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const active={id:importId,metadata:{label:'large.csv',asOf:'2026-10-19'},record_count:223425,storage_format:'snapshot-v2',vendorDigest:digest};const calls=[];
  const client={dispose(){},async request(action,payload){calls.push({action,payload});if(action==='bootstrap')return {...snapshot(),activeImport:active,capabilities:{billSnapshots:2}};if(action==='bill_vendors_page')return {importId:payload.import_id,vendors:directory,total:1,nextCursor:null,vendorDigest:digest};if(action==='bill_candidates_page')return {importId:payload.query.importId,queryDigest:'a'.repeat(64),total:1,records:[{id:payload.query.importId+':0',vendor:'Alpha',invoiceNumber:'00042',amount:18400}],nextCursor:null,afterOrdinal:-1};throw Error(action);}};
  const workspace=createSharedWorkspace(client);await workspace.load();assert.equal(workspace.state.provider.recordCount,223425);assert.equal(workspace.state.provider.records.length,0);
  const item=doc();workspace.state.statements.push(item);workspace.state.details.set(item.id,{doc:item,version:1,importId:oldId,importInfo:{...active,id:oldId,record_count:1},resolutions:{}});
  workspace.state.resolutions[item.rows[0].id]={decision:'Reviewed — no action needed',note:'Keep this note'};
  await workspace.ensureComparisons(item);assert.equal(workspace.state.provider.scopes[item.id].importId,oldId);
  await workspace.refreshComparisons(item.id);assert.equal(workspace.state.provider.scopes[item.id].importId,importId);
  assert.deepEqual(workspace.state.resolutions[item.rows[0].id],{note:'Keep this note'});
  assert.ok(calls.every(c=>c.action!=='records_page'));workspace.dispose();
});
test('all import records load before matching, including 5610 rows',async()=>{
  let pages=0;
  const client={dispose(){},async request(action,payload){if(action==='bootstrap')return snapshot();if(action==='records_page'){pages++;const start=payload.after_ordinal+1,n=Math.min(500,5610-start);return {importId,recordCount:5610,records:Array.from({length:n},(_,i)=>({id:`${importId}:${start+i}`,vendor:'Alpha',invoiceNumber:`00${start+i}`,amount:18400})),nextCursor:start+n<5610?start+n-1:null};}throw Error(action);}};
  const workspace=createSharedWorkspace(client);const state=await workspace.load();assert.equal(state.provider.loaded,true);assert.equal(state.provider.records.length,5610);assert.equal(new Set(state.provider.records.map(r=>r.id)).size,5610);assert.equal(pages,12);assert.equal(state.provider.label,'Bills.csv');workspace.dispose();
});
test('missing pages or outage cannot silently restore browser local records',async()=>{
  const states=[];const workspace=createSharedWorkspace({dispose(){},async request(){throw Error('offline');}},{onState:s=>states.push(s)});
  await assert.rejects(workspace.load(),/offline/);assert.equal(workspace.state.provider.loaded,false);assert.equal(workspace.state.statements.length,0);assert.equal(workspace.state.ready,false);
});
test('incomplete record pages reject rather than reporting missing invoices',async()=>{
  const workspace=createSharedWorkspace({dispose(){},async request(){return {records:[],recordCount:2,importId,nextCursor:null};}});
  await assert.rejects(workspace.loadProvider(importId),/incomplete/i);
});
test('original is saved before extraction fails, leaving an unconfirmed draft',async()=>{
  const draft=doc();draft.confirmed=false;draft.rows=[];const calls=[];
  const workspace=createSharedWorkspace({dispose(){},async request(action){calls.push(action);if(action==='upload_begin')return {upload_id:crypto.randomUUID()};if(action==='upload_finish')return {statement_id:draft.id,version:1,duplicate:false};if(action==='statement')return {doc:draft,version:1,originalAvailable:true,resolutions:{},results:[],importId:null,mappingSnapshot:{}};if(action==='save_revision')return {statement_id:draft.id,version:2};return {};}});
  const file=new File(['%PDF-synthetic'],'same.pdf',{type:'application/pdf'});
  const result=await workspace.uploadStatement(file,async()=>{throw Error('OCR failure');});assert.equal(result.doc.confirmed,false);assert.equal(result.originalAvailable,true);assert.ok(result.doc.warnings.some(x=>x.includes('OCR failure')));assert.ok(calls.indexOf('upload_finish')<calls.indexOf('save_revision'));
});
test('same hash uses existing corrected statement without re-extraction',async()=>{
  const existing=doc();let extracted=0;
  const workspace=createSharedWorkspace({dispose(){},async request(action){if(action==='upload_begin')return {upload_id:crypto.randomUUID()};if(action==='upload_finish')return {statement_id:existing.id,version:4,duplicate:true};if(action==='statement')return {doc:existing,version:4,originalAvailable:true,resolutions:{}};return {};}});
  const result=await workspace.uploadStatement(new File(['%PDF-synthetic'],'new-name.pdf'),async()=>{extracted++;});assert.equal(result.doc.notes,'Keep this note');assert.equal(extracted,0);
});
test('failed save preserves edits; retry uses the same mutation identity and saved only on acknowledgement',async()=>{
  const states=[],requests=[];let fail=true;const item=doc(),revisionId=crypto.randomUUID();
  const workspace=createSharedWorkspace({dispose(){},async request(action,payload,options){requests.push(options.requestId);if(fail)throw Error('offline');return action==='save_revision'?{statement_id:item.id,version:3,revision_id:revisionId}:{doc:item,version:3,revisionVersion:3,revisionId,resolutions:{}};}},{onSaveState:s=>states.push(s)});
  let error;try{await workspace.saveStatement(item,2);}catch(e){error=e;}
  assert.deepEqual(states,['saving','not_saved']);assert.equal(item.notes,'Keep this note');fail=false;await error.retry();assert.equal(requests[0],requests[1]);assert.equal(states.at(-1),'saved');
});

test('saved reviews immediately adopt the server timestamp from the exact acknowledged revision',async()=>{
  const item=doc(),row=item.rows[0].id,revisionId=crypto.randomUUID(),at='2026-10-14T18:55:00+00:00',calls=[];
  const resolution={decision:'Reviewed — no action needed',note:''};
  const workspace=createSharedWorkspace({dispose(){},async request(action,payload){calls.push({action,payload});return action==='save_revision'?{statement_id:item.id,version:3,revision_id:revisionId}:{doc:item,version:3,revisionVersion:3,revisionId,resolutions:{[row]:{...resolution,at}},completed:false,archived:false};}});
  const saved=await workspace.saveStatement(item,2,{resolutions:{[row]:resolution}});
  assert.equal(saved.resolutions[row].at,at);assert.equal(workspace.state.resolutions[row].at,at);
  assert.deepEqual(calls[1],{action:'statement',payload:{statement_id:item.id,revision_id:revisionId}});
});

test('post-save read failure keeps edits and retries readback without another save mutation',async()=>{
  const item=doc(),revisionId=crypto.randomUUID(),states=[],calls=[];let offline=true;
  const workspace=createSharedWorkspace({dispose(){},async request(action,payload,options){calls.push({action,id:options.requestId});if(action==='save_revision')return {statement_id:item.id,version:3,revision_id:revisionId};if(offline)throw Error('read offline');return {doc:item,version:3,revisionVersion:3,revisionId,resolutions:{}};}},{onSaveState:s=>states.push(s)});
  workspace.state.statements=[item];let failure;
  try{await workspace.saveStatement(item,2);}catch(error){failure=error;}
  assert.ok(failure);assert.equal(workspace.state.statements[0],item);assert.equal(item.notes,'Keep this note');assert.equal(states.at(-1),'not_saved');
  offline=false;await failure.retry();assert.equal(calls.filter(c=>c.action==='save_revision').length,1);assert.equal(calls[1].id,calls[2].id);assert.equal(states.at(-1),'saved');
});

test('a concurrently advanced head cannot be adopted as an editable saved revision',async()=>{
  const item=doc(),revisionId=crypto.randomUUID();
  const workspace=createSharedWorkspace({dispose(){},async request(action){return action==='save_revision'?{statement_id:item.id,version:3,revision_id:revisionId}:{doc:{...item,notes:'Old saved snapshot'},version:4,revisionVersion:3,revisionId,resolutions:{},completed:false};}});
  workspace.state.statements=[item];workspace.state.details.set(item.id,{doc:item,version:2});
  await assert.rejects(workspace.saveStatement(item,2),/changed.*reload/i);
  assert.equal(workspace.state.statements[0],item);assert.equal(workspace.state.details.get(item.id).version,2);
});

test('retry after readback outage cannot overwrite corrections or decisions entered after failure',async()=>{
  for(const change of ['doc','review']){
    const item=doc(),row=item.rows[0].id,revisionId=crypto.randomUUID();let offline=true,snapshot;
    const workspace=createSharedWorkspace({dispose(){},async request(action,payload){if(action==='save_revision'){snapshot=structuredClone(payload);return {statement_id:item.id,version:3,revision_id:revisionId};}if(offline)throw Error('read offline');return {doc:snapshot.doc,version:3,revisionVersion:3,revisionId,resolutions:snapshot.resolutions};}});
    workspace.state.statements=[item];workspace.state.resolutions[row]={decision:'Follow up with vendor',note:''};let failure;
    try{await workspace.saveStatement(item,2);}catch(error){failure=error;}
    if(change==='doc')item.notes='New correction after failure';else workspace.state.resolutions[row]={decision:'Investigate amount difference',note:'New note'};
    offline=false;await assert.rejects(failure.retry(),/local edits.*changed/i);
    assert.equal(workspace.state.statements[0],item);
    if(change==='doc')assert.equal(item.notes,'New correction after failure');else assert.equal(workspace.state.resolutions[row].note,'New note');
  }
});
test('failed import retains prior provider and does not show Saved',async()=>{
  const states=[];const workspace=createSharedWorkspace({dispose(){},async request(){throw Error('offline');}},{onSaveState:s=>states.push(s)});
  const previous={loaded:true,simulated:false,label:'older.csv',records:[{vendor:'Alpha',invoiceNumber:'00042',amount:18400}]};workspace.state.provider=previous;workspace.state.importId=importId;
  await assert.rejects(workspace.importBills(new File(['vendor,invoiceNumber,amount\nAlpha,00043,184.00'],'new.csv'),{...previous,label:'new.csv'}),/offline/);
  assert.equal(workspace.state.provider,previous);assert.equal(workspace.state.importId,importId);assert.equal(states.at(-1),'not_saved');
});
test('a reload without explicit replacement preserves unsaved in-memory corrections',async()=>{
  let reads=0;const workspace=createSharedWorkspace({dispose(){},async request(){reads++;return {...snapshot(),activeImport:null};}});
  await workspace.load();workspace.state.statements.push(doc());await workspace.load();assert.equal(reads,1);assert.equal(workspace.state.statements[0].notes,'Keep this note');
  workspace.dispose();assert.equal(workspace.state.statements.length,0);assert.equal(workspace.state.provider.records.length,0);
});
test('historical revisions stay read-only against their frozen import and results',async()=>{
  const original=doc(),frozen={doc:original,version:8,revisionVersion:3,results:[{id:original.rows[0].id,status:'possible'}],importId:'old-import',mappingSnapshot:{Alpha:'Old Alpha'},completed:false};
  const workspace=createSharedWorkspace({dispose(){},async request(){return frozen;}});workspace.state.importId='new-import';workspace.state.provider={loaded:true,records:[]};
  const detail=await workspace.statement(original.id,crypto.randomUUID());assert.equal(detail.readOnly,true);assert.equal(detail.importId,'old-import');assert.equal(detail.results[0].status,'possible');assert.equal(workspace.state.importId,'new-import');
});
test('completion acknowledgement retry preserves identity and removes completed work only on acknowledgement',async()=>{
  const original=doc();let fail=true;const ids=[],workspace=createSharedWorkspace({dispose(){},async request(action,payload,{requestId}){ids.push(requestId);if(fail)throw Object.assign(Error('lost acknowledgement'),{code:'timeout'});return {version:3};}});
  workspace.state.statements=[original];workspace.state.details.set(original.id,{doc:original,version:2});let failure;
  try{await workspace.completeStatement({statement_id:original.id,expected_version:2,initials:'KC',notes:''});}catch(error){failure=error;}
  assert.equal(workspace.state.statements.length,1);fail=false;await failure.retry();assert.equal(ids[0],ids[1]);assert.equal(workspace.state.statements.length,0);assert.equal(workspace.state.details.get(original.id).readOnly,true);
});
test('completion first acknowledges the exact current comparison source before freezing it',async()=>{
  const original=doc(),calls=[];const workspace=createSharedWorkspace({dispose(){},async request(action,payload){calls.push({action,payload});return {statement_id:original.id,version:action==='save_revision'?3:4};}});
  workspace.state.statements=[original];workspace.state.details.set(original.id,{doc:original,version:2,importId:'old-source',results:[{id:original.rows[0].id,status:'missing'}]});
  workspace.state.importId=importId;workspace.state.provider={loaded:true,simulated:false,records:[{id:'bill',vendor:'Alpha',invoiceNumber:'00042',amount:18400,currency:'USD'}]};
  await workspace.completeStatement({statement_id:original.id,expected_version:2,initials:'KC',notes:''});
  assert.equal(calls[0].action,'save_revision');assert.equal(calls[0].payload.import_id,importId);assert.equal(calls[0].payload.results[0].status,'matched');assert.equal(calls[1].action,'complete_revision');assert.equal(calls[1].payload.expected_version,3);
});
