import test from 'node:test';
import assert from 'node:assert/strict';
import {createSharedWorkspace,comparisonSnapshot} from '../app/ap_statements/frontend/shared-workspace.mjs';
const importId=crypto.randomUUID(),firstSet=crypto.randomUUID(),secondSet=crypto.randomUUID();
const vendor=[{vendor:'Synthetic'}];
const hash=async v=>Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(v)))) .toString('hex');

test('same-import range change refreshes comparisons and saved scope, retaining notes',async()=>{
 const vendorDigest=await hash(vendor);
 const makeSet=(id,ch)=>({workingSetId:id,workingDigest:ch.repeat(64),vendorDigest,activeCount:1,policy:{mode:'last_12_months',cutoffDate:'2025-10-30'}});
 const first=makeSet(firstSet,'a'),second=makeSet(secondSet,'b');let selected=first,workingVersion=1,savedPayload;
 const doc={id:crypto.randomUUID(),vendor:'Synthetic',filename:'statement.pdf',confirmed:true,pageCount:1,warnings:[],rows:[{id:crypto.randomUUID(),invoiceNumber:'00042',type:'invoice',amount:10000,balance:10000,page:1,confidence:99}]};
 const revisionId=crypto.randomUUID(),calls=[];
 const current=()=>({importId,importVersion:1,workingVersion,workingSet:selected,recordCount:100,metadata:{label:'full.csv'},protectionsCurrent:true});
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){calls.push({action,payload});
  if(action==='bootstrap')return {activeImport:{id:importId,record_count:100,workingSet:first,metadata:{label:'full.csv'}},importVersion:1,workingVersion:1,capabilities:{billSnapshots:2,billWorkingSets:1},statements:[],mappings:{},mappingVersions:{},nextCursor:null};
  if(action==='bill_current')return current();
  if(action==='bill_vendors_page')return {importId,workingSetId:selected.workingSetId,workingDigest:selected.workingDigest,vendors:vendor,total:1,vendorDigest,nextCursor:null};
  if(action==='bill_candidates_page')return {importId,workingSetId:selected.workingSetId,workingDigest:selected.workingDigest,total:1,queryDigest:'c'.repeat(64),afterOrdinal:-1,records:[{id:importId+':99',vendor:'Synthetic',invoiceNumber:'00042',kind:'invoice',amount:10000,comparisonScope:'invoice-only'}],nextCursor:null};
  if(action==='save_revision'){savedPayload=structuredClone(payload);return {version:3,revision_id:revisionId};}
  if(action==='statement')return {doc,version:3,revisionVersion:3,revisionId,completed:false,archived:false,workingSetId:secondSet,importId,resolutions:{},results:savedPayload.results};
  throw Error(action);
 }});
 try{
  await workspace.load();workspace.state.statements.push(doc);
  workspace.state.details.set(doc.id,{doc,version:2,importId,workingSetId:firstSet,importInfo:workspace.state.activeImport});
  workspace.state.resolutions[doc.rows[0].id]={decision:'Reviewed — no action needed',note:'Keep my note'};
  selected=second;workingVersion=2;
  await workspace.prepareStatement(doc);
  assert.equal(workspace.state.activeImport.workingSet.workingSetId,secondSet);
  assert.equal(workspace.state.workingVersion,2);
  assert.deepEqual(workspace.state.resolutions[doc.rows[0].id],{note:'Keep my note'});
  await workspace.saveStatement(doc,2);
  assert.equal(savedPayload.working_set_id,secondSet);assert.equal(savedPayload.working_version,2);
  assert.ok(calls.filter(c=>c.action==='bill_current').every(c=>c.payload.include_working===true));
 }finally{workspace.dispose();}
});


test('protection-only refresh preserves a saved decision when the original bill evidence is unchanged',async()=>{
 for(const refreshPath of ['ensureFresh','prepareStatement','reload','shrink']){
 const vendorDigest=await hash(vendor),doc={id:crypto.randomUUID(),vendor:'Synthetic',filename:'statement.pdf',confirmed:true,pageCount:1,warnings:[],rows:[{id:'row',invoiceNumber:'00042',type:'invoice',amount:10000,balance:10000,page:1,confidence:99}]};
 const policy={mode:'last_12_months',asOfDate:'2026-10-30',cutoffDate:'2025-10-30'};
 const old={workingSetId:firstSet,workingDigest:'a'.repeat(64),vendorDigest,activeCount:1,policy},next={...old,workingSetId:secondSet,workingDigest:'b'.repeat(64)};
 let selected=old,stale=false,version=1,snapshot,reloading=false;const revisionId=crypto.randomUUID();
 const current=()=>({importId,importVersion:1,workingVersion:version,workingSet:selected,recordCount:100,metadata:{label:'full.csv'},protectionsCurrent:!stale});
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){
  if(action==='bootstrap')return {activeImport:{id:importId,record_count:100,workingSet:selected,protectionsCurrent:!stale,metadata:{label:'full.csv'}},importVersion:1,workingVersion:version,capabilities:{billSnapshots:2,billWorkingSets:1},statements:reloading?[{id:doc.id}]:[],mappings:{},mappingVersions:{},nextCursor:null};
  if(action==='bill_current')return current();
  if(action==='bill_vendors_page')return {importId,workingSetId:selected.workingSetId,workingDigest:selected.workingDigest,vendors:vendor,total:1,vendorDigest,nextCursor:null};
  if(action==='bill_candidates_page')return {importId,workingSetId:selected.workingSetId,workingDigest:selected.workingDigest,total:selected===next&&refreshPath==='shrink'?0:1,queryDigest:'c'.repeat(64),afterOrdinal:-1,records:selected===next&&refreshPath==='shrink'?[]:[{id:importId+':99',vendor:'Synthetic',invoiceNumber:'00042',invoiceDate:'2025-01-01',kind:'invoice',amount:10000,status:'PaidInFull',reportedAmountDue:0,comparisonScope:'invoice-only'}],nextCursor:null};
  if(action==='save_revision'){snapshot=structuredClone(payload);stale=true;return {version:2,revision_id:revisionId};}
  if(action==='statement')return {doc,version:2,revisionVersion:2,revisionId,completed:false,archived:false,workingSetId:firstSet,importId,importInfo:{id:importId,workingSet:old},resolutions:snapshot.resolutions,results:snapshot.results};
  if(action==='bill_range_begin'){assert.equal(payload.refresh,true);return {state:'prepared',job_id:'j',generation:'g',checkpoint:0,manifest:next};}
  if(action==='bill_range_activate'){selected=next;version=2;stale=false;return current();}
  throw Error(action);
 }});
 try{
  await workspace.load();workspace.state.statements.push(doc);workspace.state.details.set(doc.id,{doc,version:1,importId,workingSetId:firstSet});
  await workspace.ensureComparisons(doc);const decision=refreshPath==='shrink'?'Reviewed — no action needed':'Follow up with vendor';workspace.state.resolutions.row={decision,note:'Retain this follow-up'};
  await workspace.saveStatement(doc,1);if(refreshPath==='reload'){reloading=true;await workspace.load({replace:true});}else if(refreshPath==='prepareStatement')await workspace.prepareStatement(doc);else await workspace.ensureFresh();await workspace.ensureComparisons(doc);
  if(refreshPath==='shrink'){assert.equal(comparisonSnapshot(doc,workspace.state.provider,{})[0].status,'presence');assert.equal(comparisonSnapshot(doc,workspace.state.provider,{})[0].coverage,'archived');}
  assert.equal(workspace.state.workingVersion,2);assert.equal(workspace.state.resolutions.row.decision,decision);assert.equal(workspace.state.resolutions.row.note,'Retain this follow-up');
 }finally{workspace.dispose();}
 }
});


test('a concurrent different export cannot inherit retained evidence from a protection refresh',async()=>{
 const other=crypto.randomUUID(),vendorDigest=await hash(vendor),policy={mode:'last_12_months',cutoffDate:'2025-10-30'};
 const scope={workingSetId:firstSet,workingDigest:'a'.repeat(64),activeCount:1,vendorDigest,policy};let changed=false;
 const doc={id:crypto.randomUUID(),vendor:'Synthetic',confirmed:true,rows:[{id:'row',invoiceNumber:'00042',type:'invoice',amount:10000,balance:10000,page:1,confidence:99}]};
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){
  const id=changed?other:importId,workingSet=changed?{...scope,workingSetId:secondSet,workingDigest:'b'.repeat(64)}:scope;
  if(action==='bootstrap')return {activeImport:{id:importId,record_count:100,workingSet:scope},importVersion:1,workingVersion:1,capabilities:{billSnapshots:2,billWorkingSets:1},statements:[],mappings:{},mappingVersions:{},nextCursor:null};
  if(action==='bill_current')return {importId:id,importVersion:changed?2:1,workingVersion:changed?2:1,workingSet,recordCount:100,protectionsCurrent:true};
  if(action==='bill_vendors_page')return {importId:id,workingSetId:workingSet.workingSetId,workingDigest:workingSet.workingDigest,vendors:vendor,total:1,vendorDigest,nextCursor:null};
  if(action==='bill_candidates_page')return {importId:id,workingSetId:workingSet.workingSetId,workingDigest:workingSet.workingDigest,total:1,queryDigest:'c'.repeat(64),afterOrdinal:-1,records:[{id:id+':99',vendor:'Synthetic',invoiceNumber:'00042',kind:'invoice',amount:10000,comparisonScope:'invoice-only'}],nextCursor:null};
  throw Error(action);
 }});
 try{
  await workspace.load();workspace.state.statements.push(doc);workspace.state.details.set(doc.id,{doc,importId,workingSetId:firstSet,version:1});await workspace.ensureComparisons(doc);
  workspace.state.resolutions.row={decision:'Reviewed — no action needed',note:'Keep the note'};changed=true;
  await workspace.adoptImport({},{preserveCompatible:true});await workspace.ensureComparisons(doc);
  assert.equal(workspace.state.resolutions.row.decision,undefined);assert.equal(workspace.state.resolutions.row.note,'Keep the note');assert.equal(comparisonSnapshot(doc,workspace.state.provider,{})[0].candidates[0].id,other+':99');
 }finally{workspace.dispose();}
});
