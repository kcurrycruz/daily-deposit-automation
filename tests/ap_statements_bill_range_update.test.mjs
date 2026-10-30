import test from 'node:test';
import assert from 'node:assert/strict';
import {createBillUpdateUI} from '../app/ap_statements/frontend/bill-update-ui.mjs';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';

test('new-capability uploads prepare the full export then apply the requested range before adoption',async()=>{
 const events=[];let options;
 const shared={state:{capabilities:{billSnapshots:2,billWorkingSets:1}},ranges:{async prepareUploaded(result,mode){events.push(['range',result.importId,mode]);return {...result,workingSet:{activeCount:12}};}},async adoptImport(){throw Error('A scoped update must not publish through legacy adoption');}};
 const ui=createBillUpdateUI({shared,client:{},importer:async(c,file,o)=>{options=o;events.push(['prepared']);return {state:'prepared',importId:'new',job_id:'upload'};}});
 const result=await ui.update({name:'weekly.csv'});assert.equal(options.prepareOnly,true);assert.equal(result.workingSet.activeCount,12);assert.deepEqual(events,[['prepared'],['range','new','last_12_months']]);ui.dispose();
});
test('existing saved full coverage remains full until explicit apply; stale protections refresh before directory reads',async()=>{
 const id=crypto.randomUUID(),setId=crypto.randomUUID(),vendors=[{vendor:'Synthetic'}];
 const digest=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(vendors)))).toString('hex');
 const mf={workingSetId:setId,workingDigest:'a'.repeat(64),policy:{mode:'last_12_months',cutoffDate:'2025-10-30'},activeCount:1,fullRecordCount:10,vendorDigest:digest};
 let stale=true;const calls=[];
 const current=()=>({importId:id,importVersion:1,workingVersion:1,workingSet:mf,recordCount:10,metadata:{label:'full.csv'},protectionsCurrent:!stale});
 const workspace=createSharedWorkspace({dispose(){},async request(action,payload){calls.push(action);
  if(action==='bootstrap')return {activeImport:{id,record_count:10,metadata:{label:'full.csv'},workingSet:mf,protectionsCurrent:false},importVersion:1,workingVersion:1,capabilities:{billSnapshots:2,billWorkingSets:1},statements:[],mappings:{},nextCursor:null};
  if(action==='bill_current')return current();
  if(action==='bill_range_begin'){assert.equal(payload.refresh,true);return {state:'prepared',job_id:'j',generation:'g',checkpoint:0,manifest:mf};}
  if(action==='bill_range_activate'){stale=false;return current();}
  if(action==='bill_vendors_page'){assert.equal(stale,false,'No scoped query may use stale protections');return {importId:id,workingSetId:setId,workingDigest:mf.workingDigest,vendors,total:1,vendorDigest:digest,nextCursor:null};}
  throw Error(action);
 }});
 try{await workspace.load();assert.equal(workspace.state.ready,true);assert.ok(calls.indexOf('bill_range_activate')<calls.indexOf('bill_vendors_page'));assert.equal(workspace.state.provider.recordCount,10);}
 finally{workspace.dispose();}
});
