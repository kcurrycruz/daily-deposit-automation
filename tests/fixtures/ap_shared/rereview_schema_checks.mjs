import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'../../..');
let PGlite;
try{({PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite'));}
catch{({PGlite}=createRequire(resolve(root,'../../app/ap_statements/package.json'))('@electric-sql/pglite'));}
const db=new PGlite(),w=crypto.randomUUID(),other=crypto.randomUUID();
const q=(sql,args=[])=>db.query(sql,args);
const call=(name,data,id=crypto.randomUUID(),hash='a'.repeat(64),workspace=w)=>q(
 `select public.${name}($1,$2,$3,$4) value`,[workspace,id,hash,JSON.stringify(data)]).then(r=>r.rows[0].value);
try{
 await db.exec('create role anon;create role authenticated;create role service_role bypassrls;');
 await db.exec(readFileSync(resolve(root,'supabase/migrations/202610130001_ap_shared_workspace.sql'),'utf8'));
 await db.exec(readFileSync(resolve(root,'supabase/migrations/202610230001_ap_statement_rereview.sql'),'utf8'));
 await q('insert into ap_workspaces(id) values($1),($2)',[w,other]);
 assert.equal((await q('select rereview_schema_version from ap_workspaces where id=$1',[w])).rows[0].rereview_schema_version,1);
 const iid=crypto.randomUUID();
 await q('insert into ap_bill_imports(id,workspace_id,file_hash,original_object_key,metadata,record_count,state) values($1,$2,$3,$4,$5,1,$6)',[iid,w,'e'.repeat(64),'synthetic/private.csv','{}','ready']);
 async function completed(){
  const sid=crypto.randomUUID(),rid=crypto.randomUUID(),rowId=crypto.randomUUID();
  const doc={id:sid,vendor:'Synthetic',filename:'statement.pdf',notes:'Keep statement notes',statementDate:'2026-10-01',confirmed:true,pageCount:1,warnings:[],rows:[{id:rowId,type:'invoice',invoiceNumber:'00042',amount:13800,page:1,confidence:99}]};
  const resolutions={[rowId]:{decision:'Reviewed — no action needed',note:'Prior checked note',at:'2026-10-01T12:00:00Z'}};
  const results=[{id:rowId,status:'missing',vendor:'Synthetic',invoiceNumber:'00042',kind:'invoice',originalAmount:13800,candidates:[]}];
  await q('insert into ap_statements(id,workspace_id,filename,version,completed,original_object_key) values($1,$2,$3,1,true,$4)',[sid,w,doc.filename,'synthetic/private.pdf']);
  await q('insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,resolutions,import_id,mapping_snapshot,results,rule_version) values($1,$2,$3,1,$4,$5,$6,$7,$8,$9)',[rid,w,sid,JSON.stringify(doc),JSON.stringify(resolutions),iid,'{"Synthetic":"Synthetic BILL"}',JSON.stringify(results),'ap-match-v3']);
  await q('update ap_statements set current_revision_id=$1 where id=$2',[rid,sid]);
  await q('insert into ap_completion_events(workspace_id,statement_id,revision_id,event,initials,status) values($1,$2,$3,$4,$5,$6)',[w,sid,rid,'completed','KC','reviewed']);
  return {sid,rid,doc,resolutions,results};
 }
 const old=await completed(),request=crypto.randomUUID(),payload={statement_id:old.sid,expected_version:1,review_mode:'manual'};
 const saved=await call('ap_reopen_statement',payload,request);
 assert.equal(saved.version,2);assert.notEqual(saved.revision_id,old.rid);
 assert.deepEqual(await call('ap_reopen_statement',payload,request),saved);
 const newRevision=(await q('select * from ap_statement_revisions where id=$1',[saved.revision_id])).rows[0];
 assert.equal(newRevision.doc.reviewMode,'manual');assert.equal(newRevision.doc.notes,'Keep statement notes');
 assert.deepEqual(newRevision.resolutions,old.resolutions);assert.deepEqual(newRevision.results,old.results);
 assert.equal(newRevision.import_id,iid);assert.equal(newRevision.rule_version,'ap-match-v3');
 assert.deepEqual(newRevision.mapping_snapshot,{'Synthetic':'Synthetic BILL'});
 assert.deepEqual((await q('select doc from ap_statement_revisions where id=$1',[old.rid])).rows[0].doc,old.doc);
 assert.equal((await q('select count(*)::int n from ap_completion_events where statement_id=$1',[old.sid])).rows[0].n,2);
 await assert.rejects(call('ap_reopen_statement',{...payload,review_mode:'latest'},request,'b'.repeat(64)),/request_conflict/);
 await assert.rejects(call('ap_reopen_statement',payload),/conflict/);
 await assert.rejects(call('ap_reopen_statement',{...payload,expected_version:2}),/conflict/);
 await assert.rejects(call('ap_reopen_statement',payload,undefined,undefined,other),/conflict/);
 const newCompletion=await call('ap_complete_revision',{statement_id:old.sid,expected_version:2,initials:'AB'});
 assert.equal(newCompletion.version,3);
 assert.equal((await q("select count(*)::int n from ap_completion_events where statement_id=$1 and event='completed'",[old.sid])).rows[0].n,2);
 const latestOld=await completed();
 const latest=await call('ap_reopen_statement',{statement_id:latestOld.sid,expected_version:1,review_mode:'latest'});
 const latestRevision=(await q('select * from ap_statement_revisions where id=$1',[latest.revision_id])).rows[0];
 assert.equal(latestRevision.doc.reviewMode,'latest');
 assert.deepEqual(latestRevision.resolutions,{[latestOld.doc.rows[0].id]:{note:'Prior checked note'}});
 await assert.rejects(call('ap_reopen_statement',{statement_id:latestOld.sid,expected_version:2,review_mode:'bogus'}),/validation/);
 await assert.rejects(call('ap_reopen_statement',{statement_id:latestOld.sid,expected_version:2,review_mode:'manual',extra:true}),/validation/);
 const legacyOld=await completed();
 const legacy=await call('ap_reopen_statement',{statement_id:legacyOld.sid,expected_version:1});
 assert.deepEqual((await q('select resolutions from ap_statement_revisions where id=$1',[legacy.revision_id])).rows[0].resolutions,{});
 for(const role of ['anon','authenticated']){
  await db.exec('set role '+role);
  await assert.rejects(call('ap_rereview_statement',payload),/permission denied/);
  await assert.rejects(call('ap_reopen_statement',payload),/permission denied/);
  await db.exec('reset role');
 }
 await db.exec('set role service_role');
 const privateOld=await call('ap_reopen_statement',{statement_id:crypto.randomUUID(),expected_version:1,review_mode:'manual'}).then(()=>false,error=>/conflict/.test(error.message));
 assert.equal(privateOld,true);await db.exec('reset role');
 await assert.rejects(q('update ap_statement_revisions set resolutions=$1 where id=$2',['{}',old.rid]),/immutable/);
 console.log('Re-review SQL checks passed: private atomic modes, pinned evidence, immutable history, CAS and retries.');
}finally{await db.close();}
