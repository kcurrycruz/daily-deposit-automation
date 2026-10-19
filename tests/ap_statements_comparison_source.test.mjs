import test from 'node:test';
import assert from 'node:assert/strict';
import {reconcile} from '../app/ap_statements/frontend/core.mjs';
import {billDataSummary,confirmVendor} from '../app/ap_statements/frontend/simple-flow.mjs';
const importId='00000000-0000-4000-8000-000000000001';
const doc=()=>({id:'statement-1',vendor:'Synthetic',layout:'generic',confirmed:true,rows:[{id:'row-1',invoiceNumber:'00042',type:'invoice',amount:13800,balance:13800,page:1,confidence:99}]});
const info={id:importId,record_count:223425,storage_format:'snapshot-v2',metadata:{label:'large.csv',sourceFormat:'bill-native'}};
const records=[{id:importId+':0',vendor:'Synthetic',invoiceNumber:'00042',amount:13800,kind:'invoice',comparisonScope:'invoice-only',status:'Open'}];
const vendors=[{vendor:'Synthetic'},{vendor:'Other'}];
const hash=async value=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value))))].map(b=>b.toString(16).padStart(2,'0')).join('');
async function api(){try{return await import('../app/ap_statements/frontend/comparison-source.mjs');}catch(error){assert.fail('Complete scoped BILL comparison source is not implemented: '+error.code);}}
async function fixture(overrides={}){const digest=await hash(vendors),calls=[];const client={async request(action,payload){calls.push({action,payload});if(overrides[action])return overrides[action](payload);if(action==='bill_vendors_page')return {importId,vendors,total:2,nextCursor:null,vendorDigest:digest};if(action==='bill_candidates_page')return {importId,queryDigest:'a'.repeat(64),total:1,afterOrdinal:-1,records,nextCursor:null};throw Error(action);}};const {createComparisonSource}=await api();return {source:createComparisonSource(client),calls,digest};}

test('metadata count is not candidate count and no full record download occurs',async()=>{
 const {source,calls}=await fixture();const provider=await source.loadDirectory(info);assert.equal(provider.recordCount,223425);assert.equal(provider.records.length,0);
 const statement=doc();await source.ensure(statement,{});assert.equal(provider.scopes[statement.id].records.length,1);
 assert.equal(reconcile(statement,provider,{})[0].status,'presence');assert.ok(calls.every(c=>c.action!=='records_page'));
});
test('partial candidate pages cannot become a unique match or missing invoice',async()=>{
 let complete;const waiting=new Promise(resolve=>complete=resolve);const {source}=await fixture({bill_candidates_page:()=>waiting});
 const provider=await source.loadDirectory(info),statement=doc(),loading=source.ensure(statement,{});
 assert.equal(reconcile(statement,provider,{})[0].status,'unverified');
 complete({importId,queryDigest:'a'.repeat(64),total:2,afterOrdinal:-1,records,nextCursor:null});
 await assert.rejects(loading,/incomplete|complete|unavailable/i);assert.equal(reconcile(statement,provider,{})[0].status,'unverified');
});
test('a missing reference for a known directory vendor is missing, not unresolved vendor',async()=>{
 const {source}=await fixture({bill_candidates_page:()=>({importId,queryDigest:'a'.repeat(64),total:0,afterOrdinal:-1,records:[],nextCursor:null})});
 const provider=await source.loadDirectory(info),statement=doc();await source.ensure(statement,{});
 assert.equal(reconcile(statement,provider,{})[0].status,'missing');
});
test('partial vendor directory cannot establish a unique vendor',async()=>{
 const {source}=await fixture({bill_vendors_page:()=>({importId,vendors:[vendors[0]],total:2,nextCursor:null,vendorDigest:'a'.repeat(64)})});
 await assert.rejects(source.loadDirectory(info),/directory|incomplete|complete/i);
});
test('editing a reference invalidates the old scope and stale responses cannot overwrite it',async()=>{
 let finishOld;let first=true;const old=new Promise(resolve=>finishOld=resolve);
 const {source}=await fixture({bill_candidates_page:payload=>{if(first){first=false;return old;}return {importId,queryDigest:'b'.repeat(64),total:0,afterOrdinal:-1,records:[],nextCursor:null};}});
 const provider=await source.loadDirectory(info),statement=doc();const earlier=source.ensure(statement,{});
 await new Promise(resolve=>setImmediate(resolve));statement.rows[0].invoiceNumber='NEW';source.invalidate(statement.id);
 await source.ensure(statement,{});finishOld({importId,queryDigest:'a'.repeat(64),total:1,afterOrdinal:-1,records,nextCursor:null});await earlier;
 assert.equal(provider.scopes[statement.id].records.length,0);assert.equal(reconcile(statement,provider,{})[0].status,'missing');
});
test('query keys above 100 are batched without losing or duplicating candidates',async()=>{
 const {source,calls}=await fixture({bill_candidates_page:payload=>{assert.ok(payload.query.references.length+payload.query.amounts.length<=100);return {importId,queryDigest:'a'.repeat(64),total:1,afterOrdinal:-1,records,nextCursor:null};}});
 const provider=await source.loadDirectory(info),statement=doc();statement.rows=Array.from({length:101},(_,i)=>({...statement.rows[0],id:'row-'+i,invoiceNumber:String(i)}));
 await source.ensure(statement,{});assert.ok(calls.filter(c=>c.action==='bill_candidates_page').length>=2);assert.equal(provider.scopes[statement.id].records.length,1);
});
test('exact reference with a different amount is not replaced by another amount candidate',async()=>{
 const candidates=[{...records[0],amount:14000},{...records[0],id:importId+':1',invoiceNumber:'OTHER'}];
 const {source}=await fixture({bill_candidates_page:()=>({importId,queryDigest:'a'.repeat(64),total:2,afterOrdinal:-1,records:candidates,nextCursor:null})});
 const provider=await source.loadDirectory(info),statement=doc();await source.ensure(statement,{});const result=reconcile(statement,provider,{})[0];
 assert.equal(result.status,'amount');assert.equal(result.candidates[0].invoiceNumber,'00042');
});
test('BILL summary and vendor confirmation use the directory rather than the candidate subset',async()=>{
 const {source}=await fixture();const provider=await source.loadDirectory(info);
 assert.equal(billDataSummary(provider).count,223425);
 const statement=doc();statement.vendor='Unidentified vendor';let saved=false;
 await confirmVendor(statement,'Other',{state:{provider}},async()=>{saved=true;});
 assert.equal(saved,true);assert.equal(statement.vendor,'Other');
});
