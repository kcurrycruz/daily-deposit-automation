-- Additive, private intake protocol. No originals, statements or history deleted.
begin;
alter table public.ap_workspaces add column mail_schema_version integer not null default 1;

create table public.ap_mail_connections (
 id uuid primary key, workspace_id uuid not null references public.ap_workspaces(id),
 account_id text not null check(octet_length(account_id) between 1 and 256),
 email text not null check(octet_length(email) between 1 and 320),
 label_id text not null check(octet_length(label_id) between 1 and 256),
 label_name text not null default 'AP Statements', secret_ref text not null,
 active boolean not null default true, paused boolean not null default true,
 generation bigint not null default 1 check(generation>0), version bigint not null default 1 check(version>0),
 cursor jsonb not null default '{"phase":"baseline"}' check(jsonb_typeof(cursor)='object' and octet_length(cursor::text)<=65536),
 activated_at timestamptz not null default now(), last_checked_at timestamptz, last_success_at timestamptz,
 error_code text, history_request jsonb, created_at timestamptz not null default now(),
 unique(workspace_id,id)
);
create unique index ap_mail_one_connection on public.ap_mail_connections(workspace_id) where active;
create table public.ap_mail_messages (
 workspace_id uuid not null, connection_id uuid not null, account_id text not null,
 message_id text not null check(octet_length(message_id) between 1 and 256),
 thread_id text not null check(octet_length(thread_id) between 1 and 256),
 received_at timestamptz, sender text not null default '' check(octet_length(sender)<=1024),
 subject text not null default '' check(octet_length(subject)<=2048), eligible boolean not null,
 error_code text check(error_code is null or error_code in ('historical','withdrawn','invalid','unreadable','limit','not_found')),
 discovered_at timestamptz not null default now(),
 primary key(workspace_id,account_id,message_id),
 foreign key(workspace_id,connection_id) references public.ap_mail_connections(workspace_id,id)
);
create table public.ap_mail_receipts (
 id uuid primary key, workspace_id uuid not null, connection_id uuid not null, account_id text not null,
 message_id text not null, part_path text not null check(part_path ~ '^0(\.[0-9]{1,3}){0,20}$'),
 filename text not null check(octet_length(filename) between 1 and 1024), mime_type text not null check(mime_type='application/pdf'),
 declared_size integer not null check(declared_size between 1 and 20971520), attachment_id text,
 status text not null default 'queued' check(status in ('queued','scanning','awaiting_review','needs_attention','already_imported','skipped')),
 reason text, version bigint not null default 1 check(version>0),
 sha256 text check(sha256 ~ '^[a-f0-9]{64}$'), original_object_key text, actual_size integer check(actual_size between 1 and 20971520),
 extraction jsonb, extraction_digest text, parser_version text,
 statement_id uuid, owned_revision_id uuid, assessment jsonb, human_choice jsonb,
 imported_at timestamptz, discovered_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(workspace_id,id), unique(workspace_id,account_id,message_id,part_path),
 foreign key(workspace_id,connection_id) references public.ap_mail_connections(workspace_id,id),
 foreign key(workspace_id,account_id,message_id) references public.ap_mail_messages(workspace_id,account_id,message_id),
 foreign key(workspace_id,statement_id) references public.ap_statements(workspace_id,id),
 check(extraction is null or (jsonb_typeof(extraction)='object' and octet_length(extraction::text)<=1048576)),
 check(sha256 is null or original_object_key=workspace_id::text||'/pdf/'||sha256||'.pdf')
);
create index ap_mail_receipt_list on public.ap_mail_receipts(workspace_id,discovered_at desc,id);
create index ap_mail_receipt_status on public.ap_mail_receipts(workspace_id,status,id);
create table public.ap_mail_jobs (
 id uuid primary key, workspace_id uuid not null, receipt_id uuid not null unique, connection_id uuid not null,
 connection_generation bigint not null check(connection_generation>0),
 dispatch_generation bigint not null default 1 check(dispatch_generation>0),
 lease_generation bigint not null default 0 check(lease_generation>=0), slot_generation bigint not null default 0,
 state text not null default 'queued' check(state in ('queued','running','done','attention')),
 mode text not null default 'extract' check(mode in ('extract','recompare')),
 attempts integer not null default 0 check(attempts between 0 and 3), lease_until timestamptz not null default '-infinity',
 next_retry_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 reserved_bytes bigint not null default 0 check(reserved_bytes>=0), reservation_bucket text,
 unique(workspace_id,id),
 foreign key(workspace_id,receipt_id) references public.ap_mail_receipts(workspace_id,id),
 foreign key(workspace_id,connection_id) references public.ap_mail_connections(workspace_id,id)
);
create index ap_mail_jobs_recovery on public.ap_mail_jobs(workspace_id,state,id);
create table public.ap_mail_processor_slots (
 workspace_id uuid primary key references public.ap_workspaces(id), job_id uuid,
 generation bigint not null default 0, lease_until timestamptz not null default '-infinity',
 foreign key(workspace_id,job_id) references public.ap_mail_jobs(workspace_id,id)
);
create table public.ap_mail_attempts (
 id bigint generated always as identity primary key, workspace_id uuid not null, job_id uuid not null,
 dispatch_generation bigint not null, lease_generation bigint not null, slot_generation bigint not null,
 event text not null, reason text, at timestamptz not null default now(),
 foreign key(workspace_id,job_id) references public.ap_mail_jobs(workspace_id,id)
);
create trigger ap_mail_attempt_immutable before update or delete on public.ap_mail_attempts
 for each row execute function public.ap_immutable_history();
create table public.ap_mail_outbox (
 workspace_id uuid not null, job_id uuid not null, dispatch_generation bigint not null,
 state text not null default 'pending' check(state in ('pending','sent')),
 task_name text, next_attempt_at timestamptz not null default now(), sent_at timestamptz,
 created_at timestamptz not null default now(),
 primary key(workspace_id,job_id,dispatch_generation),
 foreign key(workspace_id,job_id) references public.ap_mail_jobs(workspace_id,id)
);
create table public.ap_mail_preliminary (
 workspace_id uuid not null, receipt_id uuid not null, statement_id uuid not null,
 revision_id uuid not null, source_pin jsonb not null, parser_version text not null,
 extraction_digest text not null, rows jsonb not null check(jsonb_typeof(rows)='array'),
 created_at timestamptz not null default now(),
 primary key(workspace_id,receipt_id),
 foreign key(workspace_id,receipt_id) references public.ap_mail_receipts(workspace_id,id),
 foreign key(workspace_id,statement_id) references public.ap_statements(workspace_id,id)
);

do $permissions$
declare name text;
begin
 foreach name in array array['connections','messages','receipts','jobs','processor_slots','attempts','outbox','preliminary'] loop
  execute format('alter table public.ap_mail_%I enable row level security',name);
  execute format('revoke all on public.ap_mail_%I from public,anon,authenticated',name);
  execute format('grant select,insert,update on public.ap_mail_%I to service_role',name);
 end loop;
end $permissions$;
grant usage,select on sequence public.ap_mail_attempts_id_seq to service_role;

create function public.ap_mail_mutate(p_operation text,p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare c ap_mail_connections; j ap_mail_jobs; r ap_mail_receipts; s ap_mail_processor_slots;
 item jsonb; f jsonb; result jsonb; cached ap_requests; ident uuid; v_reason text; changed integer; v_allowed text; v_required text;
begin
 if p_workspace is null or p_request_id is null or p_payload_hash is null or p_payload_hash !~ '^[a-f0-9]{64}$'
  or jsonb_typeof(p_data) is distinct from 'object' or octet_length(p_data::text)>1048576 then raise exception 'invalid'; end if;
 v_allowed=case p_operation
  when 'inventory' then 'connection_id expected_generation expected_version expected_cursor messages receipts next_cursor completed'
  when 'claim' then 'job_id dispatch_generation' when 'heartbeat' then 'claim'
  when 'record_original' then 'claim sha256 object_key size' when 'save_extraction' then 'claim doc parser_version extraction_digest'
  when 'needs_attention' then 'claim reason' when 'release_retry' then 'claim reason delay_seconds' when 'finish' then 'claim status reason'
  when 'retry' then 'receipt_id expected_version' when 'requeue' then 'receipt_id expected_version'
  when 'pause' then 'connection_id expected_version paused' when 'reconcile' then 'limit'
  when 'outbox_sent' then 'job_id dispatch_generation task_name' when 'outbox_delay' then 'job_id dispatch_generation delay_seconds' end;
 if p_operation='sync_error' then v_allowed='connection_id expected_generation reason'; end if;
 v_required=case p_operation when 'inventory' then 'connection_id expected_generation expected_version expected_cursor messages receipts next_cursor'
  when 'finish' then 'claim status' else v_allowed end;
 if v_allowed is null or p_data-string_to_array(v_allowed,' ')<>'{}'::jsonb or not(p_data ?& string_to_array(v_required,' ')) then raise exception 'invalid'; end if;
 perform pg_advisory_xact_lock(hashtext('ap-mail:'||p_workspace::text));
 if not exists(select 1 from ap_workspaces where id=p_workspace and mail_schema_version=1) then raise exception 'not_configured'; end if;
 select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
 if found then
  if cached.payload_hash<>p_payload_hash then raise exception 'conflict'; end if;
  return cached.response;
 end if;

 if p_operation='inventory' then
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=(p_data->>'connection_id')::uuid for update;
  if not found then raise exception 'not_found'; end if;
  if not c.active or c.paused then raise exception 'paused'; end if;
  if c.version is distinct from (p_data->>'expected_version')::bigint or c.generation is distinct from (p_data->>'expected_generation')::bigint or
   c.cursor is distinct from p_data->'expected_cursor' then raise exception 'conflict'; end if;
  if jsonb_typeof(p_data->'messages') is distinct from 'array' or jsonb_array_length(p_data->'messages')>100 or
   jsonb_typeof(p_data->'receipts') is distinct from 'array' or jsonb_array_length(p_data->'receipts')>200 or
   jsonb_typeof(p_data->'next_cursor') is distinct from 'object' then raise exception 'invalid'; end if;
  for item in select value from jsonb_array_elements(p_data->'messages') loop
   insert into ap_mail_messages(workspace_id,connection_id,account_id,message_id,thread_id,received_at,sender,subject,eligible,error_code)
    values(p_workspace,c.id,c.account_id,item->>'message_id',item->>'thread_id',(item->>'received_at')::timestamptz,
     coalesce(item->>'sender',''),coalesce(item->>'subject',''),(item->>'eligible')::boolean,item->>'error_code')
    on conflict(workspace_id,account_id,message_id) do update set eligible=ap_mail_messages.eligible or excluded.eligible,
     sender=coalesce(nullif(excluded.sender,''),ap_mail_messages.sender),subject=coalesce(nullif(excluded.subject,''),ap_mail_messages.subject),
     received_at=coalesce(ap_mail_messages.received_at,excluded.received_at),error_code=excluded.error_code;
  end loop;
  for item in select value from jsonb_array_elements(p_data->'receipts') loop
   if item->>'status' not in ('queued','needs_attention','skipped') then raise exception 'invalid'; end if;
   insert into ap_mail_receipts(id,workspace_id,connection_id,account_id,message_id,part_path,filename,mime_type,declared_size,attachment_id,status,reason)
    values((item->>'id')::uuid,p_workspace,c.id,c.account_id,item->>'message_id',item->>'part_path',item->>'filename',
     item->>'mime_type',(item->>'declared_size')::integer,item->>'attachment_id',item->>'status',item->>'reason')
    on conflict(workspace_id,account_id,message_id,part_path) do nothing;
   select * into r from ap_mail_receipts where workspace_id=p_workspace and account_id=c.account_id and
    message_id=item->>'message_id' and part_path=item->>'part_path';
   if r.id<>(item->>'id')::uuid then raise exception 'conflict'; end if;
   if r.status='queued' then
    insert into ap_mail_jobs(id,workspace_id,receipt_id,connection_id,connection_generation)
     values(r.id,p_workspace,r.id,c.id,c.generation) on conflict(receipt_id) do nothing;
    insert into ap_mail_outbox(workspace_id,job_id,dispatch_generation)
     select p_workspace,id,dispatch_generation from ap_mail_jobs where receipt_id=r.id and state='queued'
     on conflict do nothing;
   end if;
  end loop;
  update ap_mail_connections set cursor=p_data->'next_cursor',version=version+1,last_checked_at=now(),error_code=null,
   last_success_at=case when coalesce((p_data->>'completed')::boolean,false) then now() else last_success_at end where id=c.id;
  result=jsonb_build_object('version',c.version+1);

 elsif p_operation='claim' then
  select * into j from ap_mail_jobs where workspace_id=p_workspace and id=(p_data->>'job_id')::uuid for update;
  if not found then raise exception 'not_found'; end if;
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=j.connection_id;
  insert into ap_mail_processor_slots(workspace_id) values(p_workspace) on conflict do nothing;
  select * into s from ap_mail_processor_slots where workspace_id=p_workspace for update;
  result=jsonb_build_object('claim',null);
  if c.active and not c.paused and c.generation=j.connection_generation and j.state='queued' and j.attempts<3 and
   j.next_retry_at<=now() and j.dispatch_generation=(p_data->>'dispatch_generation')::bigint and s.lease_until<=now() then
   update ap_mail_processor_slots set job_id=j.id,generation=generation+1,lease_until=now()+interval '60 seconds'
    where workspace_id=p_workspace returning * into s;
   update ap_mail_jobs set state='running',attempts=attempts+1,lease_generation=lease_generation+1,
    slot_generation=s.generation,lease_until=s.lease_until,updated_at=now() where id=j.id returning * into j;
   update ap_mail_receipts set status='scanning',reason=null,version=version+1,updated_at=now() where id=j.receipt_id;
   insert into ap_mail_attempts(workspace_id,job_id,dispatch_generation,lease_generation,slot_generation,event)
    values(p_workspace,j.id,j.dispatch_generation,j.lease_generation,s.generation,'claimed');
   result=jsonb_build_object('claim',jsonb_build_object('job_id',j.id,'receipt_id',j.receipt_id,'connection_generation',j.connection_generation,
    'dispatch_generation',j.dispatch_generation,'lease_generation',j.lease_generation,'slot_generation',s.generation,'lease_until',j.lease_until,'mode',j.mode));
  end if;

 elsif p_operation in ('heartbeat','record_original','save_extraction','needs_attention','release_retry','finish') then
  f=p_data->'claim';
  select * into j from ap_mail_jobs where workspace_id=p_workspace and id=(f->>'job_id')::uuid for update;
  select * into s from ap_mail_processor_slots where workspace_id=p_workspace for update;
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=j.connection_id;
  if j.id is null or s.job_id is distinct from j.id or j.state<>'running' or j.lease_until<=now() or s.lease_until<=now() or
   j.receipt_id is distinct from (f->>'receipt_id')::uuid or
   j.connection_generation is distinct from (f->>'connection_generation')::bigint or c.generation<>j.connection_generation or not c.active or
   j.dispatch_generation is distinct from (f->>'dispatch_generation')::bigint or
   j.lease_generation is distinct from (f->>'lease_generation')::bigint or
   s.generation is distinct from (f->>'slot_generation')::bigint or j.slot_generation<>s.generation then raise exception 'stale_claim'; end if;
  select * into r from ap_mail_receipts where id=j.receipt_id and workspace_id=p_workspace for update;
  if p_operation='heartbeat' then
   update ap_mail_jobs set lease_until=now()+interval '60 seconds',updated_at=now() where id=j.id returning * into j;
   update ap_mail_processor_slots set lease_until=j.lease_until where workspace_id=p_workspace;
   result=jsonb_build_object('claim',f||jsonb_build_object('lease_until',j.lease_until));
  elsif p_operation='record_original' then
   if jsonb_typeof(p_data->'size') is distinct from 'number' or coalesce(p_data->>'sha256','') !~ '^[a-f0-9]{64}$' or p_data->>'object_key' is distinct from
    p_workspace::text||'/pdf/'||(p_data->>'sha256')||'.pdf' or (p_data->>'size')::integer not between 1 and 20971520 then raise exception 'invalid'; end if;
   if r.sha256 is not null and (r.sha256<>p_data->>'sha256' or r.actual_size<>(p_data->>'size')::integer) then raise exception 'conflict'; end if;
   update ap_mail_receipts set sha256=p_data->>'sha256',original_object_key=p_data->>'object_key',actual_size=(p_data->>'size')::integer,
    updated_at=now() where id=r.id;
   result=jsonb_build_object('recorded',true);
  elsif p_operation='save_extraction' then
   if r.sha256 is null or jsonb_typeof(p_data->'doc') is distinct from 'object' or
    p_data->'doc'->'confirmed' is distinct from 'false'::jsonb or jsonb_typeof(p_data->'doc'->'rows') is distinct from 'array' or
    jsonb_array_length(p_data->'doc'->'rows')=0 or coalesce(p_data->>'parser_version','')='' then raise exception 'invalid'; end if;
   if r.extraction is not null and r.extraction is distinct from p_data->'doc' then raise exception 'conflict'; end if;
   update ap_mail_receipts set extraction=p_data->'doc',extraction_digest=p_data->>'extraction_digest',parser_version=p_data->>'parser_version',updated_at=now() where id=r.id;
   result=jsonb_build_object('recorded',true);
  else
   v_reason=p_data->>'reason';
   if v_reason is not null and v_reason not in ('invalid','auth','denied','wrong_account','label_missing','not_found','quota','unavailable','limit',
     'unreadable','conflict','stale_source','stale_claim','paused','exhausted','storage','similar','waiting_source','not_configured','withdrawn') then raise exception 'invalid'; end if;
   if p_operation='release_retry' then
    if coalesce((p_data->>'delay_seconds')::integer,-1) not between 0 and 3600 then raise exception 'invalid'; end if;
    update ap_mail_jobs set state=case when attempts>=3 then 'attention' else 'queued' end,
     next_retry_at=now()+make_interval(secs=>(p_data->>'delay_seconds')::integer),lease_until='-infinity',updated_at=now() where id=j.id;
    update ap_mail_receipts set status=case when j.attempts>=3 then 'needs_attention' else 'queued' end,
     reason=case when j.attempts>=3 then 'exhausted' else v_reason end,version=version+1,updated_at=now() where id=r.id;
   elsif p_operation='needs_attention' then
    update ap_mail_jobs set state='attention',lease_until='-infinity',updated_at=now() where id=j.id;
    update ap_mail_receipts set status='needs_attention',reason=coalesce(v_reason,'unavailable'),version=version+1,updated_at=now() where id=r.id;
   else
    if p_data->>'status' not in ('awaiting_review','already_imported','skipped') or
     (p_data->>'status'<>'skipped' and r.statement_id is null) then raise exception 'invalid'; end if;
    update ap_mail_jobs set state='done',lease_until='-infinity',updated_at=now() where id=j.id;
    update ap_mail_receipts set status=p_data->>'status',reason=v_reason,version=version+1,
     imported_at=coalesce(imported_at,now()),updated_at=now() where id=r.id;
   end if;
   update ap_mail_processor_slots set job_id=null,lease_until='-infinity' where workspace_id=p_workspace;
   insert into ap_mail_attempts(workspace_id,job_id,dispatch_generation,lease_generation,slot_generation,event,reason)
    values(p_workspace,j.id,j.dispatch_generation,j.lease_generation,s.generation,p_operation,v_reason);
   result=jsonb_build_object('saved',true);
  end if;

 elsif p_operation='sync_error' then
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=(p_data->>'connection_id')::uuid for update;
  if not found then raise exception 'not_found'; end if;
  if c.generation is distinct from (p_data->>'expected_generation')::bigint then raise exception 'conflict'; end if;
  if coalesce(p_data->>'reason','') not in ('invalid','auth','denied','wrong_account','label_missing','not_found','quota',
    'unavailable','limit','unreadable','conflict','paused','not_configured') then raise exception 'invalid'; end if;
  update ap_mail_connections set error_code=p_data->>'reason',last_checked_at=now() where id=c.id;
  result=jsonb_build_object('saved',true);
 elsif p_operation='pause' then
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=(p_data->>'connection_id')::uuid for update;
  if not found then raise exception 'not_found'; end if;
  if c.version is distinct from (p_data->>'expected_version')::bigint then raise exception 'conflict'; end if;
  if jsonb_typeof(p_data->'paused') is distinct from 'boolean' then raise exception 'invalid'; end if;
  update ap_mail_connections set paused=(p_data->>'paused')::boolean,version=version+1 where id=c.id;
  result=jsonb_build_object('version',c.version+1);

 elsif p_operation in ('retry','requeue') then
  select * into r from ap_mail_receipts where workspace_id=p_workspace and id=(p_data->>'receipt_id')::uuid for update;
  if not found then raise exception 'not_found'; end if;
  if r.version is distinct from (p_data->>'expected_version')::bigint then raise exception 'conflict'; end if;
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=r.connection_id;
  if not c.active or c.paused then raise exception 'paused'; end if;
  select * into j from ap_mail_jobs where workspace_id=p_workspace and receipt_id=r.id for update;
  if j.state='running' and j.lease_until>now() then raise exception 'conflict'; end if;
  if not found then
   insert into ap_mail_jobs(id,workspace_id,receipt_id,connection_id,connection_generation) values(r.id,p_workspace,r.id,c.id,c.generation) returning * into j;
  else
   update ap_mail_jobs set state='queued',connection_generation=c.generation,dispatch_generation=dispatch_generation+1,
    attempts=case when p_operation='retry' then 0 else attempts end,lease_until='-infinity',next_retry_at=now(),updated_at=now(),
    mode=case when r.extraction is not null then 'recompare' else 'extract' end where id=j.id returning * into j;
  end if;
  update ap_mail_receipts set status='queued',reason=null,version=version+1,updated_at=now() where id=r.id;
  insert into ap_mail_outbox(workspace_id,job_id,dispatch_generation) values(p_workspace,j.id,j.dispatch_generation) on conflict do nothing;
  result=jsonb_build_object('version',r.version+1,'dispatch_generation',j.dispatch_generation);

 elsif p_operation='reconcile' then
  if coalesce((p_data->>'limit')::integer,0) not between 1 and 100 then raise exception 'invalid'; end if;
  changed=0;
  for j in select mj.* from ap_mail_jobs mj join ap_mail_connections mc on mc.id=mj.connection_id and mc.workspace_id=mj.workspace_id
    where mj.workspace_id=p_workspace and mj.state in ('queued','running') and
     ((mj.state='running' and mj.lease_until<=now()) or not mc.active or mc.generation<>mj.connection_generation)
    order by mj.id limit (p_data->>'limit')::integer for update of mj loop
   select * into c from ap_mail_connections where workspace_id=p_workspace and id=j.connection_id;
   v_reason=case when not c.active or c.generation<>j.connection_generation then 'wrong_account' when j.attempts>=3 then 'exhausted' else null end;
   update ap_mail_jobs set state=case when v_reason is not null then 'attention' else 'queued' end,dispatch_generation=dispatch_generation+1,
    lease_until='-infinity',next_retry_at=now(),updated_at=now() where id=j.id returning * into j;
   update ap_mail_receipts set status=case when v_reason is not null then 'needs_attention' else 'queued' end,
    reason=v_reason,version=version+1,updated_at=now() where id=j.receipt_id;
   update ap_mail_processor_slots set job_id=null,lease_until='-infinity' where workspace_id=p_workspace and job_id=j.id;
   if j.state='queued' then insert into ap_mail_outbox(workspace_id,job_id,dispatch_generation) values(p_workspace,j.id,j.dispatch_generation) on conflict do nothing; end if;
   changed=changed+1;
  end loop;
  result=jsonb_build_object('recovered',changed);

 elsif p_operation in ('outbox_sent','outbox_delay') then
  if p_operation='outbox_sent' then
   update ap_mail_outbox set state='sent',task_name=p_data->>'task_name',sent_at=now()
    where workspace_id=p_workspace and job_id=(p_data->>'job_id')::uuid and dispatch_generation=(p_data->>'dispatch_generation')::bigint;
  else
   if coalesce((p_data->>'delay_seconds')::integer,-1) not between 0 and 3600 then raise exception 'invalid'; end if;
   update ap_mail_outbox set next_attempt_at=now()+make_interval(secs=>(p_data->>'delay_seconds')::integer)
    where workspace_id=p_workspace and job_id=(p_data->>'job_id')::uuid and dispatch_generation=(p_data->>'dispatch_generation')::bigint;
  end if;
  result=jsonb_build_object('saved',true);
 else raise exception 'invalid';
 end if;
 insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,result);
 return result;
end $$;
revoke all on function public.ap_mail_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_mail_mutate(text,uuid,uuid,text,jsonb) to service_role;

create function public.ap_mail_read(p_operation text,p_workspace uuid,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare c ap_mail_connections; r ap_mail_receipts; result jsonb; v_limit integer;
begin
 if jsonb_typeof(p_data) is distinct from 'object' then raise exception 'invalid'; end if;
 if p_operation='connection' then
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=(p_data->>'connection_id')::uuid;
  return jsonb_build_object('connection',case when c.id is not null then to_jsonb(c) else null end);
 elsif p_operation='receipt' then
  select * into r from ap_mail_receipts where workspace_id=p_workspace and id=(p_data->>'receipt_id')::uuid;
  if not found then raise exception 'not_found'; end if;
  return to_jsonb(r);
 elsif p_operation='messages' then
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=(p_data->>'connection_id')::uuid;
  if not found then raise exception 'not_found'; end if;
  if jsonb_typeof(p_data->'ids') is distinct from 'array' or jsonb_array_length(p_data->'ids')>100 then raise exception 'invalid'; end if;
  select jsonb_agg(to_jsonb(items)) into result from (select message_id,eligible,error_code,received_at from ap_mail_messages
   where workspace_id=p_workspace and account_id=c.account_id and message_id in (select jsonb_array_elements_text(p_data->'ids'))) items;
  return jsonb_build_object('items',coalesce(result,'[]'));
 elsif p_operation='status' then
  select * into c from ap_mail_connections where workspace_id=p_workspace and active;
  select jsonb_object_agg(status,n) into result from (select status,count(*) n from ap_mail_receipts where workspace_id=p_workspace group by status) counts;
  return jsonb_build_object('connection',case when c.id is null then null else jsonb_build_object('id',c.id,'email',c.email,
   'label',c.label_name,'paused',c.paused,'version',c.version,'generation',c.generation,'lastSuccessAt',c.last_success_at,'error',c.error_code) end,
   'counts',coalesce(result,'{}')||jsonb_build_object('message_attention',(select count(*) from ap_mail_messages where workspace_id=p_workspace and error_code is not null)));
 elsif p_operation in ('receipts','outbox') then
  v_limit=(p_data->>'limit')::integer;
  if v_limit is null or v_limit<1 or v_limit>(case when p_operation='receipts' then 50 else 100 end) then raise exception 'invalid'; end if;
  if p_operation='receipts' then
   select jsonb_agg(to_jsonb(items)) into result from (
    select ar.id,ar.status,ar.reason,ar.version,ar.filename,ar.statement_id,ar.discovered_at,ar.imported_at,m.received_at,m.sender,m.subject
    from ap_mail_receipts ar join ap_mail_messages m on m.workspace_id=ar.workspace_id and m.account_id=ar.account_id and m.message_id=ar.message_id
    where ar.workspace_id=p_workspace and ((p_data->>'cursor') is null or ar.id>(p_data->>'cursor')::uuid)
    order by ar.id limit v_limit) items;
  else
   select jsonb_agg(to_jsonb(items)) into result from (
    select o.* from ap_mail_outbox o join ap_mail_jobs j on j.workspace_id=o.workspace_id and j.id=o.job_id
    join ap_mail_connections mc on mc.workspace_id=j.workspace_id and mc.id=j.connection_id
    where o.workspace_id=p_workspace and o.dispatch_generation=j.dispatch_generation and j.state='queued' and
     mc.active and not mc.paused and mc.generation=j.connection_generation and o.next_attempt_at<=now() and
     ((p_data->>'cursor') is null or (o.job_id,o.dispatch_generation)>((p_data->'cursor'->>'job_id')::uuid,(p_data->'cursor'->>'dispatch_generation')::bigint))
    order by o.job_id,o.dispatch_generation limit v_limit) items;
  end if;
  return jsonb_build_object('items',coalesce(result,'[]'),'nextCursor',case when jsonb_array_length(coalesce(result,'[]'))=v_limit
   then case when p_operation='receipts' then result->-1->'id' else jsonb_build_object('job_id',result->-1->'job_id','dispatch_generation',result->-1->'dispatch_generation') end else null end);
 end if;
 raise exception 'invalid';
end $$;
revoke all on function public.ap_mail_read(text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.ap_mail_read(text,uuid,jsonb) to service_role;
commit;
