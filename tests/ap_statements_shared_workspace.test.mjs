import test from 'node:test';
import assert from 'node:assert/strict';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
const importId=crypto.randomUUID();
const doc=()=>({id:crypto.randomUUID(),vendor:'Alpha',filename:'statement.pdf',layout:'generic',statementDate:'2026-10-01',declaredTotal:18400,confirmed:true,pageCount:1,notes:'Keep this note',warnings:[],rows:[{id:crypto.randomUUID(),invoiceNumber:'00042',type:'invoice',amount:18400,balance:18400,page:1,confidence:99}]});
const snapshot=()=>({activeImport:{id:importId,metadata:{label:'Bills.csv',asOf:'2026-10-01',sourceFormat:'bill-native'},record_count:5610},mappings:{},mappingVersions:{},statements:[],nextCursor:null});
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
  const states=[],requests=[];let fail=true;const item=doc();
  const workspace=createSharedWorkspace({dispose(){},async request(action,payload,options){requests.push(options.requestId);if(fail)throw Error('offline');return {statement_id:item.id,version:3};}},{onSaveState:s=>states.push(s)});
  let error;try{await workspace.saveStatement(item,2);}catch(e){error=e;}
  assert.deepEqual(states,['saving','not_saved']);assert.equal(item.notes,'Keep this note');fail=false;await error.retry();assert.equal(requests[0],requests[1]);assert.equal(states.at(-1),'saved');
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
