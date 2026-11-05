import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
const root=resolve(import.meta.dirname,'../../..');
const {PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite');
const db=new PGlite(),id=()=>crypto.randomUUID(),w=id(),conn=id(),q=(s,p=[])=>db.query(s,p);
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const mail=(op,data)=>q('select ap_mail_mutate($1,$2,$3,$4,$5) v',[op,w,id(),hash(data),JSON.stringify(data)]).then(r=>r.rows[0].v);
const publish=(data,request=id(),digest=hash(data))=>q('select ap_mail_publish($1,$2,$3,$4) v',[w,request,digest,JSON.stringify(data)]).then(r=>r.rows[0].v);
const context=()=>q("select ap_mail_read('source_context',$1,'{}') v",[w]).then(r=>r.rows[0].v);
const pin=async()=>{const c=await context();return {import_id:null,import_version:c.home.import_version,source_digest:null,working_set_id:null,
 working_version:c.home.working_set_version,protection_epoch:c.home.bill_protection_epoch,working_digest:null,
 mapping_versions:c.mappingVersions,mapping_digest:'a'.repeat(64),rule_version:'ap-match-v4'};};
async function incoming(letter){
 const rid=id(),sha=letter.repeat(64);
 await q(`insert into ap_mail_messages(workspace_id,connection_id,account_id,message_id,thread_id,eligible) values($1,$2,'test',$3,$3,true)`,[w,conn,rid]);
 await q(`insert into ap_mail_receipts(id,workspace_id,connection_id,account_id,message_id,part_path,filename,mime_type,declared_size)
 values($1::uuid,$2,$3,'test',$1::text,'0','synthetic.pdf','application/pdf',8)`,[rid,w,conn]);
 await q('insert into ap_mail_jobs(id,workspace_id,receipt_id,connection_id,connection_generation) values($1,$2,$1,$3,1)',[rid,w,conn]);
 const claim=(await mail('claim',{job_id:rid,dispatch_generation:1})).claim;assert.ok(claim);
 await mail('record_original',{claim,sha256:sha,object_key:`${w}/pdf/${sha}.pdf`,size:8});
 const doc={id:id(),vendor:'Synthetic Co',filename:'synthetic.pdf',confirmed:false,pageCount:1,statementDate:'2026-11-04',
 rows:[{id:id(),type:'invoice',invoiceNumber:'123',amount:100,page:1,confidence:99}]};
 await mail('save_extraction',{claim,doc,parser_version:'test',extraction_digest:hash(doc)});
 return {claim,doc,assessment:{kind:'new',match:null,repeated:0,added:1},evidence:{preliminary:true,rows:[],rangeRefreshPending:false},pin:await pin()};
}
try{
 await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create schema storage;create table storage.objects(bucket_id text,name text,metadata jsonb);');
 for(const name of readdirSync(resolve(root,'supabase/migrations')).filter(n=>n.endsWith('.sql')).sort())await db.exec(readFileSync(resolve(root,'supabase/migrations',name),'utf8'));
 await q('insert into ap_workspaces(id) values($1)',[w]);
 await q(`insert into ap_mail_connections(id,workspace_id,account_id,email,label_id,secret_ref,paused) values($1,$2,'test','test@example.test','Label_1','secret-reference',false)`,[conn,w]);
 assert.equal((await q("select has_function_privilege('anon','public.ap_mail_publish(uuid,uuid,text,jsonb)','EXECUTE') allowed")).rows[0].allowed,false);
 const a=await incoming('a'),request=id(),first=await publish(a,request);
 assert.equal(first.status,'awaiting_review');assert.equal(first.statement_id,a.doc.id);
 assert.equal((await mail('claim',{job_id:a.claim.job_id,dispatch_generation:1})).retry,false);
 assert.deepEqual(await publish(a,request),first); // lost response can replay after lease is released
 await assert.rejects(publish({...a,doc:{...a.doc,vendor:'Changed'}},request),/conflict/);
 const rev=(await q('select * from ap_statement_revisions where statement_id=$1',[a.doc.id])).rows[0];
 const receiptVersion=(await q('select version from ap_mail_receipts where id=$1',[a.claim.receipt_id])).rows[0].version;
 await q('update ap_mail_preliminary set rows=$1 where receipt_id=$2',[Array.from({length:75},(_,n)=>({id:'row-'+n,invoiceNumber:String(n),originalAmount:100,status:n?'amount':'presence',candidates:[]})),a.claim.receipt_id]);
 const evidence=(await q("select ap_mail_control_read('evidence',$1,$2) v",[w,{receipt_id:a.claim.receipt_id,expected_version:receiptVersion,limit:50,cursor:0}])).rows[0].v;
 assert.equal(evidence.preliminary,true);assert.equal(evidence.rows.length,50);assert.equal(evidence.total,75);assert.equal(evidence.nextCursor,50);
 const evidenceTail=(await q("select ap_mail_control_read('evidence',$1,$2) v",[w,{receipt_id:a.claim.receipt_id,expected_version:receiptVersion,limit:50,cursor:50}])).rows[0].v;
 assert.equal(evidenceTail.rows.length,25);assert.equal(evidenceTail.nextCursor,null);
 await assert.rejects(q("select ap_mail_control_read('evidence',$1,$2)",[w,{receipt_id:a.claim.receipt_id,expected_version:receiptVersion-1,limit:50}]),/conflict/);
 assert.deepEqual(rev.results,[]);assert.deepEqual(rev.resolutions,{});assert.equal(rev.import_id,null);
 assert.equal((await q('select count(*)::int n from ap_mail_preliminary')).rows[0].n,1);
 assert.equal((await q('select count(*)::int n from ap_completion_events')).rows[0].n,0);
 // Byte matches link even completed/archived, regardless of semantic parser output.
 await q('update ap_statements set completed=true,archived=true,version=version+1 where id=$1',[a.doc.id]);
 const b=await incoming('a');
 assert.equal((await q('select ap_mail_byte_match($1,$2) v',[w,b.claim.receipt_id])).rows[0].v.match.id,a.doc.id);
 assert.equal((await publish(b)).status,'already_imported');
 assert.equal((await q('select count(*)::int n from ap_statement_revisions')).rows[0].n,1);
 // Semantic duplicate keeps its different incoming original and links the saved head.
 const c=await incoming('c');c.assessment={kind:'duplicate',match:{id:a.doc.id,revision_id:rev.id,version:2},repeated:1,added:0};
 assert.equal((await publish(c)).statement_id,a.doc.id);
 assert.equal((await q('select sha256 from ap_mail_receipts where id=$1',[c.claim.receipt_id])).rows[0].sha256,'c'.repeat(64));
 // Similar statements stop at attention; no new statement/revision.
 const d=await incoming('d');d.assessment={...c.assessment,kind:'similar'};
 assert.equal((await publish(d)).status,'needs_attention');
 assert.equal((await q('select count(*)::int n from ap_statements')).rows[0].n,1);
 // Overlap creates a whole separate draft, retains all rows.
 const e=await incoming('e');e.doc.rows.push({...e.doc.rows[0],id:id(),invoiceNumber:'124'});
 await q('update ap_mail_receipts set extraction=$1,extraction_digest=$2 where id=$3',[e.doc,hash(e.doc),e.claim.receipt_id]);
 e.assessment={...c.assessment,kind:'overlap',added:1};const overlap=await publish(e);
 assert.equal(overlap.status,'awaiting_review');
 assert.equal((await q('select jsonb_array_length(doc->\'rows\') n from ap_statement_revisions where statement_id=$1',[e.doc.id])).rows[0].n,2);
 // All inventory/head and source races fail before any draft is published.
 const f=await incoming('f');await q('update ap_statements set version=version+1 where id=$1',[a.doc.id]);
 await assert.rejects(publish(f),/stale_source/);
 f.pin=await pin();f.assessment={...c.assessment};await assert.rejects(publish(f),/conflict/);
 await mail('needs_attention',{claim:f.claim,reason:'conflict'});
 // A stale worker cannot write, and no caller-supplied results can forge a review.
 const g=await incoming('0');await assert.rejects(publish({...g,claim:{...g.claim,slot_generation:999}}),/stale_claim/);
 await assert.rejects(publish({...g,results:[{status:'presence'}]}),/invalid/);
 await mail('needs_attention',{claim:g.claim,reason:'conflict'});
 // Recompare only replaces separate preliminary evidence while owned head stays untouched.
 const receipt=(await q('select * from ap_mail_receipts where id=$1',[e.claim.receipt_id])).rows[0];
 await mail('retry',{receipt_id:receipt.id,expected_version:receipt.version});
 let claim=(await mail('claim',{job_id:receipt.id,dispatch_generation:2})).claim;
 const recomparison={...e,claim,pin:await pin()};await publish(recomparison);
 assert.equal((await q('select count(*)::int n from ap_statement_revisions where statement_id=$1',[e.doc.id])).rows[0].n,1);
 const r2=(await q('select * from ap_mail_receipts where id=$1',[receipt.id])).rows[0];await mail('retry',{receipt_id:r2.id,expected_version:r2.version});
 claim=(await mail('claim',{job_id:r2.id,dispatch_generation:3})).claim;
 await q('update ap_statements set version=version+1 where id=$1',[e.doc.id]);
 await assert.rejects(publish({...e,claim,pin:await pin()}),/conflict/);
 await mail('needs_attention',{claim,reason:'conflict'});
 // All storage writers share the same bucket budget, including mail reservations.
 const h=await incoming('1');
 const reserve=(bytes,budget)=>q('select ap_mail_reserve($1,$2,$3,$4,$5) v',[w,h.claim,'hwfc-ap-private',bytes,budget]);
 await assert.rejects(reserve(8,7),/storage/);await reserve(8,100);
 const billJob=id();
 await q("insert into ap_bill_jobs(id,workspace_id,session_nonce,expected_import_version,metadata) values($1,$2,$3,0,'{}')",[billJob,w,id()]);
 await assert.rejects(q("select ap_storage_reserve('bill',$1,$2,'hwfc-ap-private',95,100)",[w,billJob]),/bill_quota/);
 await mail('needs_attention',{claim:h.claim,reason:'storage'});
 // A new comparison cycle can be queued only for an untouched machine draft.
 const i=await incoming('3');await publish(i);
 const queued=(await q('select ap_mail_queue_stale($1,$2,50) v',[w,conn])).rows[0].v;
 assert.equal(queued.queued,1);
 const job=(await q('select mode,attempts,state from ap_mail_jobs where receipt_id=$1',[i.claim.receipt_id])).rows[0];
 assert.deepEqual(job,{mode:'recompare',attempts:0,state:'queued'});
 // Human controls never take a worker lease, create a revision or expose secrets.
 const control=(op,data,request=id(),digest=hash(data))=>q('select ap_mail_control($1,$2,$3,$4,$5) v',[op,w,request,digest,data]).then(r=>r.rows[0].v);
 const paused=(await q('select version from ap_mail_connections where id=$1',[conn])).rows[0].version;
 const pauseRequest=id(),pauseData={connection_id:conn,expected_version:paused,paused:true};
 const pauseReply=await control('pause',pauseData,pauseRequest);assert.deepEqual(await control('pause',pauseData,pauseRequest),pauseReply);
 await assert.rejects(control('pause',{...pauseData,paused:false},pauseRequest),/conflict/);
 await control('pause',{...pauseData,expected_version:paused+1,paused:false});
 const history={connection_id:conn,expected_version:paused+2,after:'2026-10-01T00:00:00Z',before:'2026-11-01T00:00:00Z',max_messages:1001};
 await assert.rejects(control('history',history),/invalid/);
 await control('history',{...history,max_messages:100});
 assert.equal((await q('select history_request from ap_mail_connections where id=$1',[conn])).rows[0].history_request.max_messages,100);
 const similar=(await q('select version from ap_mail_receipts where id=$1',[d.claim.receipt_id])).rows[0];
 // Candidate a changed since the saved similarity assessment; it cannot be silently chosen.
 await assert.rejects(control('choice',{receipt_id:d.claim.receipt_id,expected_version:similar.version,choice:'existing'}),/conflict/);
 const list=(await q("select ap_mail_control_read('receipts',$1,'{\"limit\":50}') v",[w])).rows[0].v;
 assert.ok(list.items.length);assert.equal(JSON.stringify(list).includes('secret-reference'),false);
 assert.equal(list.items.find(row=>row.id===a.claim.receipt_id).display_status,'reviewed');
 const refreshed=(await q("select ap_mail_control_read('receipt_updates',$1,$2) v",[w,{receipt_ids:[a.claim.receipt_id]}])).rows[0].v;
 assert.equal(refreshed.items.length,1);assert.equal(refreshed.items[0].id,a.claim.receipt_id);
 await q("update ap_mail_receipts set discovered_at=now()+interval '1 day' where id=$1",[d.claim.receipt_id]);
 const latest=(await q("select ap_mail_control_read('receipts',$1,'{\"limit\":1}') v",[w])).rows[0].v;
 assert.equal(latest.items[0].id,d.claim.receipt_id);
 const next=(await q("select ap_mail_control_read('receipts',$1,$2) v",[w,{limit:50,cursor:latest.nextCursor}])).rows[0].v;
 assert.ok(next.items.every(row=>row.id!==d.claim.receipt_id));
 const msg=id();await q(`insert into ap_mail_messages(workspace_id,connection_id,account_id,message_id,thread_id,eligible,error_code)
 values($1,$2,'test',$3,$3,false,'historical')`,[w,conn,msg]);
 await control('message_retry',{connection_id:conn,message_id:msg,expected_version:1});
 assert.ok((await q('select cursor from ap_mail_connections where id=$1',[conn])).rows[0].cursor.manual_pending.includes(msg));
 console.log('Mail publication checks passed');
}finally{await db.close();}
