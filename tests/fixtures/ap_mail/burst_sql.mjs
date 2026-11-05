// Test-only RPC boundary over real embedded PostgreSQL. No external database exists here.
import {createInterface} from 'node:readline';
import {readFileSync,readdirSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {textPdf,statementLines} from './pdfs.mjs';
const root=resolve(import.meta.dirname,'../../..');
const {PGlite}=createRequire(resolve(root,'app/ap_statements/package.json'))('@electric-sql/pglite');
const db=new PGlite(),w='00000000-0000-4000-8000-000000000001',conn='00000000-0000-4000-8000-000000000002';
const q=(sql,args=[])=>db.query(sql,args);let human;let billReads=0;
await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create schema storage;create table storage.objects(bucket_id text,name text,metadata jsonb);');
for(const name of readdirSync(resolve(root,'supabase/migrations')).filter(n=>n.endsWith('.sql')).sort())await db.exec(readFileSync(resolve(root,'supabase/migrations',name),'utf8'));
await q('insert into ap_workspaces(id) values($1)',[w]);
const source=crypto.randomUUID();
await q(`insert into ap_bill_imports(id,workspace_id,file_hash,original_object_key,metadata,record_count)
 values($1,$2,$3,$4,'{"label":"Synthetic Bills.csv","sourceFormat":"bill-native"}',200)`,[source,w,'b'.repeat(64),w+'/csv/'+'b'.repeat(64)+'.csv']);
for(let n=0;n<200;n++)await q('insert into ap_bill_records(workspace_id,import_id,ordinal,record) values($1,$2,$3,$4)',[w,source,n,
 {vendor:'A.J. Rinella',invoiceNumber:String(40000+n),amount:n%2?20000:10000,kind:'invoice',currency:'USD',comparisonScope:'invoice-only'}]);
await q("update ap_bill_imports set state='ready' where id=$1",[source]);
await q('update ap_workspaces set active_import_id=$1 where id=$2',[source,w]);
await q(`insert into ap_mail_connections(id,workspace_id,account_id,email,label_id,secret_ref,paused,cursor) values($1,$2,'test','synthetic@example.test','Label_1','projects/synthetic-project/secrets/test',false,'{"phase":"live","history_id":"999"}')`,[conn,w]);
const sid=crypto.randomUUID(),rev=crypto.randomUUID();
await q(`insert into ap_statements(id,workspace_id,filename) values($1,$2,'prior-human.pdf')`,[sid,w]);
await q(`insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,resolutions,rule_version)
 values($1,$2,$3,1,$4,'{"prior":{"decision":"Reviewed — no action needed","note":"Preserve human note"}}','ap-match-v4')`,
 [rev,w,sid,{id:sid,vendor:'Different synthetic vendor',confirmed:true,rows:[],notes:'Preserve this saved history'}]);
await q('update ap_statements set version=1,completed=true,current_revision_id=$1 where id=$2',[rev,sid]);
await q(`insert into ap_completion_events(workspace_id,statement_id,revision_id,event,initials,status) values($1,$2,$3,'completed','KC','reviewed')`,[w,sid,rev]);
human=JSON.stringify((await q('select * from ap_statement_revisions where id=$1',[rev])).rows[0]);
const pdfs=Array.from({length:100},(_,n)=>textPdf(statementLines.map(line=>line.replace('00042',String(40000+n*2)).replace('00043',String(40001+n*2)))).toString('base64'));
const send=value=>process.stdout.write(JSON.stringify(value)+'\n');send({workspace_id:w,connection_id:conn,pdfs});
const functions={
 ap_mail_mutate:['p_operation','p_workspace','p_request_id','p_payload_hash','p_data'],
 ap_mail_read:['p_operation','p_workspace','p_data'],ap_mail_publish:['p_workspace','p_request_id','p_payload_hash','p_data'],
 ap_mail_candidates:['p_workspace','p_cursor','p_limit'],ap_mail_queue_stale:['p_workspace','p_connection','p_limit'],
 ap_mail_byte_match:['p_workspace','p_receipt_id'],
 ap_mail_reserve:['p_workspace','p_claim','p_bucket','p_requested','p_budget'],
};
const lines=createInterface({input:process.stdin,crlfDelay:Infinity});
try{for await(const line of lines){
 try{
  const request=JSON.parse(line);let value;
  if(request.test==='expire'){
   await q("update ap_mail_jobs set lease_until=now()-interval '1 second' where id=$1",[request.job_id]);
   await q("update ap_mail_processor_slots set lease_until=now()-interval '1 second' where job_id=$1",[request.job_id]);value={saved:true};
  }else if(request.test==='advance'){
   await q('update ap_mail_jobs set next_retry_at=now() where state=\'queued\'');await q('update ap_mail_outbox set next_attempt_at=now()');value={saved:true};
  }else if(request.test==='object'){
   await q("insert into storage.objects(bucket_id,name,metadata) values('hwfc-ap-private',$1,$2)",[request.key,{size:request.size}]);value={saved:true};
  }else if(request.test==='table'){
   if(!['ap_bill_records','ap_bill_imports'].includes(request.table))throw Error('invalid');
   const params=[],conditions=[];
   for(const [key,operator,value] of request.filters){
    if(!['workspace_id','id','import_id','ordinal'].includes(key)||!['=','>'].includes(operator))throw Error('invalid');
    params.push(value);conditions.push(key+operator+'$'+params.length);
   }
   if(request.table==='ap_bill_records')billReads++;
   params.push(request.limit||1);
   value=(await q('select * from '+request.table+' where '+conditions.join(' and ')+(request.table==='ap_bill_records'?' order by ordinal':'')+' limit $'+params.length,params)).rows;
  }else if(request.test==='counts'){
   const count=async(sql)=>(await q(sql)).rows[0].n;
   value={receipts:await count('select count(*)::int n from ap_mail_receipts'),statements:await count('select count(*)::int n from ap_statements'),
    awaiting_review:await count("select count(*)::int n from ap_mail_receipts where status='awaiting_review'"),
    completion_events:await count('select count(*)::int n from ap_completion_events'),running:await count("select count(*)::int n from ap_mail_jobs where state='running'"),
    max_attempts:await count('select max(attempts)::int n from ap_mail_jobs'),human_unchanged:human===JSON.stringify((await q('select * from ap_statement_revisions where id=$1',[rev])).rows[0]),
    preliminary_found:await count("select count(*)::int n from ap_mail_preliminary p,jsonb_array_elements(p.rows) r where r->>'status'='presence'"),
    bill_source_table_reads:billReads,sql_peak_rss_kib:process.resourceUsage().maxRSS};
  }else{
   const keys=functions[request.name];if(!keys)throw Error('invalid');
   const params=keys.map(key=>request.args[key]??null).map(v=>v&&typeof v==='object'?JSON.stringify(v):v);
   value=(await q(`select ${request.name}(${keys.map((_,n)=>'$'+(n+1)).join(',')}) value`,params)).rows[0].value;
  }
  send({value});
 }catch(error){send({error:['conflict','stale_claim','stale_source','invalid','not_found','paused','exhausted','storage'].includes(error.message)?error.message:'unavailable'});}
}}finally{await db.close();}
