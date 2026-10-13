-- Private AP records. Apply only to an explicitly authorized project.
begin;
create table public.ap_workspaces (
  id uuid primary key, active_import_id uuid, created_at timestamptz not null default now()
);
create table public.ap_bill_imports (
  id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.ap_workspaces(id),
  file_hash text not null check(file_hash ~ '^[0-9a-f]{64}$'), original_object_key text not null,
  metadata jsonb not null, record_count integer not null check(record_count between 1 and 100000),
  state text not null default 'staging' check(state in ('staging','ready')), created_at timestamptz not null default now(),
  unique(workspace_id,file_hash), unique(workspace_id,id)
);
alter table public.ap_workspaces add constraint ap_active_import_fk
  foreign key(id,active_import_id) references public.ap_bill_imports(workspace_id,id);
create table public.ap_bill_records (
  workspace_id uuid not null, import_id uuid not null, ordinal integer not null check(ordinal between 0 and 99999),
  record jsonb not null check(jsonb_typeof(record)='object'), primary key(import_id,ordinal),
  foreign key(workspace_id,import_id) references public.ap_bill_imports(workspace_id,id)
);
create table public.ap_statements (
  id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.ap_workspaces(id),
  file_hash text check(file_hash ~ '^[0-9a-f]{64}$'), original_object_key text,
  filename text not null, version integer not null default 0 check(version>=0), current_revision_id uuid,
  completed boolean not null default false, archived boolean not null default false,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(workspace_id,file_hash), unique(workspace_id,id)
);
create table public.ap_statement_revisions (
  id uuid primary key default gen_random_uuid(), workspace_id uuid not null, statement_id uuid not null,
  version integer not null check(version>0), doc jsonb not null, resolutions jsonb not null default '{}',
  import_id uuid, mapping_snapshot jsonb not null default '{}', results jsonb not null default '[]',
  rule_version text not null, created_at timestamptz not null default now(),
  unique(statement_id,version), unique(workspace_id,id),
  foreign key(workspace_id,statement_id) references public.ap_statements(workspace_id,id),
  foreign key(workspace_id,import_id) references public.ap_bill_imports(workspace_id,id)
);
alter table public.ap_statements add constraint ap_current_revision_fk
  foreign key(workspace_id,current_revision_id) references public.ap_statement_revisions(workspace_id,id);
create table public.ap_completion_events (
  id uuid primary key default gen_random_uuid(), workspace_id uuid not null, statement_id uuid not null,
  revision_id uuid not null, event text not null check(event in ('completed','reopened')),
  initials text check(initials ~ '^[A-Z]{1,10}$'), status text not null, note text not null default '',
  vendor text, statement_date date,
  created_at timestamptz not null default now(),
  foreign key(workspace_id,statement_id) references public.ap_statements(workspace_id,id),
  foreign key(workspace_id,revision_id) references public.ap_statement_revisions(workspace_id,id),
  check(event<>'completed' or initials is not null)
);
create index ap_history_order on public.ap_completion_events(workspace_id,created_at desc,id desc);
create table public.ap_vendor_mappings (
  workspace_id uuid not null references public.ap_workspaces(id), vendor text not null, bill_vendor text not null,
  version integer not null default 1, updated_at timestamptz not null default now(), primary key(workspace_id,vendor)
);
create table public.ap_requests (
  workspace_id uuid not null references public.ap_workspaces(id), request_id uuid not null,
  payload_hash text not null check(payload_hash ~ '^[0-9a-f]{64}$'), response jsonb not null,
  created_at timestamptz not null default now(), primary key(workspace_id,request_id)
);
create table public.ap_uploads (
  id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.ap_workspaces(id),
  session_nonce uuid not null, metadata jsonb not null, chunks jsonb not null default '{}',
  state text not null default 'staging' check(state in ('staging','ready')), object_key text,
  created_at timestamptz not null default now(), unique(workspace_id,id)
);
-- Nonfinancial attempt bookkeeping, used before unlocking.
create table public.ap_access_limits (
  workspace_id uuid not null, key text not null, events jsonb not null default '[]',
  blocked_until timestamptz not null default '-infinity', primary key(workspace_id,key)
);

create function public.ap_immutable_history() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin raise exception 'immutable_history'; end;
$$;
create trigger ap_revision_immutable before update or delete on public.ap_statement_revisions
  for each row execute function public.ap_immutable_history();
create trigger ap_completion_immutable before update or delete on public.ap_completion_events
  for each row execute function public.ap_immutable_history();
create trigger ap_bill_record_immutable before update or delete on public.ap_bill_records
  for each row execute function public.ap_immutable_history();
create function public.ap_ready_import_immutable() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
  if old.state='ready' and (tg_op='DELETE' or to_jsonb(new) is distinct from to_jsonb(old)) then raise exception 'immutable_import'; end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$$;
create trigger ap_import_immutable before update or delete on public.ap_bill_imports
  for each row execute function public.ap_ready_import_immutable();

create function public.ap_mutate(p_operation text,p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare
  cached ap_requests%rowtype; item ap_statements%rowtype; previous ap_statement_revisions%rowtype;
  source ap_bill_imports%rowtype; mapped ap_vendor_mappings%rowtype;
  upload ap_uploads%rowtype; old_chunk jsonb; part integer;
  sid uuid; rid uuid; iid uuid; reply jsonb; next_version integer; doc_value jsonb; result_status text;
begin
  if p_payload_hash !~ '^[0-9a-f]{64}$' or jsonb_typeof(p_data)<>'object' then raise exception 'validation'; end if;
  perform 1 from ap_workspaces where id=p_workspace for update;
  if not found then raise exception 'workspace_unavailable'; end if;
  select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
  if found then
    if cached.payload_hash<>p_payload_hash then raise exception 'request_conflict'; end if;
    return cached.response;
  end if;
  if p_operation='begin_upload' then
    if coalesce(p_data->'metadata'->>'kind','') not in ('pdf','csv') or
       coalesce(p_data->'metadata'->>'file_hash','') !~ '^[0-9a-f]{64}$' or
       (p_data->'metadata'->>'size')::integer not between 1 and 20971520 then raise exception 'validation'; end if;
    sid=(p_data->>'upload_id')::uuid;
    insert into ap_uploads(id,workspace_id,session_nonce,metadata)
      values(sid,p_workspace,(p_data->>'session_nonce')::uuid,p_data->'metadata');
    reply=jsonb_build_object('upload_id',sid,'state','staging');
  elsif p_operation in ('put_chunk','finish_upload') then
    sid=(p_data->>'upload_id')::uuid;
    select * into upload from ap_uploads where id=sid and workspace_id=p_workspace for update;
    if not found or upload.session_nonce is distinct from (p_data->>'session_nonce')::uuid then raise exception 'upload_denied'; end if;
    if p_operation='put_chunk' then
      if upload.state<>'staging' then raise exception 'upload_immutable'; end if;
      part=(p_data->>'index')::integer;
      if part not between 0 and 79 or part*262144 >= (upload.metadata->>'size')::integer or
         coalesce(p_data->>'chunk_hash','') !~ '^[0-9a-f]{64}$' or
         (p_data->>'size')::integer is distinct from least(262144,(upload.metadata->>'size')::integer-part*262144)
         then raise exception 'validation'; end if;
      old_chunk=upload.chunks->part::text;
      if old_chunk is not null and old_chunk<>jsonb_build_object('hash',p_data->>'chunk_hash','size',(p_data->>'size')::integer) then raise exception 'request_conflict'; end if;
      if old_chunk is null and part<>(select count(*) from jsonb_object_keys(upload.chunks)) then raise exception 'chunk_order'; end if;
      if (select coalesce(sum((e.value->>'size')::integer),0) from jsonb_each(upload.chunks) e)+(case when old_chunk is null then (p_data->>'size')::integer else 0 end)>(upload.metadata->>'size')::integer then raise exception 'validation'; end if;
      update ap_uploads set chunks=chunks||jsonb_build_object(part::text,jsonb_build_object('hash',p_data->>'chunk_hash','size',(p_data->>'size')::integer)) where id=sid;
      reply=jsonb_build_object('upload_id',sid,'index',part);
    else
      if coalesce(p_data->>'object_key','')<>p_workspace::text||'/'||(upload.metadata->>'kind')||'/'||(upload.metadata->>'file_hash')||'.'||(upload.metadata->>'kind') then raise exception 'validation'; end if;
      if (select coalesce(sum((e.value->>'size')::integer),0) from jsonb_each(upload.chunks) e)<>(upload.metadata->>'size')::integer then raise exception 'upload_incomplete'; end if;
      update ap_uploads set state='ready',object_key=p_data->>'object_key' where id=sid;
      reply=jsonb_build_object('upload_id',sid,'state','ready');
    end if;
  elsif p_operation='register_statement' then
    if p_data->>'file_hash' !~ '^[0-9a-f]{64}$' or nullif(p_data->>'original_object_key','') is null then raise exception 'validation'; end if;
    select * into item from ap_statements where workspace_id=p_workspace and file_hash=p_data->>'file_hash';
    if found then
      reply=jsonb_build_object('statement_id',item.id,'version',item.version,'duplicate',true);
    else
      sid=(p_data->>'statement_id')::uuid; rid=gen_random_uuid();
      doc_value=p_data->'doc';
      if jsonb_typeof(doc_value)<>'object' or doc_value->>'id'<>sid::text then raise exception 'validation'; end if;
      insert into ap_statements(id,workspace_id,file_hash,original_object_key,filename)
        values(sid,p_workspace,p_data->>'file_hash',p_data->>'original_object_key',doc_value->>'filename');
      insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,rule_version)
        values(rid,p_workspace,sid,1,doc_value,'ap-match-v2');
      update ap_statements set version=1,current_revision_id=rid where id=sid;
      reply=jsonb_build_object('statement_id',sid,'version',1,'duplicate',false);
    end if;
  elsif p_operation in ('save_revision','complete_revision','reopen_statement','archive_statement') then
    sid=(p_data->>'statement_id')::uuid;
    select * into item from ap_statements where id=sid and workspace_id=p_workspace for update;
    if not found then raise exception 'not_found'; end if;
    if (p_data->>'expected_version')::integer is distinct from item.version then raise exception 'conflict'; end if;
    select * into previous from ap_statement_revisions where id=item.current_revision_id and workspace_id=p_workspace;
    next_version=item.version+1; rid=gen_random_uuid();
    if p_operation='save_revision' then
      if item.completed then raise exception 'completed_revision'; end if;
      iid=(p_data->>'import_id')::uuid;
      if iid is not null and not exists(select 1 from ap_bill_imports where id=iid and workspace_id=p_workspace and state='ready') then raise exception 'validation'; end if;
      doc_value=p_data->'doc';
      if jsonb_typeof(doc_value)<>'object' or doc_value->>'id'<>sid::text then raise exception 'validation'; end if;
      insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,resolutions,import_id,mapping_snapshot,results,rule_version)
        values(rid,p_workspace,sid,next_version,doc_value,
               (select coalesce(jsonb_object_agg(e.key,case when e.value->>'decision' is not null then (e.value-'at')||jsonb_build_object('at',now()) else e.value-'at' end),'{}') from jsonb_each(coalesce(p_data->'resolutions','{}')) e),iid,
               coalesce(p_data->'mapping_snapshot','{}'),coalesce(p_data->'results','[]'),p_data->>'rule_version');
    elsif p_operation='complete_revision' then
      if item.completed then raise exception 'completed_revision'; end if;
      if p_data->>'initials' !~ '^[A-Z]{1,10}$' or p_data->>'initials' is null then raise exception 'initials_required'; end if;
      if coalesce(previous.doc->>'confirmed','false')<>'true' or jsonb_array_length(previous.doc->'rows')=0 or jsonb_array_length(previous.results)=0 then raise exception 'extraction_unconfirmed'; end if;
      if exists(select 1 from jsonb_array_elements(previous.results) r where r->>'status'<>'matched' and
        (previous.resolutions->(r->>'id')->>'decision' is null or previous.resolutions->(r->>'id')->>'decision' not in
        ('Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed'))) then raise exception 'review_required'; end if;
      doc_value=previous.doc;
      insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,resolutions,import_id,mapping_snapshot,results,rule_version)
        values(rid,p_workspace,sid,next_version,doc_value,previous.resolutions,previous.import_id,previous.mapping_snapshot,previous.results,previous.rule_version);
      result_status=case when not exists(select 1 from jsonb_array_elements(previous.results) r where r->>'status'<>'matched') then 'reconciled'
        when exists(select 1 from jsonb_each(previous.resolutions) r where r.value->>'decision'<>'Reviewed — no action needed') then 'follow_up'
        else 'reviewed' end;
      insert into ap_completion_events(workspace_id,statement_id,revision_id,event,initials,status,note,vendor,statement_date)
        values(p_workspace,sid,rid,'completed',p_data->>'initials',result_status,coalesce(p_data->>'notes',''),doc_value->>'vendor',nullif(doc_value->>'statementDate','')::date);
      update ap_statements set completed=true where id=sid;
    elsif p_operation='reopen_statement' then
      if not item.completed then raise exception 'not_completed'; end if;
      insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,resolutions,import_id,mapping_snapshot,results,rule_version)
        values(rid,p_workspace,sid,next_version,previous.doc,'{}',previous.import_id,previous.mapping_snapshot,previous.results,previous.rule_version);
      insert into ap_completion_events(workspace_id,statement_id,revision_id,event,status)
        values(p_workspace,sid,rid,'reopened','draft');
      update ap_statements set completed=false,archived=false where id=sid;
    else
      -- Archiving changes list visibility, not the immutable reviewed revision.
      rid=item.current_revision_id;
      update ap_statements set archived=true where id=sid;
    end if;
    update ap_statements set version=next_version,current_revision_id=rid,updated_at=now() where id=sid;
    reply=jsonb_build_object('statement_id',sid,'version',next_version,'revision_id',rid);
  elsif p_operation='begin_import' then
    select * into source from ap_bill_imports where workspace_id=p_workspace and file_hash=p_data->>'file_hash';
    if found then reply=jsonb_build_object('import_id',source.id,'state',source.state,'duplicate',true);
    else
      iid=gen_random_uuid();
      insert into ap_bill_imports(id,workspace_id,file_hash,original_object_key,metadata,record_count)
        values(iid,p_workspace,p_data->>'file_hash',p_data->>'original_object_key',p_data->'metadata',(p_data->>'record_count')::integer);
      reply=jsonb_build_object('import_id',iid,'state','staging','duplicate',false);
    end if;
  elsif p_operation in ('append_records','activate_import') then
    iid=(p_data->>'import_id')::uuid;
    select * into source from ap_bill_imports where workspace_id=p_workspace and id=iid for update;
    if not found then raise exception 'not_found'; end if;
    if p_operation='append_records' then
      if source.state<>'staging' then raise exception 'import_immutable'; end if;
      if jsonb_array_length(p_data->'records') not between 1 and 500 then raise exception 'validation'; end if;
      if (p_data->>'start')::integer<0 or (p_data->>'start')::integer+jsonb_array_length(p_data->'records')>source.record_count then raise exception 'validation'; end if;
      if exists(select 1 from jsonb_array_elements(p_data->'records') with ordinality r(value,n)
                join ap_bill_records b on b.import_id=iid and b.ordinal=(p_data->>'start')::integer+r.n-1 where b.record<>r.value) then raise exception 'request_conflict'; end if;
      insert into ap_bill_records(workspace_id,import_id,ordinal,record)
        select p_workspace,iid,(p_data->>'start')::integer+r.n-1,r.value from jsonb_array_elements(p_data->'records') with ordinality r(value,n)
        on conflict(import_id,ordinal) do nothing;
    else
      if (select count(*) from ap_bill_records where import_id=iid and workspace_id=p_workspace)<>source.record_count then raise exception 'import_incomplete'; end if;
      update ap_bill_imports set state='ready' where id=iid;
      update ap_workspaces set active_import_id=iid where id=p_workspace;
    end if;
    reply=jsonb_build_object('import_id',iid,'state',case when p_operation='activate_import' then 'ready' else source.state end);
  elsif p_operation='save_mapping' then
    select * into mapped from ap_vendor_mappings where workspace_id=p_workspace and vendor=p_data->>'vendor' for update;
    if coalesce(mapped.version,0) is distinct from (p_data->>'expected_version')::integer then raise exception 'conflict'; end if;
    if nullif(btrim(p_data->>'vendor'),'') is null or nullif(btrim(p_data->>'bill_vendor'),'') is null then raise exception 'validation'; end if;
    insert into ap_vendor_mappings(workspace_id,vendor,bill_vendor,version) values(p_workspace,p_data->>'vendor',p_data->>'bill_vendor',coalesce(mapped.version,0)+1)
      on conflict(workspace_id,vendor) do update set bill_vendor=excluded.bill_vendor,version=excluded.version,updated_at=now();
    reply=jsonb_build_object('version',coalesce(mapped.version,0)+1);
  else raise exception 'unsupported_operation';
  end if;
  insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,reply);
  return reply;
end;
$$;

-- Fixed operations expose the same transactional contract to the server adapter.
create function public.ap_register_statement(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('register_statement',$1,$2,$3,$4)$$;
create function public.ap_begin_upload(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('begin_upload',$1,$2,$3,$4)$$;
create function public.ap_put_chunk(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('put_chunk',$1,$2,$3,$4)$$;
create function public.ap_finish_upload(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('finish_upload',$1,$2,$3,$4)$$;
create function public.ap_save_revision(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('save_revision',$1,$2,$3,$4)$$;
create function public.ap_complete_revision(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('complete_revision',$1,$2,$3,$4)$$;
create function public.ap_reopen_statement(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('reopen_statement',$1,$2,$3,$4)$$;
create function public.ap_archive_statement(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('archive_statement',$1,$2,$3,$4)$$;
create function public.ap_begin_import(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('begin_import',$1,$2,$3,$4)$$;
create function public.ap_append_records(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('append_records',$1,$2,$3,$4)$$;
create function public.ap_activate_import(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('activate_import',$1,$2,$3,$4)$$;
create function public.ap_save_mapping(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $$select public.ap_mutate('save_mapping',$1,$2,$3,$4)$$;

create function public.ap_begin_access_attempt(p_workspace uuid,p_nonce uuid) returns uuid
language plpgsql security definer set search_path=public,pg_temp as $$
declare t uuid=gen_random_uuid(); counter ap_access_limits%rowtype; bucket text; threshold integer; kept jsonb;
begin
  insert into ap_access_limits(workspace_id,key) values(p_workspace,'global'),(p_workspace,p_nonce::text) on conflict do nothing;
  perform 1 from ap_access_limits where workspace_id=p_workspace and key='global' for update;
  foreach bucket in array array['global',p_nonce::text] loop
    select * into counter from ap_access_limits where workspace_id=p_workspace and key=bucket for update;
    if counter.blocked_until>now() then return null; end if;
    select coalesce(jsonb_agg(e),'[]') into kept from jsonb_array_elements(counter.events) e where (e->>'at')::timestamptz>now()-interval '5 minutes';
    threshold=case when bucket='global' then 100 else 5 end;
    if jsonb_array_length(kept)>=threshold then
      update ap_access_limits set events=kept,blocked_until=now()+interval '5 minutes' where workspace_id=p_workspace and key=bucket;
      return null;
    end if;
  end loop;
  foreach bucket in array array['global',p_nonce::text] loop
    update ap_access_limits set events=(select coalesce(jsonb_agg(e),'[]') from jsonb_array_elements(events) e where (e->>'at')::timestamptz>now()-interval '5 minutes')
      ||jsonb_build_array(jsonb_build_object('id',t,'at',now(),'nonce',p_nonce)) where workspace_id=p_workspace and key=bucket;
  end loop;
  return t;
end;
$$;
create function public.ap_finish_access_attempt(p_workspace uuid,p_ticket uuid,p_success boolean) returns void
language plpgsql security definer set search_path=public,pg_temp as $$
declare nonce text; bucket text; threshold integer;
begin
  perform 1 from ap_access_limits where workspace_id=p_workspace and key='global' for update;
  select e->>'nonce' into nonce from ap_access_limits c,jsonb_array_elements(c.events) e where c.workspace_id=p_workspace and c.key='global' and e->>'id'=p_ticket::text;
  if nonce is null then raise exception 'invalid_attempt'; end if;
  foreach bucket in array array['global',nonce] loop
    if p_success then update ap_access_limits set events=(select coalesce(jsonb_agg(e),'[]') from jsonb_array_elements(events) e where e->>'id'<>p_ticket::text) where workspace_id=p_workspace and key=bucket;
    else
      threshold=case when bucket='global' then 100 else 5 end;
      update ap_access_limits set blocked_until=case when jsonb_array_length(events)>=threshold then now()+interval '5 minutes' else blocked_until end where workspace_id=p_workspace and key=bucket;
    end if;
  end loop;
end;
$$;

do $$ declare obj record; begin
  for obj in select tablename from pg_tables where schemaname='public' and tablename like 'ap\_%' escape '\' loop
    execute format('alter table public.%I enable row level security',obj.tablename);
    execute format('revoke all on table public.%I from public,anon,authenticated',obj.tablename);
    execute format('grant select,insert,update,delete on table public.%I to service_role',obj.tablename);
  end loop;
  for obj in select oid::regprocedure as signature from pg_proc where pronamespace='public'::regnamespace and proname like 'ap\_%' escape '\' loop
    execute format('revoke all on function %s from public,anon,authenticated',obj.signature);
    execute format('grant execute on function %s to service_role',obj.signature);
  end loop;
end $$;
commit;
