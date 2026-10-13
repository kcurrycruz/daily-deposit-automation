import test from 'node:test';
import assert from 'node:assert/strict';
import {createSharedClient} from '../app/ap_statements/frontend/shared-client.mjs';
const fixture=(timeoutMs=200)=>{let receiver;const sent=[];const client=createSharedClient({send:v=>sent.push(v),subscribe:f=>{receiver=f;return()=>{receiver=null;};},timeoutMs});return {client,sent,reply:v=>receiver?.(v)};};
const ack=(request,data={saved:true})=>({version:1,request_id:request.request_id,ok:true,data,error:null});
test('queues one request at a time and ignores unrelated acknowledgements',async()=>{
  const {client,sent,reply}=fixture();const first=client.request('bootstrap',{}),second=client.request('statement',{statement_id:crypto.randomUUID()});
  assert.equal(sent.length,1);reply({...ack(sent[0]),request_id:crypto.randomUUID()});assert.equal(sent.length,1);
  reply(ack(sent[0],{first:true}));assert.deepEqual(await first,{first:true});assert.equal(sent.length,2);reply(ack(sent[1]));await second;client.dispose();
});
test('timeout offers identical request retry rather than a second write identity',async()=>{
  const {client,sent,reply}=fixture(10);let failure;try{await client.request('complete_revision',{initials:'KC'});}catch(e){failure=e;}
  assert.equal(failure.code,'timeout');const retry=failure.retry();assert.deepEqual(sent[1],sent[0]);reply(ack(sent[1]));await retry;client.dispose();
});
test('dispose rejects outstanding requests and clears subscribers',async()=>{
  const {client,sent}=fixture();const first=client.request('bootstrap',{}),second=client.request('bootstrap',{});
  client.dispose();await assert.rejects(first,/locked/i);await assert.rejects(second,/locked/i);assert.equal(sent.length,1);
});
test('changed payload cannot reuse the same request id',async()=>{
  const {client,sent,reply}=fixture();const requestId=crypto.randomUUID();const first=client.request('save_mapping',{vendor:'A'},{requestId});
  reply(ack(sent[0]));await first;await assert.rejects(client.request('save_mapping',{vendor:'B'},{requestId}),/different payload/i);client.dispose();
});
