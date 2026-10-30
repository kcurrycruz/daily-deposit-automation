import test from 'node:test';
import assert from 'node:assert/strict';
import {createComparisonSource} from '../app/ap_statements/frontend/comparison-source.mjs';
import {reconcile} from '../app/ap_statements/frontend/core.mjs';
const importId='00000000-0000-4000-8000-000000000001';
const setId='00000000-0000-4000-8000-000000000002';
const digest='a'.repeat(64);
const hash=async value=>Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)))).toString('hex');
const doc=(date='2025-09-01')=>({id:'doc',vendor:'Synthetic',confirmed:true,rows:[{id:'row',invoiceNumber:'OLD',type:'invoice',date,amount:10000,balance:10000,page:1,confidence:99}]});
async function fixture({empty=false,records=[],wrongScope=false}={}){
 const vendors=empty?[]:[{vendor:'Synthetic'}],archiveVendors=[{vendor:'Synthetic'}],vendorDigest=await hash(vendors),archiveVendorDigest=await hash(archiveVendors),calls=[];
 const workingSet={workingSetId:setId,workingDigest:digest,activeCount:empty?0:1,vendorDigest,archiveVendorDigest,policy:{mode:'last_12_months',cutoffDate:'2025-10-30'}};
 const info={id:importId,record_count:223425,workingSet,metadata:{sourceFormat:'bill-native'}};
 const source=createComparisonSource({async request(action,payload){
  calls.push({action,payload});
  const scope={workingSetId:wrongScope?'other':setId,workingDigest:digest};
  if(action==='bill_vendors_page')return payload.include_archived?{importId,...scope,vendors:archiveVendors,total:archiveVendors.length,nextCursor:null,vendorDigest:archiveVendorDigest}:{importId,...scope,vendors,total:vendors.length,nextCursor:null,vendorDigest};
  if(action==='bill_candidates_page')return {importId,...scope,queryDigest:'b'.repeat(64),total:records.length,afterOrdinal:-1,records,nextCursor:null};
  if(action==='bill_archived_candidates_page')return {importId,...scope,queryDigest:'c'.repeat(64),total:1,afterOrdinal:-1,
   records:[{id:importId+':5',vendor:'Synthetic',invoiceNumber:'OLD',amount:10000,kind:'invoice',comparisonScope:'invoice-only'}],archivedIds:[importId+':5'],nextCursor:null};
  throw Error(action);
 }});
 return {source,info,calls};
}

test('active candidate reads include the working identity and preserve sparse original IDs',async()=>{
 const record={id:importId+':223000',vendor:'Synthetic',invoiceNumber:'OLD',amount:10000,kind:'invoice',comparisonScope:'invoice-only'};
 const {source,info,calls}=await fixture({records:[record]});const provider=await source.loadDirectory(info);
 await source.ensure(doc(),{});
 assert.equal(calls.find(c=>c.action==='bill_vendors_page').payload.working_set_id,setId);
 assert.equal(calls.find(c=>c.action==='bill_candidates_page').payload.query.workingSetId,setId);
 assert.equal(provider.scopes.doc.workingSet.workingSetId,setId);
 assert.equal(provider.scopes.doc.records[0].id,record.id);
});

test('old or undated absent references have an outside-range result, never full-source missing',async()=>{
 const {source,info}=await fixture();const provider=await source.loadDirectory(info);
 for(const day of ['2025-09-01','']){
  const statement=doc(day);await source.ensure(statement,{});const row=reconcile(statement,provider,{})[0];
  assert.equal(row.status,'range');assert.match(row.reason,/Outside active BILL range/);
 }
});

test('a valid empty working directory loads and exposes outside-range coverage',async()=>{
 const {source,info}=await fixture({empty:true});const provider=await source.loadDirectory(info);
 await source.ensure(doc(),{});assert.equal(provider.loaded,true);assert.equal(provider.vendorDirectory.length,0);
 assert.equal(reconcile(doc(),provider,{})[0].status,'range');
});

test('wrong-scope response cannot become a verified comparison',async()=>{
 const {source,info}=await fixture({wrongScope:true});await assert.rejects(source.loadDirectory(info),/incomplete|unavailable/i);
});

test('archive lookup is explicit and marks original-source matches as archived',async()=>{
 const {source,info,calls}=await fixture();const statement=doc(),provider=await source.loadDirectory(info);
 await source.ensure(statement,{});assert.equal(calls.some(c=>c.action==='bill_archived_candidates_page'),false);
 assert.equal(typeof source.lookupArchived,'function');
 await source.lookupArchived(statement,{},'OLD','invoice');
 const row=reconcile(statement,provider,{})[0];assert.equal(row.status,'presence');assert.equal(row.coverage,'archived');
 assert.equal(calls.at(-1).payload.references[0].invoiceKey,'OLD');assert.equal(calls.at(-1).payload.amounts,undefined);
});

test('archive lookup can resolve a vendor with no active bills',async()=>{
 const {source,info}=await fixture({empty:true});const statement=doc(),provider=await source.loadDirectory(info);
 await source.ensure(statement,{});await source.lookupArchived(statement,{},'OLD');
 assert.equal(reconcile(statement,provider,{})[0].status,'presence');
});

test('a recent absent reference reports only active coverage, never full-export absence',async()=>{
 const {source,info}=await fixture();const provider=await source.loadDirectory(info),statement=doc('2026-10-01');
 await source.ensure(statement,{});const row=reconcile(statement,provider,{})[0];
 assert.equal(row.status,'range');assert.match(row.reason,/active BILL range/);
});
