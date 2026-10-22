import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'../../..');
let PGlite;
try{({PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite'));}
catch{({PGlite}=createRequire(resolve(root,'.superpowers/sdd/2026-10-13-ap-shared-workspace/sql-runtime/package.json'))('@electric-sql/pglite'));}
const db=new PGlite(),w='00000000-0000-4000-8000-000000000001',other='00000000-0000-4000-8000-000000000002';
const iid=crypto.randomUUID(),sid=crypto.randomUUID(),nonce=crypto.randomUUID(),q=(s,p=[])=>db.query(s,p);
const call=(op,data,id=crypto.randomUUID(),hash='f'.repeat(64),workspace=w)=>q(
  'select public.ap_duplicate_mutate($1,$2,$3,$4,$5) value',[op,workspace,id,hash,JSON.stringify(data)]).then(r=>r.rows[0].value);
const mf=()=>({format:'bill-duplicates-v1',ruleVersion:'bill-duplicates-v1',sourceDigest:'a'.repeat(64),importId:iid,
  key:w+'/bill-duplicates/v1/'+iid+'/bill-duplicates-v1/'+'b'.repeat(64)+'.sqlite.gz',
  hash:'b'.repeat(64),bytes:50,expandedHash:'c'.repeat(64),expandedBytes:4096,findingCount:1,recordCount:2});
try{
 await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create schema storage;create table storage.objects(bucket_id text,name text,metadata jsonb);');
 for(const file of ['202610130001_ap_shared_workspace.sql','202610190001_ap_bill_snapshots.sql','202610220001_ap_duplicate_bills.sql'])
   await db.exec(readFileSync(resolve(root,'supabase/migrations',file),'utf8'));
 await q('insert into ap_workspaces(id) values($1),($2)',[w,other]);
 await q('insert into ap_bill_imports(id,workspace_id,file_hash,original_object_key,metadata,record_count,state) values($1,$2,$3,$4,$5,2,$6)',
   [iid,w,'a'.repeat(64),w+'/csv/'+'a'.repeat(64)+'.csv','{}','ready']);
 await q('update ap_workspaces set active_import_id=$1 where id=$2',[iid,w]);
 const ensure={scan_id:sid,import_id:iid,expected_import_version:1,source_digest:'a'.repeat(64),rule_version:'bill-duplicates-v1'};
 let scan=await call('ensure',ensure);
 assert.equal(scan.state,'pending');
 assert.equal((await call('ensure',ensure)).id,sid);
 assert.equal((await q('select count(*)::int n from ap_duplicate_scans')).rows[0].n,1);
 scan=await call('claim',{scan_id:sid,session_nonce:nonce});
 await assert.rejects(call('claim',{scan_id:sid,session_nonce:crypto.randomUUID()}),/duplicate_conflict/);
 await assert.rejects(call('ensure',{...ensure,expected_import_version:0}),/duplicate_conflict/);
 await assert.rejects(call('checkpoint',{scan_id:sid,session_nonce:nonce,generation:scan.generation,
   expected_checkpoint:0,next_checkpoint:2,phase:'reading',progress:{recordsRead:2,probes:0}}),/duplicate_conflict/);
 const lostGeneration=scan.generation;
 scan=await call('fail',{scan_id:sid,session_nonce:nonce,generation:scan.generation,expected_checkpoint:0,error_code:'duplicate_restart'});
 assert.equal(scan.state,'restart_required');
 scan=await call('restart',{scan_id:sid,session_nonce:nonce,expected_generation:lostGeneration});
 assert.notEqual(scan.generation,lostGeneration);assert.equal(scan.checkpoint,0);
 await assert.rejects(call('checkpoint',{scan_id:sid,session_nonce:nonce,generation:lostGeneration,
   expected_checkpoint:0,next_checkpoint:1,phase:'reading',progress:{recordsRead:2,probes:0}}),/duplicate_conflict/);
 scan=await call('checkpoint',{scan_id:sid,session_nonce:nonce,generation:scan.generation,
   expected_checkpoint:0,next_checkpoint:1,phase:'packaging',progress:{recordsRead:2,probes:20}});
 // Reservations must account for competing imports, not only detector jobs.
 const billJob=crypto.randomUUID();
 await q('insert into ap_bill_jobs(id,workspace_id,session_nonce,expected_import_version,metadata) values($1,$2,$3,1,$4)',
   [billJob,w,nonce,'{}']);
 const billReserve=(n)=>q('select public.ap_bill_quota_reserve($1,$2,$3,$4) value',
   [w,crypto.randomUUID(),'d'.repeat(64),JSON.stringify({job_id:billJob,session_nonce:nonce,bucket:'private',requested_bytes:n,budget_bytes:1000})]);
 await call('reserve',{scan_id:sid,session_nonce:nonce,bucket:'private',requested_bytes:600,budget_bytes:1000});
 await assert.rejects(billReserve(401),/bill_quota/);
 await billReserve(400);
 await assert.rejects(call('reserve',{scan_id:sid,session_nonce:nonce,bucket:'private',requested_bytes:601,budget_bytes:1000}),/duplicate_quota/);
 scan=await call('publish',{scan_id:sid,session_nonce:nonce,generation:scan.generation,expected_checkpoint:1,expected_import_version:1,manifest:mf()});
 assert.equal(scan.state,'ready');
 const review={scan_id:sid,import_id:iid,expected_import_version:1,finding_key:'e'.repeat(64),
   verified_key:'e'.repeat(64),expected_review_version:0,decision:'not_duplicate',initials:'KC',note:''};
 const request=crypto.randomUUID(),saved=await call('review',review,request);
 assert.equal(saved.review.version,1);assert.equal(saved.reviewRevision,1);
 assert.equal(saved.review.initials,'KC');assert.ok(saved.review.at);
 assert.deepEqual(await call('review',review,request),saved);
 assert.equal((await q('select count(*)::int n from ap_duplicate_review_events')).rows[0].n,1);
 await assert.rejects(call('review',{...review,note:'changed'},request,'c'.repeat(64)),/request_conflict/);
 await assert.rejects(call('review',review),/duplicate_conflict/);
 await assert.rejects(call('review',{...review,expected_review_version:1,verified_key:'0'.repeat(64)}),/duplicate_conflict/);
 const reopened=await call('review',{...review,expected_review_version:1,decision:'unreviewed'});
 assert.equal(reopened.review.version,2);assert.equal(reopened.reviewRevision,2);
 await assert.rejects(call('review',{...review,expected_review_version:2,initials:''}),/initials/);
 await assert.rejects(call('review',{...review,expected_review_version:2},undefined,undefined,other),/duplicate_conflict/);
 await q('update ap_workspaces set active_import_id=null where id=$1',[w]);
 await q('update ap_workspaces set active_import_id=$1 where id=$2',[iid,w]);
 await assert.rejects(call('review',{...review,expected_review_version:2}),/duplicate_conflict/);
 const retained=await call('review',{...review,expected_import_version:3,expected_review_version:2,decision:'confirmed_duplicate'});
 assert.equal(retained.review.version,3);
 await assert.rejects(q("update ap_duplicate_scans set manifest='{}' where id=$1",[sid]),/immutable/);
 await assert.rejects(q('delete from ap_duplicate_review_events'),/immutable/);
 assert.equal((await q('select count(*)::int n from ap_bill_records')).rows[0].n,0);
 assert.equal((await q('select count(*)::int n from ap_completion_events')).rows[0].n,0);
 // Existing BILL operations still work after the additive quota rewrite.
 await q("update ap_bill_jobs set state='abandoned',reserved_bytes=0");
 const oldCall=(op,data)=>q('select public.ap_bill_mutate($1,$2,$3,$4,$5) value',
   [op,w,crypto.randomUUID(),'f'.repeat(64),JSON.stringify(data)]).then(r=>r.rows[0].value);
 const newBillJob=crypto.randomUUID(),oldJob=await oldCall('job_begin',{job_id:newBillJob,session_nonce:nonce,filename:'synthetic.csv',compressed_size:20,as_of:''});
 assert.equal(oldJob.expected_import_version,3);
 await oldCall('job_chunk',{job_id:newBillJob,session_nonce:nonce,index:0,size:20,chunk_hash:'c'.repeat(64)});
 await oldCall('job_uploaded',{job_id:newBillJob,session_nonce:nonce,original_hash:'d'.repeat(64),original_bytes:100,
   original_archive:{key:w+'/bills/v2/'+'d'.repeat(64)+'/'+'c'.repeat(64)+'.csv.gz',hash:'c'.repeat(64),bytes:20}});
 const oldProgress=await oldCall('job_checkpoint',{job_id:newBillJob,session_nonce:nonce,generation:oldJob.generation,
   expected_checkpoint:0,next_checkpoint:1,state:'reading',counts:{}});
 assert.equal(oldProgress.checkpoint,1);
 await oldCall('job_abandon',{job_id:newBillJob,session_nonce:nonce,generation:oldJob.generation});
 for(const role of ['anon','authenticated']){
   await db.exec('set role '+role);
   await assert.rejects(q('select * from ap_duplicate_reviews'),/permission denied/);
   await assert.rejects(call('ensure',ensure),/permission denied/);
   await db.exec('reset role');
 }
 console.log('Duplicate bill SQL checks passed');
}finally{await db.close();}
