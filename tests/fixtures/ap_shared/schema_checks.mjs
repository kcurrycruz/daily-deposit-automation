import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';

const root=resolve(import.meta.dirname,'../../..');
const migration=resolve(root,'supabase/migrations/202610130001_ap_shared_workspace.sql');
assert.ok(existsSync(migration),'The private shared AP migration must exist');
let PGlite;
try { ({PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite')); }
catch { ({PGlite}=createRequire(resolve(root,'.superpowers/sdd/2026-10-13-ap-shared-workspace/sql-runtime/package.json'))('@electric-sql/pglite')); }
const db=new PGlite();
const workspace='00000000-0000-4000-8000-000000000001';
const statement='00000000-0000-4000-8000-000000000002';
let count=0;
const query=(sql,params=[])=>db.query(sql,params);
const call=(name,data,id=crypto.randomUUID(),hash='a'.repeat(64))=>query(`select public.${name}($1::uuid,$2::uuid,$3::text,$4::jsonb) as result`,[workspace,id,hash,JSON.stringify(data)]).then(r=>r.rows[0].result);
try {
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
  await db.exec(readFileSync(migration,'utf8'));
  const tables=await query("select relname,relrowsecurity from pg_class where relname = any($1::text[]) order by relname",[['ap_workspaces','ap_bill_imports','ap_bill_records','ap_statements','ap_statement_revisions','ap_completion_events','ap_vendor_mappings','ap_requests','ap_uploads','ap_access_limits']]);
  assert.equal(tables.rows.length,10); assert.ok(tables.rows.every(r=>r.relrowsecurity)); count++;
  const rpc=(await query("select proargnames from pg_proc where proname='ap_save_revision'")).rows[0];
  assert.deepEqual(rpc.proargnames,['p_workspace','p_request_id','p_payload_hash','p_data']); count++;
  await query('insert into public.ap_workspaces(id) values($1)',[workspace]);
  await db.exec('set role anon');
  await assert.rejects(query('select * from public.ap_workspaces'),/permission denied/); count++;
  await assert.rejects(call('ap_save_revision',{}),/permission denied/); count++;
  await db.exec('reset role; grant select on public.ap_workspaces to anon; set role anon');
  assert.equal((await query('select * from public.ap_workspaces')).rows.length,0); count++;
  await db.exec('reset role; revoke select on public.ap_workspaces from anon');
  const uploadId='00000000-0000-4000-8000-000000000015';
  const uploadNonce='00000000-0000-4000-8000-000000000016';
  const up=await call('ap_begin_upload',{upload_id:uploadId,session_nonce:uploadNonce,metadata:{kind:'pdf',filename:'synthetic.pdf',size:4,file_hash:'3'.repeat(64)}});
  assert.equal(up.upload_id,uploadId); count++;
  await assert.rejects(call('ap_put_chunk',{upload_id:uploadId,session_nonce:uploadNonce,index:0,size:1,chunk_hash:'4'.repeat(64)}),/validation/); count++;
  await assert.rejects(call('ap_put_chunk',{upload_id:uploadId,session_nonce:crypto.randomUUID(),index:0,size:4,chunk_hash:'4'.repeat(64)}),/upload_denied/); count++;
  await call('ap_put_chunk',{upload_id:uploadId,session_nonce:uploadNonce,index:0,size:4,chunk_hash:'4'.repeat(64)});
  await assert.rejects(call('ap_put_chunk',{upload_id:uploadId,session_nonce:uploadNonce,index:0,size:4,chunk_hash:'5'.repeat(64)}),/request_conflict/); count++;
  const finished=await call('ap_finish_upload',{upload_id:uploadId,session_nonce:uploadNonce,object_key:workspace+'/pdf/'+'3'.repeat(64)+'.pdf'});
  assert.equal(finished.state,'ready'); count++;
  const importing=await call('ap_begin_import',{file_hash:'2'.repeat(64),original_object_key:'synthetic/private.csv',metadata:{label:'synthetic.csv'},record_count:2});
  await assert.rejects(call('ap_activate_import',{import_id:importing.import_id}),/import_incomplete/);
  assert.equal((await query('select active_import_id from ap_workspaces')).rows[0].active_import_id,null); count++;
  await call('ap_append_records',{import_id:importing.import_id,start:0,records:[{vendor:'Synthetic',invoiceNumber:'00042',amount:18400}]});
  await assert.rejects(call('ap_activate_import',{import_id:importing.import_id}),/import_incomplete/); count++;
  await call('ap_append_records',{import_id:importing.import_id,start:1,records:[{vendor:'Synthetic',invoiceNumber:'00043',amount:18400}]});
  await call('ap_activate_import',{import_id:importing.import_id});
  assert.equal((await query('select active_import_id from ap_workspaces')).rows[0].active_import_id,importing.import_id); count++;
  await assert.rejects(query('update ap_bill_records set record=$1',[JSON.stringify({vendor:'tampered'})]),/immutable/); count++;
  await assert.rejects(query('update ap_bill_imports set metadata=$1',[JSON.stringify({label:'tampered'})]),/immutable/); count++;
  const doc={id:statement,vendor:'Synthetic',filename:'synthetic.pdf',confirmed:true,pageCount:1,warnings:[],notes:'Preserve earlier statement notes',rows:[{id:'00000000-0000-4000-8000-000000000003',type:'invoice',invoiceNumber:'00042',amount:18400,balance:18400,confidence:99,page:1}]};
  await call('ap_register_statement',{statement_id:statement,file_hash:'1'.repeat(64),original_object_key:'synthetic/private.pdf',doc});
  const draft=await call('ap_save_revision',{statement_id:statement,expected_version:1,doc,resolutions:{r:{decision:'Reviewed — no action needed',note:''}},results:[{id:'r',status:'possible',invoiceNumber:'00042'}],mapping_snapshot:{},import_id:null,rule_version:'ap-match-v2'});
  assert.equal(draft.version,2); count++;
  assert.ok((await query("select resolutions->'r'->>'at' as at from ap_statement_revisions where version=2")).rows[0].at); count++;
  await assert.rejects(call('ap_save_revision',{statement_id:statement,expected_version:1,doc}),/conflict/); count++;
  const req=crypto.randomUUID();
  const complete={statement_id:statement,expected_version:2,initials:'KC',notes:''};
  const first=await call('ap_complete_revision',complete,req),second=await call('ap_complete_revision',complete,req);
  assert.deepEqual(first,second); assert.equal((await query('select count(*)::int as n from ap_completion_events')).rows[0].n,1); count++;
  assert.equal((await query('select vendor from ap_completion_events')).rows[0].vendor,'Synthetic'); count++;
  assert.equal((await query("select doc->>'notes' as note from ap_statement_revisions where version=3")).rows[0].note,'Preserve earlier statement notes'); count++;
  await assert.rejects(call('ap_complete_revision',{...complete,notes:'changed'},req,'b'.repeat(64)),/request_conflict/); count++;
  await assert.rejects(query('update ap_statement_revisions set doc=$1',[JSON.stringify({})]),/immutable/); count++;
  await assert.rejects(query('delete from ap_completion_events'),/immutable/); count++;
  await assert.rejects(call('ap_save_revision',{statement_id:statement,expected_version:3,doc}),/completed/); count++;
  const reopened=await call('ap_reopen_statement',{statement_id:statement,expected_version:3});
  assert.equal(reopened.version,4); assert.equal((await query('select count(*)::int as n from ap_completion_events')).rows[0].n,2); count++;
  const nonce='00000000-0000-4000-8000-000000000004';
  for(let i=0;i<5;i++) {
    const ticket=(await query('select ap_begin_access_attempt($1::uuid,$2::uuid) as ticket',[workspace,nonce])).rows[0].ticket;
    assert.ok(ticket); await query('select ap_finish_access_attempt($1::uuid,$2::uuid,$3::boolean)',[workspace,ticket,false]);
  }
  assert.equal((await query('select ap_begin_access_attempt($1::uuid,$2::uuid) as ticket',[workspace,nonce])).rows[0].ticket,null); count++;
  const authWorkspace='00000000-0000-4000-8000-000000000099';
  for(let i=0;i<100;i++) {
    const ticket=(await query('select ap_begin_access_attempt($1::uuid,$2::uuid) as ticket',[authWorkspace,crypto.randomUUID()])).rows[0].ticket;
    assert.ok(ticket); await query('select ap_finish_access_attempt($1::uuid,$2::uuid,$3::boolean)',[authWorkspace,ticket,false]);
  }
  assert.equal((await query('select ap_begin_access_attempt($1::uuid,$2::uuid) as ticket',[authWorkspace,crypto.randomUUID()])).rows[0].ticket,null); count++;
  await query("update ap_access_limits set blocked_until=now()-interval '1 second',events='[]' where workspace_id=$1",[authWorkspace]);
  const recovery=(await query('select ap_begin_access_attempt($1::uuid,$2::uuid) as ticket',[authWorkspace,nonce])).rows[0].ticket;
  assert.ok(recovery); await query('select ap_finish_access_attempt($1::uuid,$2::uuid,$3::boolean)',[authWorkspace,recovery,true]);
  assert.ok((await query('select events from ap_access_limits where workspace_id=$1',[authWorkspace])).rows.every(r=>r.events.length===0)); count++;
  console.log(`SQL behavior checks passed: ${count}; real Postgres engine, synthetic fixtures only.`);
} catch(error) {
  console.error(error.message);
  if(error.where)console.error(error.where);
  process.exitCode=1;
} finally { await db.close(); }
