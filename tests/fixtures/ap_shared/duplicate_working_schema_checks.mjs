import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
const root=resolve(import.meta.dirname,'../../..');
let PGlite;
try{({PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite'));}
catch{({PGlite}=createRequire(resolve(root,'.superpowers/sdd/2026-10-13-ap-shared-workspace/sql-runtime/package.json'))('@electric-sql/pglite'));}
const db=new PGlite(),w=crypto.randomUUID(),nonce=crypto.randomUUID(),sourceId=crypto.randomUUID();
const q=(s,p=[])=>db.query(s,p);
const hash=value=>createHash('sha256').update(JSON.stringify(sort(value))).digest('hex');
const sort=v=>Array.isArray(v)?v.map(sort):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])])):v;
const call=(op,data,id=crypto.randomUUID())=>q('select public.ap_bill_working_mutate($1,$2,$3,$4,$5) value',[op,w,id,hash({operation:op,data}),JSON.stringify(data)]).then(r=>r.rows[0].value);
const home=async()=> (await q('select * from ap_workspaces where id=$1',[w])).rows[0];
const policy={version:'ap-active-range-v1',mode:'last_12_months',asOfDate:'2026-10-30',cutoffDate:'2025-10-30'};
const begin=async(extra={})=>{
 const h=await home();return call('begin',{job_id:crypto.randomUUID(),session_nonce:nonce,source_import_id:sourceId,
 expected_import_version:h.import_version,expected_working_version:h.working_set_version,
 protection_epoch:h.bill_protection_epoch,protection_digest:'b'.repeat(64),policy,...extra});
};
const data=job=>({job_id:job.job_id,session_nonce:nonce,generation:job.generation});
const manifest=(job,activeCount=1)=>{
 const source={importId:sourceId,sourceDigest:'a'.repeat(64),recordCount:2};
 const workingDigest=hash({source,policy:job.policy,protectionDigest:'b'.repeat(64),trainingVersion:'vendor-history-v1'});
 const archive=letter=>({key:`${w}/bill-working/v1/${workingDigest}/${letter.repeat(64)}.sqlite.gz`,hash:letter.repeat(64),bytes:100,expandedHash:'e'.repeat(64),expandedBytes:1000});
 return {format:'ap-bill-working-v1',workingSetId:crypto.randomUUID(),workingDigest,source,policy:job.policy,
 protectionDigest:'b'.repeat(64),trainingVersion:'vendor-history-v1',fullRecordCount:2,activeCount,archivedCount:2-activeCount,
 retainedReasonCounts:activeCount?{recent:activeCount}:{},vendorDigest:'f'.repeat(64),archiveVendorDigest:'f'.repeat(64),mappingDigest:'9'.repeat(64),indexArchive:archive('c'),contextArchive:archive('d')};
};
const stage=async(job,mf=manifest(job))=>{
 await call('checkpoint',{...data(job),expected_checkpoint:0,next_checkpoint:1,state:'packaging',progress:{recordsRead:2}});
 return call('stage',{...data(job),expected_checkpoint:1,manifest:mf});
};
const activate=job=>call('activate',data(job));
try{
 await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create schema storage;create table storage.objects(bucket_id text,name text,metadata jsonb);');
 for(const name of ['202610130001_ap_shared_workspace.sql','202610190001_ap_bill_snapshots.sql','202610220001_ap_duplicate_bills.sql','202610230001_ap_statement_rereview.sql','202610260001_ap_duplicate_rules_v2.sql','202610280001_ap_duplicate_vendor_rules_v3.sql','202610300001_ap_bill_working_sets.sql','202610300002_ap_duplicate_working_scope.sql'])await db.exec(readFileSync(resolve(root,'supabase/migrations',name),'utf8'));
 await q('insert into ap_workspaces(id) values($1)',[w]);
 await q("insert into ap_bill_imports(id,workspace_id,file_hash,original_object_key,metadata,record_count,state) values($1,$2,$3,$4,'{}',2,'ready')",[sourceId,w,'a'.repeat(64),w+'/csv/'+'a'.repeat(64)+'.csv']);
 await q('update ap_workspaces set active_import_id=$1 where id=$2',[sourceId,w]);
 const first=await begin(),mf=manifest(first);await stage(first,mf);await activate(first);
 const dup=(op,data,id=crypto.randomUUID())=>q('select public.ap_duplicate_mutate($1,$2,$3,$4,$5) value',[op,w,id,hash({operation:op,data}),JSON.stringify(data)]).then(r=>r.rows[0].value);
 const h=await home(),sid=crypto.randomUUID();
 const ensure={scan_id:sid,import_id:sourceId,expected_import_version:h.import_version,source_digest:mf.workingDigest,rule_version:'bill-duplicates-v4',working_set_id:mf.workingSetId,expected_working_version:h.working_set_version};
 await assert.rejects(dup('ensure',{...ensure,expected_working_version:0}),/duplicate_conflict/);
 await assert.rejects(dup('ensure',{...ensure,source_digest:'0'.repeat(64)}),/duplicate_conflict/);
 await assert.rejects(dup('ensure',{...ensure,working_set_id:crypto.randomUUID()}),/duplicate_conflict/);
 const pending=await dup('ensure',ensure);assert.equal(pending.working_set_id,mf.workingSetId);
 const claim=await dup('claim',{scan_id:sid,session_nonce:nonce});
 const job={scan_id:sid,session_nonce:nonce,generation:claim.generation,expected_checkpoint:0};
 await dup('checkpoint',{...job,next_checkpoint:1,phase:'packaging',progress:{recordsRead:1,probes:0}});
 const result={format:'bill-duplicates-v3',ruleVersion:'bill-duplicates-v4',sourceDigest:mf.workingDigest,importId:sourceId,
 workingSetId:mf.workingSetId,workingDigest:mf.workingDigest,workingVersion:h.working_set_version,fullSourceDigest:'a'.repeat(64),fullRecordCount:2,mappingDigest:mf.mappingDigest,
 key:`${w}/bill-duplicates/v3/${sourceId}/bill-duplicates-v4/${'7'.repeat(64)}.sqlite.gz`,hash:'7'.repeat(64),bytes:100,expandedHash:'8'.repeat(64),expandedBytes:1000,findingCount:1,recordCount:1};
 const publish={...job,expected_checkpoint:1,expected_import_version:h.import_version,manifest:result};
 for(const [field,value] of [['recordCount',2],['mappingDigest','0'.repeat(64)],['workingSetId',crypto.randomUUID()],['workingVersion',0],['format','bill-duplicates-v2']])await assert.rejects(dup('publish',{...publish,manifest:{...result,[field]:value}}),/duplicate_invalid_source/);
 const ready=await dup('publish',publish);assert.equal(ready.state,'ready');
 await assert.rejects(q('update ap_duplicate_scans set manifest=null where id=$1',[sid]),/immutable_duplicate_scan/);
 const review={scan_id:sid,import_id:sourceId,expected_import_version:h.import_version,working_set_id:mf.workingSetId,expected_working_version:h.working_set_version,finding_key:'1'.repeat(64),verified_key:'1'.repeat(64),expected_review_version:0,decision:'confirmed_duplicate',initials:'KC',note:'Synthetic'};
 await assert.rejects(dup('review',{...review,expected_working_version:0}),/duplicate_conflict/);
 const req=crypto.randomUUID(),ack=await dup('review',review,req);assert.equal(ack.review.reviewedWorkingSetId,mf.workingSetId);
 assert.deepEqual(await dup('review',review,req),ack);assert.equal((await home()).bill_protection_epoch,h.bill_protection_epoch+1);
 await assert.rejects(dup('ensure',ensure),/duplicate_conflict/);
 const next=await begin({policy:{...policy,mode:'all',cutoffDate:''}}),nextMf=manifest(next,2);await stage(next,nextMf);await activate(next);
 const fresh=await home();
 await assert.rejects(dup('review',{...review,expected_review_version:1}),/duplicate_conflict/);
 const sid2=crypto.randomUUID(),pending2=await dup('ensure',{...ensure,scan_id:sid2,working_set_id:nextMf.workingSetId,source_digest:nextMf.workingDigest,expected_working_version:fresh.working_set_version});
 assert.equal(pending2.id,sid2);assert.equal((await q('select count(*) n from ap_duplicate_scans where workspace_id=$1',[w])).rows[0].n,2);
 assert.equal((await q('select count(*) n from ap_duplicate_review_events where workspace_id=$1',[w])).rows[0].n,1);
 assert.equal((await q("select has_function_privilege('anon','public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)','execute') ok")).rows[0].ok,false);
 console.log('Scoped duplicate SQL checks passed');
}catch(error){console.error(error.message);process.exitCode=1;}finally{await db.close();}
