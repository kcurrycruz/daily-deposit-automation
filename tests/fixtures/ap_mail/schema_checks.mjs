import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'../../..');
let PGlite;
try{({PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite'));}
catch{({PGlite}=createRequire(resolve(root,'../../app/ap_statements/package.json'))('@electric-sql/pglite'));}
const db=new PGlite(),w=crypto.randomUUID(),other=crypto.randomUUID(),conn=crypto.randomUUID();
const q=(s,p=[])=>db.query(s,p), id=()=>crypto.randomUUID();
const call=(op,data={},request=id(),hash='a'.repeat(64),workspace=w)=>q(
 'select public.ap_mail_mutate($1,$2,$3,$4,$5) result',[op,workspace,request,hash,JSON.stringify(data)]).then(r=>r.rows[0].result);
try{
 await db.exec('create role anon;create role authenticated;create role service_role bypassrls;');
 await db.exec(readFileSync(resolve(root,'supabase/migrations/202610130001_ap_shared_workspace.sql'),'utf8'));
 await q('insert into ap_workspaces(id) values($1),($2)',[w,other]);
 await db.exec(readFileSync(resolve(root,'supabase/migrations/202611040001_ap_mail_intake.sql'),'utf8'));
 await q(`insert into ap_mail_connections(id,workspace_id,account_id,email,label_id,secret_ref,paused,cursor)
 values($1,$2,'account-1','owner@example.test','Label_1','projects/test/secrets/gmail',false,'{"phase":"baseline"}')`,[conn,w]);
 const a=id(),b=id();
 const message={message_id:'msg-1',thread_id:'thread-1',received_at:'2026-11-04T12:00:00Z',sender:'Synthetic',subject:'Statement',eligible:true};
 const receipt=(value,path)=>({id:value,message_id:'msg-1',part_path:path,filename:'synthetic.pdf',mime_type:'application/pdf',declared_size:8,attachment_id:'att-1',status:'queued',reason:null});
 const inventory={connection_id:conn,expected_generation:1,expected_version:1,expected_cursor:{phase:'baseline'},
                  messages:[message],receipts:[receipt(a,'0.1'),receipt(b,'0.2')],next_cursor:{phase:'live',history_id:'999'}};
 const request=id();
 const first=await call('inventory',inventory,request);
 assert.deepEqual(await call('inventory',inventory,request),first);
 assert.equal((await q('select count(*)::int n from ap_mail_jobs')).rows[0].n,2);
 assert.equal((await q('select count(*)::int n from ap_mail_outbox')).rows[0].n,2);
 const read=(op,data={})=>q('select ap_mail_read($1,$2,$3) value',[op,w,JSON.stringify(data)]).then(r=>r.rows[0].value);
 const sourceContext=await read('source_context');
 assert.equal(sourceContext.home.id,w);assert.equal(sourceContext.source,null);
 assert.deepEqual(sourceContext.mappings,{});assert.deepEqual(sourceContext.mappingVersions,{});
 assert.equal((await read('status')).counts.queued,2);
 assert.equal((await read('receipts',{limit:1,cursor:null})).items.length,1);
 assert.equal((await read('outbox',{limit:100,cursor:null})).items.length,2);
 await assert.rejects(call('reconcile',{limit:100,unexpected:true}),/invalid/);
 await assert.rejects(call('inventory',inventory),/conflict/);
 await assert.rejects(call('inventory',inventory,request,'b'.repeat(64)),/conflict/);
 const current=(await q('select * from ap_mail_connections where id=$1',[conn])).rows[0];
 await assert.rejects(call('inventory',{...inventory,expected_version:null,expected_generation:null,expected_cursor:current.cursor}),/conflict|invalid/);
 const next={...inventory,expected_version:current.version,expected_cursor:current.cursor,
             receipts:[{...receipt(id(),'0.9'),declared_size:0}],next_cursor:{phase:'live',history_id:'1000'}};
 await assert.rejects(call('inventory',next),/invalid|check/);
 assert.equal((await q('select cursor from ap_mail_connections where id=$1',[conn])).rows[0].cursor.history_id,'999');
 const attentionInventory={...inventory,expected_version:current.version,expected_cursor:current.cursor,
  messages:[{...message,message_id:'bad',received_at:null,error_code:'unreadable'}],receipts:[],next_cursor:current.cursor};
 await call('inventory',attentionInventory);
 assert.equal((await read('messages',{connection_id:conn,ids:['bad']})).items[0].error_code,'unreadable');
 assert.equal((await read('status')).counts.message_attention,1);
 await call('sync_error',{connection_id:conn,expected_generation:1,reason:'auth'});
 assert.equal((await read('status')).connection.error,'auth');
 const claimed=await call('claim',{job_id:a,dispatch_generation:1});
 const fence=claimed.claim;
 assert.equal(fence.receipt_id,a);assert.equal(fence.mode,'extract');
 assert.equal((await call('claim',{job_id:b,dispatch_generation:1})).claim,null);
 assert.equal((await call('claim',{job_id:a,dispatch_generation:1})).claim,null);
 assert.equal((await q('select attempts from ap_mail_jobs where id=$1',[a])).rows[0].attempts,1);
 const renewed=await call('heartbeat',{claim:fence});assert.ok(renewed.claim.lease_until);
 assert.equal((await call('dispatch_missing',{job_id:a,dispatch_generation:1})).requeued,false);
 await call('outbox_sent',{job_id:b,dispatch_generation:1,task_name:'projects/test/locations/us-east1/queues/q/tasks/test'});
 assert.equal((await read('outbox',{limit:100,state:'sent'})).items.length,1);
 await call('dispatch_checkpoint',{connection_id:conn,expected_generation:1,cursor:{job_id:b,dispatch_generation:1}});
 assert.equal((await read('connection',{connection_id:conn})).connection.dispatch_cursor.job_id,b);
 await assert.rejects(call('record_original',{claim:fence,sha256:'a'.repeat(64),object_key:w+'/pdf/'+'a'.repeat(64)+'.pdf'}),/invalid/);
 await assert.rejects(call('record_original',{claim:{...fence,slot_generation:999},sha256:'a'.repeat(64),object_key:w+'/pdf/'+'a'.repeat(64)+'.pdf',size:8}),/stale_claim/);
 await call('record_original',{claim:fence,sha256:'a'.repeat(64),object_key:w+'/pdf/'+'a'.repeat(64)+'.pdf',size:8});
 await assert.rejects(call('record_original',{claim:fence,sha256:'b'.repeat(64),object_key:w+'/pdf/'+'b'.repeat(64)+'.pdf',size:8}),/conflict/);
 await assert.rejects(call('save_extraction',{claim:fence,doc:{id:id(),confirmed:true,rows:[]},parser_version:'test'}),/invalid/);
 // Expire via test-only SQL; runtime cannot provide its own clock.
 await q("update ap_mail_jobs set lease_until=now()-interval '1 second' where id=$1",[a]);
 await q("update ap_mail_processor_slots set lease_until=now()-interval '1 second' where workspace_id=$1",[w]);
 await assert.rejects(call('heartbeat',{claim:fence}),/stale_claim/);
 await call('reconcile',{limit:100});
 const repaired=(await q('select * from ap_mail_jobs where id=$1',[a])).rows[0];
 assert.equal(repaired.dispatch_generation,2);assert.equal(repaired.attempts,1);
 const successor=(await call('claim',{job_id:a,dispatch_generation:2})).claim;
 assert.ok(successor.lease_generation>fence.lease_generation);
 await assert.rejects(call('needs_attention',{claim:fence,reason:'unreadable'}),/stale_claim/);
 await call('needs_attention',{claim:successor,reason:'unreadable'});
 assert.equal((await q('select status from ap_mail_receipts where id=$1',[a])).rows[0].status,'needs_attention');
 const receiptVersion=(await q('select version from ap_mail_receipts where id=$1',[a])).rows[0].version;
 const retryRequest=id();
 await call('retry',{receipt_id:a,expected_version:receiptVersion},retryRequest);
 await call('retry',{receipt_id:a,expected_version:receiptVersion},retryRequest);
 const retried=(await q('select * from ap_mail_jobs where id=$1',[a])).rows[0];
 assert.equal(retried.attempts,0);assert.equal(retried.dispatch_generation,3);
 assert.equal((await call('dispatch_missing',{job_id:a,dispatch_generation:3})).requeued,true);
 assert.equal((await call('dispatch_missing',{job_id:a,dispatch_generation:3})).requeued,false);
 // Three failed real claims exhaust; transport duplicates do not add attempts.
 for(let attempt=1;attempt<=3;attempt++){
  const f=(await call('claim',{job_id:a,dispatch_generation:4})).claim;
  assert.ok(f);await call('release_retry',{claim:f,reason:'unavailable',delay_seconds:0});
 }
 assert.equal((await call('claim',{job_id:a,dispatch_generation:4})).claim,null);
 assert.equal((await q('select status from ap_mail_receipts where id=$1',[a])).rows[0].status,'needs_attention');
 const cv=(await q('select version from ap_mail_connections where id=$1',[conn])).rows[0].version;
 await call('pause',{connection_id:conn,expected_version:cv,paused:true});
 assert.equal((await call('claim',{job_id:b,dispatch_generation:1})).claim,null);
 await assert.rejects(call('retry',{receipt_id:b,expected_version:1},id(),'a'.repeat(64),other),/not_found/);
 const paused=(await q('select version from ap_mail_connections where id=$1',[conn])).rows[0].version;
 await call('pause',{connection_id:conn,expected_version:paused,paused:false});
 const oldAccountClaim=(await call('claim',{job_id:b,dispatch_generation:1})).claim;
 await q("update ap_mail_connections set generation=generation+1,account_id='account-2' where id=$1",[conn]);
 await assert.rejects(call('heartbeat',{claim:oldAccountClaim}),/stale_claim/);
 await call('reconcile',{limit:100});
 assert.equal((await q('select status from ap_mail_receipts where id=$1',[b])).rows[0].status,'needs_attention');
 const oldReceipt=(await q('select * from ap_mail_receipts where id=$1',[b])).rows[0];
 await assert.rejects(call('retry',{receipt_id:b,expected_version:oldReceipt.version}),/wrong_account/);
 const incompatible=(await q("update ap_mail_jobs set state='queued',connection_generation=2,attempts=0,lease_until='-infinity' where id=$1 returning dispatch_generation",[b])).rows[0];
 const refused=await call('claim',{job_id:b,dispatch_generation:incompatible.dispatch_generation});
 assert.equal(refused.claim,null);assert.equal(refused.retry,false);
 for(const role of ['anon','authenticated']){
  await db.exec('set role '+role);
  await assert.rejects(q('select * from ap_mail_receipts'),/permission denied/);
  await assert.rejects(call('reconcile',{limit:100}),/permission denied/);
  await db.exec('reset role');
 }
 assert.equal((await q('select mail_schema_version from ap_workspaces where id=$1',[w])).rows[0].mail_schema_version,1);
 assert.equal((await q("select count(*)::int n from ap_mail_attempts where event='claimed' and job_id=$1",[a])).rows[0].n,5);
 console.log('Mail SQL behavior checks passed: atomic inventory, outbox, slot, fencing, exhaustion, controls, ACL.');
}catch(error){throw new Error([error.message,error.where,error.position].filter(Boolean).join(' | '));}
finally{await db.close();}
