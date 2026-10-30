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
 for(const name of ['202610130001_ap_shared_workspace.sql','202610190001_ap_bill_snapshots.sql','202610220001_ap_duplicate_bills.sql','202610230001_ap_statement_rereview.sql','202610260001_ap_duplicate_rules_v2.sql','202610280001_ap_duplicate_vendor_rules_v3.sql','202610300001_ap_bill_working_sets.sql'])await db.exec(readFileSync(resolve(root,'supabase/migrations',name),'utf8'));
 await q('insert into ap_workspaces(id) values($1)',[w]);
 await q("insert into ap_bill_imports(id,workspace_id,file_hash,original_object_key,metadata,record_count,state) values($1,$2,$3,$4,'{}',2,'ready')",[sourceId,w,'a'.repeat(64),w+'/csv/'+'a'.repeat(64)+'.csv']);
 await q('update ap_workspaces set active_import_id=$1 where id=$2',[sourceId,w]);
 const first=await begin(),mf=manifest(first);
 await assert.rejects(begin(),/bill_conflict/);
 await assert.rejects(call('checkpoint',{...data(first),session_nonce:crypto.randomUUID(),expected_checkpoint:0,next_checkpoint:1,state:'packaging'}),/bill_conflict/);
 await assert.rejects(call('checkpoint',{...data(first),generation:crypto.randomUUID(),expected_checkpoint:0,next_checkpoint:1,state:'packaging'}),/bill_conflict/);
 await assert.rejects(call('checkpoint',{...data(first),expected_checkpoint:1,next_checkpoint:2,state:'packaging'}),/bill_conflict/);
 await q('insert into storage.objects values($1,$2,$3)',['private','synthetic',JSON.stringify({size:900})]);
 await assert.rejects(call('reserve',{...data(first),bucket:'private',requested_bytes:101,budget_bytes:1000}),/bill_quota/);
 assert.equal((await call('reserve',{...data(first),bucket:'private',requested_bytes:50,budget_bytes:1000})).reserved_bytes,50);
 await assert.rejects(activate(first),/bill_incomplete/);
 const staged=await stage(first,mf);
 assert.equal(staged.working_set_id,mf.workingSetId);
 const request=crypto.randomUUID(),a=await call('activate',data(first),request);
 assert.deepEqual(await call('activate',data(first),request),a);
 await assert.rejects(call('cancel',data(first),request),/request_conflict/);
 assert.equal(a.working_set_id,mf.workingSetId);assert.equal((await home()).working_set_version,1);
 assert.equal((await home()).working_protection_epoch,(await home()).bill_protection_epoch);
 assert.equal((await q('select reserved_bytes from ap_bill_working_jobs where id=$1',[first.job_id])).rows[0].reserved_bytes,0);
 await assert.rejects(q('update ap_bill_working_sets set active_count=2'),/immutable/);
 assert.equal((await q('select count(*)::int n from ap_bill_imports')).rows[0].n,1);
 const empty=await begin({policy:{...policy,asOfDate:'2026-10-31',cutoffDate:'2025-10-31'}});
 const emptyManifest=manifest(empty,0);
 await call('checkpoint',{...data(empty),expected_checkpoint:0,next_checkpoint:1,state:'packaging'});
 for(const field of ['bytes','expandedBytes']){
  const bad=structuredClone(emptyManifest);delete bad.contextArchive[field];
  await assert.rejects(call('stage',{...data(empty),expected_checkpoint:1,manifest:bad}),/bill_incomplete/);
 }
 const badSource=structuredClone(emptyManifest);badSource.source.importId=crypto.randomUUID();
 await assert.rejects(call('stage',{...data(empty),expected_checkpoint:1,manifest:badSource}),/bill_incomplete/);
 const badDirectory=structuredClone(emptyManifest);delete badDirectory.archiveVendorDigest;
 await assert.rejects(call('stage',{...data(empty),expected_checkpoint:1,manifest:badDirectory}),/bill_incomplete/);
 await call('stage',{...data(empty),expected_checkpoint:1,manifest:emptyManifest});await activate(empty);
 assert.equal((await q('select active_count from ap_bill_working_sets where id=(select active_working_set_id from ap_workspaces where id=$1)',[w])).rows[0].active_count,0);
 const conflict=await begin();await stage(conflict);
 const before=(await home()).bill_protection_epoch;
 await q('insert into ap_vendor_mappings(workspace_id,vendor,bill_vendor) values($1,$2,$3)',[w,'Synthetic','Synthetic']);
 assert.equal(Number((await home()).bill_protection_epoch),Number(before)+1);
 await assert.rejects(activate(conflict),/bill_conflict/);
 await call('cancel',data(conflict));
 const rollbackEpoch=(await home()).bill_protection_epoch;
 await db.exec('begin');await q("update ap_vendor_mappings set bill_vendor='Changed' where workspace_id=$1",[w]);await db.exec('rollback');
 assert.equal((await home()).bill_protection_epoch,rollbackEpoch);
 const reusable=await begin();const again=await stage(reusable,mf);
 assert.equal(again.working_set_id,mf.workingSetId);await activate(reusable);
 const other=crypto.randomUUID();await q("insert into ap_bill_imports(id,workspace_id,file_hash,original_object_key,metadata,record_count,state) values($1,$2,$3,$4,'{}',1,'ready')",[other,w,'c'.repeat(64),w+'/csv/'+'c'.repeat(64)+'.csv']);
 await q('update ap_workspaces set active_import_id=$1 where id=$2',[other,w]);
 assert.equal((await home()).active_working_set_id,null);
 assert.equal((await home()).working_protection_epoch,null);
 await assert.rejects(begin(),/bill_conflict/);
 // A prepared full import and its range become active together, never in stages.
 const upload=crypto.randomUUID(),beforeNew=await home();
 await q("insert into ap_bill_jobs(id,workspace_id,session_nonce,expected_import_version,metadata,state,import_id) values($1,$2,$3,$4,'{}','prepared',$5)",[upload,w,nonce,beforeNew.import_version,sourceId]);
 const uploaded=await begin({upload_job_id:upload});await stage(uploaded,mf);
 assert.equal((await home()).active_import_id,other);assert.equal((await home()).active_working_set_id,null);
 await activate(uploaded);
 assert.equal((await home()).active_import_id,sourceId);assert.equal((await home()).active_working_set_id,mf.workingSetId);
 assert.equal(Number((await home()).import_version),Number(beforeNew.import_version)+1);
 assert.equal((await q('select state from ap_bill_jobs where id=$1',[upload])).rows[0].state,'activated');
 const statement=crypto.randomUUID(),revision=crypto.randomUUID(),beforeStatement=Number((await home()).bill_protection_epoch);
 await q("insert into ap_statements(id,workspace_id,filename) values($1,$2,'synthetic.pdf')",[statement,w]);
 await q("insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,rule_version,import_id,working_set_id) values($1,$2,$3,1,'{}','ap-match-v4',$4,$5)",[revision,w,statement,sourceId,mf.workingSetId]);
 await q('update ap_statements set current_revision_id=$1,completed=true,archived=true where id=$2',[revision,statement]);
 assert.equal(Number((await home()).bill_protection_epoch),beforeStatement+2);
 await assert.rejects(q("insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,rule_version,import_id,working_set_id) values($1,$2,$3,2,'{}','ap-match-v4',$4,$5)",[crypto.randomUUID(),w,statement,other,mf.workingSetId]),/bill_conflict/);
 const expired=await begin();await q("update ap_bill_working_jobs set lease_until=now()-interval '1 second' where id=$1",[expired.job_id]);
 await assert.rejects(call('checkpoint',{...data(expired),expected_checkpoint:0,next_checkpoint:1,state:'packaging'}),/bill_conflict/);
 const restarted=await call('restart',{...data(expired),expected_checkpoint:0});
 assert.notEqual(restarted.generation,expired.generation);assert.equal(restarted.checkpoint,0);assert.deepEqual(restarted.policy,expired.policy);
 await call('cancel',{...data(expired),generation:restarted.generation});
 // Scoped saves retain their exact evidence through completion and manual reopen.
 const scopedStatement=crypto.randomUUID(),initialRevision=crypto.randomUUID(),row=crypto.randomUUID();
 const doc={id:scopedStatement,vendor:'Synthetic',filename:'synthetic.pdf',confirmed:true,pageCount:1,warnings:[],statementDate:'2026-10-30',rows:[{id:row,invoiceNumber:'INV1',type:'invoice',amount:10000,confidence:99,page:1}]};
 await q("insert into ap_statements(id,workspace_id,filename,version,original_object_key) values($1,$2,'synthetic.pdf',1,'synthetic.pdf')",[scopedStatement,w]);
 await q("insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,rule_version,import_id) values($1,$2,$3,1,$4,'ap-match-v4',$5)",[initialRevision,w,scopedStatement,JSON.stringify(doc),sourceId]);
 await q('update ap_statements set current_revision_id=$1 where id=$2',[initialRevision,scopedStatement]);
 const saveData={statement_id:scopedStatement,expected_version:1,doc,resolutions:{},import_id:sourceId,mapping_snapshot:{},results:[{id:row,status:'matched',candidates:[]}],rule_version:'ap-match-v4',working_set_id:mf.workingSetId,working_version:(await home()).working_set_version};
 await assert.rejects(q('select ap_save_revision($1,$2,$3,$4)',[w,crypto.randomUUID(),'a'.repeat(64),JSON.stringify(saveData)]),/bill_conflict/);
 const refresh=await begin();await stage(refresh,mf);await activate(refresh);
 saveData.working_version=(await home()).working_set_version;
 const saved=(await q('select ap_save_revision($1,$2,$3,$4) value',[w,crypto.randomUUID(),'a'.repeat(64),JSON.stringify(saveData)])).rows[0].value;
 assert.equal((await q('select working_set_id from ap_statement_revisions where id=$1',[saved.revision_id])).rows[0].working_set_id,mf.workingSetId);
 const completed=(await q('select ap_complete_revision($1,$2,$3,$4) value',[w,crypto.randomUUID(),'b'.repeat(64),JSON.stringify({statement_id:scopedStatement,expected_version:2,initials:'KC'})])).rows[0].value;
 assert.equal((await q('select working_set_id from ap_statement_revisions where id=$1',[completed.revision_id])).rows[0].working_set_id,mf.workingSetId);
 const reopened=(await q('select ap_reopen_statement($1,$2,$3,$4) value',[w,crypto.randomUUID(),'c'.repeat(64),JSON.stringify({statement_id:scopedStatement,expected_version:3,review_mode:'manual'})])).rows[0].value;
 assert.equal((await q('select working_set_id from ap_statement_revisions where id=$1',[reopened.revision_id])).rows[0].working_set_id,mf.workingSetId);
 for(const role of ['anon','authenticated']){
  assert.equal((await q("select has_function_privilege($1,'public.ap_bill_working_mutate(text,uuid,uuid,text,jsonb)','execute') ok",[role])).rows[0].ok,false);
  assert.equal((await q("select has_table_privilege($1,'public.ap_bill_working_sets','select') ok",[role])).rows[0].ok,false);
 }
 assert.equal((await q("select has_function_privilege('service_role','public.ap_bill_working_mutate(text,uuid,uuid,text,jsonb)','execute') ok")).rows[0].ok,true);
 assert.equal((await q('select count(*)::int n from ap_bill_working_sets')).rows[0].n,2);
 assert.equal((await q('select count(*)::int n from ap_statement_revisions')).rows[0].n,5);
 console.log('Working-set SQL checks passed');
}finally{await db.close();}
