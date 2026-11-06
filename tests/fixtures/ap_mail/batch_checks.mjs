import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'../../..');
const {PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite');
const db=new PGlite(),q=(sql,params=[])=>db.query(sql,params),id=n=>`00000000-0000-4000-8000-${n.toString(16).padStart(12,'0')}`;
const w=id(1),other=id(2),conn=id(3),old=id(4),elsewhere=id(5);
try{
 await db.exec('create role anon;create role authenticated;create role service_role bypassrls;');
 for(const name of ['202610130001_ap_shared_workspace.sql','202611040001_ap_mail_intake.sql'])await db.exec(readFileSync(resolve(root,'supabase/migrations',name),'utf8'));
 await q('insert into ap_workspaces(id) values($1),($2)',[w,other]);
 for(const [c,workspace,active] of [[conn,w,true],[old,w,false],[elsewhere,other,true]])await q(
  `insert into ap_mail_connections(id,workspace_id,account_id,email,label_id,secret_ref,paused,active)
   values($1,$2,$4,'synthetic@example.test','Label_1','github:synthetic/repo:AP_MAIL_GMAIL_GRANT',false,$3)`,[c,workspace,active,'account-'+c]);
 async function seed(n,{c=conn,workspace=w,state='queued',generation=1,attempts=0,outbox='pending',futureJob=false,futureOutbox=false,wrongAccount=false}={}){
  const account=wrongAccount?'old-account':'account-'+c;
  await q(`insert into ap_mail_messages(workspace_id,connection_id,account_id,message_id,thread_id,eligible) values($1,$2,$3,$4,$4,true)`,[workspace,c,account,'m'+n]);
  await q(`insert into ap_mail_receipts(id,workspace_id,connection_id,account_id,message_id,part_path,filename,mime_type,declared_size)
   values($1,$2,$3,$4,$5,'0','synthetic.pdf','application/pdf',8)`,[id(n),workspace,c,account,'m'+n]);
  await q(`insert into ap_mail_jobs(id,workspace_id,receipt_id,connection_id,connection_generation,state,attempts,next_retry_at)
   values($1,$2,$1,$3,$4,$5,$6,now()+$7::interval)`,[id(n),workspace,c,generation,state,attempts,futureJob?'1 hour':'-1 hour']);
  await q(`insert into ap_mail_outbox(workspace_id,job_id,dispatch_generation,state,next_attempt_at)
   values($1,$2,1,$3,now()+$4::interval)`,[workspace,id(n),outbox,futureOutbox?'1 hour':'-1 hour']);
 }
 await seed(10);await seed(20);await seed(30,{outbox:'sent'});await seed(40,{futureJob:true});await seed(50,{futureOutbox:true});
 await seed(60,{attempts:3});await seed(70,{state:'running'});await seed(80,{state:'done'});await seed(90,{state:'attention'});
 await seed(100,{generation:2});await seed(110,{c:old});await seed(120,{workspace:other,c:elsewhere});await seed(130,{wrongAccount:true});
 await q('insert into ap_mail_outbox(workspace_id,job_id,dispatch_generation) values($1,$2,2)',[w,id(10)]);
 const before=JSON.stringify((await q('select * from ap_mail_jobs order by id')).rows);
 const migration=resolve(root,'supabase/migrations/202611060001_ap_mail_batch.sql');
 if(existsSync(migration))await db.exec(readFileSync(migration,'utf8'));
 const read=(workspace=w,c=conn,generation=1,cursor=null,limit=25)=>q(
  'select public.ap_mail_batch_pending($1,$2,$3,$4,$5) result',[workspace,c,generation,cursor,limit]).then(r=>r.rows[0].result);
 const page=await read();assert.deepEqual(page.items.map(x=>x.job_id),[id(10),id(20)]);assert.equal(page.nextCursor,null);
 assert.deepEqual(Object.keys(page.items[0]).sort(),['dispatch_generation','job_id','mode','receipt_id']);
 const first=await read(w,conn,1,null,1);assert.equal(first.nextCursor,id(10));
 assert.deepEqual((await read(w,conn,1,first.nextCursor,1)).items.map(x=>x.job_id),[id(20)]);
 assert.deepEqual((await read(w,conn,1,id(20))).items,[]);
 for(const limit of [null,0,101])await assert.rejects(read(w,conn,1,null,limit),/invalid/);
 for(const generation of [null,0,2])await assert.rejects(read(w,conn,generation),/invalid|conflict/);
 await assert.rejects(read(other,conn),/not_found|denied/);
 await assert.rejects(read(w,elsewhere),/not_found|denied/);
 await q('update ap_mail_connections set paused=true where id=$1',[conn]);assert.deepEqual((await read()).items,[]);
 await q('update ap_mail_connections set paused=false,active=false where id=$1',[conn]);assert.deepEqual((await read()).items,[]);
 await q('update ap_mail_connections set active=true where id=$1',[conn]);
 const signature='public.ap_mail_batch_pending(uuid,uuid,bigint,uuid,integer)';
 for(const role of ['anon','authenticated']){
  assert.equal((await q('select has_function_privilege($1,$2,$3) allowed',[role,signature,'EXECUTE'])).rows[0].allowed,false);
  await db.exec('set role '+role);await assert.rejects(read(),/permission denied/);await db.exec('reset role');
 }
 assert.equal((await q('select has_function_privilege($1,$2,$3) allowed',['service_role',signature,'EXECUTE'])).rows[0].allowed,true);
 await db.exec('set role service_role');assert.equal((await read()).items.length,2);await db.exec('reset role');
 assert.equal(JSON.stringify((await q('select * from ap_mail_jobs order by id')).rows),before);
 assert.equal((await q('select count(*)::int n from ap_mail_attempts')).rows[0].n,0);
 console.log('Mail batch SQL checks passed: exact connection, due jobs, pagination, ACL, no mutation.');
}catch(error){console.error(error.message);process.exitCode=1;}finally{await db.close();}
