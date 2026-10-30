import test from 'node:test';
import assert from 'node:assert/strict';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
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
