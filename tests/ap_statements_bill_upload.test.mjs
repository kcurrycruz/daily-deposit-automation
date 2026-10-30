import test from 'node:test';
import assert from 'node:assert/strict';
import {gunzipSync} from 'node:zlib';
const jobId='00000000-0000-4000-8000-000000000001',generation='00000000-0000-4000-8000-000000000002';
const importId='00000000-0000-4000-8000-000000000003';
async function api(){try{return await import('../app/ap_statements/frontend/bill-upload.mjs');}catch(error){assert.fail('Streaming BILL upload module is not implemented: '+error.code);}}
async function workerApi(){try{return await import('../app/ap_statements/frontend/bill-upload-worker.mjs');}catch(error){assert.fail('BILL compression worker is not implemented: '+error.code);}}
function source(){const file=new File(['vendor,invoiceNumber,amount\nSynthetic,00042-A,138.00\n'],'synthetic.csv');file.text=()=>{throw Error('Original text must not be read');};file.arrayBuffer=()=>{throw Error('Original bytes must not be buffered');};return file;}
async function workerFactory(){const {compressBillFile}=await workerApi();return ()=>({terminate(){this.terminated=true;},postMessage({id,file}){queueMicrotask(async()=>{try{const result=await compressBillFile(file);this.onmessage?.({data:{id,type:'result',...result}});}catch(error){this.onmessage?.({data:{id,type:'error',message:error.message}});}});}});}
function client(overrides={}){const calls=[],chunks=[];let prepared=0,activated=0;return {calls,chunks,get activated(){return activated;},async request(action,payload,options={}){calls.push({action,payload,id:options.requestId});if(overrides[action])return overrides[action](payload,options);if(action==='bill_upload_begin')return {job_id:jobId,generation,checkpoint:0,state:'uploading'};if(action==='bill_upload_chunk'){chunks.push(Buffer.from(payload.data,'base64'));return {index:payload.index};}if(action==='bill_upload_finish')return {job_id:jobId,generation,checkpoint:0,state:'reading'};if(action==='bill_prepare_step'){prepared++;return {state:'prepared',generation,checkpoint:prepared,importId,recordCount:223425};}if(action==='bill_activate'){activated++;return {importId,recordCount:223425,metadata:{label:'synthetic.csv'}};}if(action==='bill_cancel')return {cancelled:true};throw Error(action);}};}

test('worker compresses a stream without whole-file text or arrayBuffer reads',async()=>{
 const {compressBillFile}=await workerApi();const file=source();const result=await compressBillFile(file);
 assert.equal(result.originalBytes,file.size);assert.equal(gunzipSync(Buffer.from(await result.blob.arrayBuffer())).toString(),'vendor,invoiceNumber,amount\nSynthetic,00042-A,138.00\n');
 await assert.rejects(compressBillFile({size:256*1024*1024+1,stream(){assert.fail('Oversized source was read');}}),/size|256|large/i);
});
test('serial import sends compressed chunks and activates only after preparation',async()=>{
 const {importBillSnapshot}=await api();const transport=client(),stages=[];
 const saved=await importBillSnapshot(transport,source(),{workerFactory:await workerFactory(),onProgress:p=>stages.push(p.stage)});
 assert.equal(saved.recordCount,223425);assert.equal(transport.activated,1);
 assert.equal(gunzipSync(Buffer.concat(transport.chunks)).toString().includes('00042-A'),true);
 assert.ok(stages.includes('preparing')&&stages.includes('uploading')&&stages.includes('checking')&&stages.includes('saving'));
 assert.ok(transport.calls.findIndex(c=>c.action==='bill_activate')>transport.calls.findIndex(c=>c.action==='bill_prepare_step'));
});

test('range handoff prepares a full import without activating it first',async()=>{
 const {importBillSnapshot}=await api();const transport=client();
 const prepared=await importBillSnapshot(transport,source(),{workerFactory:await workerFactory(),prepareOnly:true});
 assert.equal(prepared.state,'prepared');assert.equal(prepared.importId,importId);
 assert.equal(prepared.job_id,jobId);assert.equal(transport.activated,0);
 const duplicate=client({bill_upload_finish:()=>({state:'prepared',generation,checkpoint:0,duplicate:true,alreadyCurrent:true,importId,recordCount:1})});
 const reused=await importBillSnapshot(duplicate,source(),{workerFactory:await workerFactory(),prepareOnly:true});
 assert.equal(reused.state,'prepared');assert.equal(reused.job_id,jobId);assert.equal(duplicate.activated,0);
});
test('a transport retry keeps request identity and does not re-upload acknowledged chunks',async()=>{
 const {importBillSnapshot}=await api();let offline=true;const transport=client({bill_prepare_step:()=>{if(offline)throw Error('offline');return {state:'prepared',generation,checkpoint:1};}});
 let failure;try{await importBillSnapshot(transport,source(),{workerFactory:await workerFactory()});}catch(error){failure=error;}
 assert.match(failure.message,/offline/);assert.equal(transport.activated,0);offline=false;
 const saved=await failure.retry();assert.equal(saved.importId,importId);
 const prepare=transport.calls.filter(c=>c.action==='bill_prepare_step');assert.equal(prepare[0].id,prepare[1].id);
 assert.equal(transport.calls.filter(c=>c.action==='bill_upload_chunk').length,1);
});

test('failed uploads expose explicit cancellation and terminal invalid files are not offered same-file retry',async()=>{
 const {importBillSnapshot}=await api();
 for(const code of ['unavailable','bill_invalid_archive']){
  const transport=client({bill_prepare_step:()=>{throw Object.assign(Error('Rejected'),{code});}});let failure;
  try{await importBillSnapshot(transport,source(),{workerFactory:await workerFactory()});}catch(e){failure=e;}
  assert.equal(typeof failure.cancel,'function');
  assert.equal(typeof failure.retry,code==='unavailable'?'function':'undefined');
  await failure.cancel();assert.equal(transport.calls.at(-1).action,'bill_cancel');
 }
});
test('already-current duplicate does not activate and old source requires explicit consent',async()=>{
 const {importBillSnapshot}=await api();const current=client({bill_upload_finish:()=>({state:'prepared',generation,checkpoint:0,duplicate:true,alreadyCurrent:true,importId,recordCount:1})});
 const same=await importBillSnapshot(current,source(),{workerFactory:await workerFactory()});assert.equal(same.alreadyCurrent,true);assert.equal(current.activated,0);
 const older=client({bill_upload_finish:()=>({state:'prepared',generation,checkpoint:0,duplicate:true,confirmationRequired:true,importId,recordCount:1})});
 const cancelled=await importBillSnapshot(older,source(),{workerFactory:await workerFactory(),confirmRestore:async()=>false});assert.equal(cancelled.cancelled,true);assert.equal(older.activated,0);assert.ok(older.calls.some(c=>c.action==='bill_cancel'));
});
test('lost build handle restarts only after confirmation and uses the new generation',async()=>{
 const {importBillSnapshot}=await api();const next='00000000-0000-4000-8000-000000000004';let n=0,confirmed=0;
 const transport=client({bill_prepare_step:p=>{n++;if(n===1)return {state:'restart_required',generation,checkpoint:0};if(p.restart)return {state:'reading',generation:next,checkpoint:0};assert.equal(p.generation,next);return {state:'prepared',generation:next,checkpoint:1};}});
 const saved=await importBillSnapshot(transport,source(),{workerFactory:await workerFactory(),confirmRestart:async()=>{confirmed++;return true;}});
 assert.equal(saved.importId,importId);assert.equal(confirmed,1);
});
test('abort terminates worker and ignores late completion without a storage write',async()=>{
 const {prepareBillUpload}=await api();const controller=new AbortController();let instance;
 const pending=prepareBillUpload(source(),{signal:controller.signal,workerFactory:()=>instance={postMessage(p){this.id=p.id;},terminate(){this.stopped=true;}}});
 controller.abort();await assert.rejects(pending,/cancel|abort/i);assert.equal(instance.stopped,true);
 instance.onmessage?.({data:{id:instance.id,type:'result',blob:new Blob(['late']),originalBytes:1}});
});
test('abort during begin acknowledgement releases the acknowledged job',async()=>{
 const {importBillSnapshot}=await api();const controller=new AbortController();
 const transport=client({bill_upload_begin:()=>{controller.abort();return {job_id:jobId,generation,checkpoint:0,state:'uploading'};}});
 await assert.rejects(importBillSnapshot(transport,source(),{workerFactory:await workerFactory(),signal:controller.signal}),/cancel|abort/i);
 assert.ok(transport.calls.some(c=>c.action==='bill_cancel'&&c.payload.job_id===jobId));
 assert.equal(transport.activated,0);
});
