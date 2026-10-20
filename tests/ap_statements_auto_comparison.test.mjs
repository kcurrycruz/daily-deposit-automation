import test from 'node:test';
import assert from 'node:assert/strict';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
import {reconcile} from '../app/ap_statements/frontend/core.mjs';

async function fixture(){
  const old=crypto.randomUUID(),latest=crypto.randomUUID(),id=crypto.randomUUID(),rowId=crypto.randomUUID();
  const vendors=[{vendor:'A.J. Rinella & Co., Inc.'}];
  const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(vendors))))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const doc={id,vendor:'A.J. Rinella',filename:'synthetic.pdf',confirmed:true,layout:'rinella',statementDate:'2026-06-26',declaredTotal:13800,notes:'Keep statement note',warnings:[],pageCount:1,rows:[{id:rowId,type:'invoice',invoiceNumber:'261371',amount:13800,balance:13800,page:1,confidence:99}]};
  let current=old,version=1,failCandidates=false;
  const calls=[];
  const info=source=>({id:source,metadata:{label:source===old?'old.csv':'weekly.csv'},record_count:source===old?2:1,storage_format:'snapshot-v2'});
  const client={dispose(){},async request(action,payload){
    calls.push({action,payload});
    if(action==='bootstrap')return {activeImport:info(current),importVersion:version,capabilities:{billSnapshots:2},mappings:{},mappingVersions:{},statements:[{id}],nextCursor:null};
    if(action==='statement')return {doc:structuredClone(doc),version:1,importId:old,importInfo:info(old),originalAvailable:true,resolutions:{[rowId]:{note:'Keep follow-up note',decision:'Follow up with vendor'}},completed:false};
    if(action==='bill_current')return {importId:current,importVersion:version,metadata:info(current).metadata,recordCount:info(current).record_count,storageFormat:'snapshot-v2'};
    if(action==='bill_vendors_page')return {importId:payload.import_id,total:1,vendors,vendorDigest:digest,nextCursor:null};
    if(action==='bill_candidates_page'){
      if(failCandidates)throw Error('Comparison unavailable');
      const source=payload.query.importId,refs=source===old?['261768','261874']:['261371'];
      return {importId:source,queryDigest:'a'.repeat(64),afterOrdinal:-1,total:refs.length,nextCursor:null,records:refs.map((invoiceNumber,i)=>({id:source+':'+i,vendor:vendors[0].vendor,invoiceNumber,amount:13800,kind:'invoice',comparisonScope:'invoice-only',status:'PaidInFull'}))};
    }
    throw Error('Unexpected action '+action);
  }};
  const workspace=createSharedWorkspace(client);
  await workspace.load();await workspace.ensureComparisons(workspace.state.statements[0]);
  return {workspace,client,doc:workspace.state.statements[0],rowId,old,latest,calls,advance(){current=latest;version++;},fail(){failCandidates=true;}};
}

test('a new weekly source refreshes unfinished comparisons without a manual compare click',async()=>{
  const f=await fixture();
  assert.equal(reconcile(f.doc,f.workspace.state.provider)[0].status,'ambiguous');
  const frozen={doc:{id:'completed'},completed:true,readOnly:true,importId:f.old,results:[{status:'ambiguous'}],resolutions:{kept:{note:'Saved evidence'}}};
  f.workspace.state.details.set('completed',frozen);const before=structuredClone(frozen);
  f.advance();await f.workspace.adoptImport({});
  await f.workspace.ensureComparisons(f.doc);
  const row=reconcile(f.doc,f.workspace.state.provider)[0];
  assert.equal(row.matchMethod,'reference');assert.equal(row.status,'presence');
  assert.equal(row.candidates[0].invoiceNumber,'261371');
  assert.equal(f.workspace.state.details.get(f.doc.id).importId,f.latest);
  assert.equal(f.doc.notes,'Keep statement note');
  assert.deepEqual(f.workspace.state.resolutions[f.rowId],{note:'Keep follow-up note'});
  assert.deepEqual(frozen,before);
  assert.ok(f.calls.every(c=>!['save_revision','complete_revision'].includes(c.action)));
  f.workspace.dispose();
});

test('opening a draft notices a newer export saved by another session',async()=>{
  const f=await fixture();f.doc.notes='Unsaved local note';f.advance();
  await f.workspace.prepareStatement(f.doc);
  assert.equal(f.workspace.state.provider.scopes[f.doc.id].importId,f.latest);
  assert.equal(reconcile(f.doc,f.workspace.state.provider)[0].candidates[0].invoiceNumber,'261371');
  assert.equal(f.doc.notes,'Unsaved local note');
  f.workspace.dispose();
});

test('failed refresh cannot keep showing healthy matches against the prior source',async()=>{
  const f=await fixture();f.advance();f.fail();await f.workspace.adoptImport({});
  await assert.rejects(f.workspace.ensureComparisons(f.doc),/unavailable/i);
  assert.equal(reconcile(f.doc,f.workspace.state.provider)[0].status,'unverified');
  assert.equal(f.doc.notes,'Keep statement note');f.workspace.dispose();
});

test('a late failed old-source prepare cannot invalidate a successful newer comparison',async()=>{
  const f=await fixture(),original=f.client.request;let release,started;
  const waiting=new Promise(resolve=>started=resolve);
  f.client.request=async(action,payload)=>{
    if(action==='bill_candidates_page'&&payload.query.importId===f.old){started();await new Promise(resolve=>release=resolve);}
    return original(action,payload);
  };
  const stale=f.workspace.prepareStatement(f.doc).catch(error=>error);await waiting;
  f.advance();await f.workspace.prepareStatement(f.doc);
  assert.equal(f.workspace.state.provider.scopes[f.doc.id].complete,true);
  release();const oldResult=await stale;
  assert.equal(f.workspace.state.provider.scopes[f.doc.id].complete,true);
  assert.equal(reconcile(f.doc,f.workspace.state.provider)[0].matchMethod,'reference');
  assert.ok(!(oldResult instanceof Error),'A superseded read must not show a current failure');
  f.workspace.dispose();
});
