-- Additive compressed BILL snapshots. Apply only to an authorized project.
begin;
alter table public.ap_workspaces add column import_version bigint not null default 0;
alter table public.ap_bill_imports add column storage_format text not null default 'rows-v1'
  check(storage_format in ('rows-v1','snapshot-v2'));
alter table public.ap_bill_imports add column snapshot_manifest jsonb;
alter table public.ap_bill_imports drop constraint ap_bill_imports_record_count_check;
alter table public.ap_bill_imports add constraint ap_bill_imports_record_count_check
  check(record_count between 1 and case when storage_format='snapshot-v2' then 500000 else 100000 end);
alter table public.ap_bill_imports add constraint ap_bill_snapshot_manifest_check
  check(storage_format='rows-v1' or (jsonb_typeof(snapshot_manifest)='object'
    and snapshot_manifest->>'format'='snapshot-v2'
    and (snapshot_manifest->>'recordCount')::integer=record_count));

create function public.ap_bill_import_version() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
  new.import_version=old.import_version + case when new.active_import_id is distinct from old.active_import_id then 1 else 0 end;
  return new;
end $$;
create trigger ap_bill_import_version before update on public.ap_workspaces
  for each row execute function public.ap_bill_import_version();

create table public.ap_bill_jobs (
  id uuid primary key, workspace_id uuid not null references public.ap_workspaces(id), session_nonce uuid not null,
  generation uuid not null default gen_random_uuid(), expected_import_version bigint not null,
  state text not null default 'uploading', checkpoint integer not null default 0,
  lease_until timestamptz not null default now()+interval '1 hour', metadata jsonb not null,
  chunks jsonb not null default '{}', counts jsonb not null default '{}', import_id uuid,
  reserved_bytes bigint not null default 0 check(reserved_bytes>=0), reservation_bucket text,
  original_hash text, original_archive jsonb, created_at timestamptz not null default now(),
  unique(workspace_id,id), foreign key(workspace_id,import_id) references public.ap_bill_imports(workspace_id,id)
);
alter table public.ap_bill_jobs enable row level security;
revoke all on public.ap_bill_jobs from public,anon,authenticated;
grant select,insert,update,delete on public.ap_bill_jobs to service_role;

create function public.ap_bill_mutate(p_operation text,p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare
  home ap_workspaces%rowtype; job ap_bill_jobs%rowtype; source ap_bill_imports%rowtype;
  cached ap_requests%rowtype; result jsonb; mf jsonb; jid uuid; n bigint; used bigint; reserved bigint; reused boolean;
begin
  if p_payload_hash !~ '^[0-9a-f]{64}$' or jsonb_typeof(p_data)<>'object' then raise exception 'bill_incomplete'; end if;
  select * into home from ap_workspaces where id=p_workspace for update;
  if not found then raise exception 'bill_conflict'; end if;
  select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
  if found then
    if cached.payload_hash<>p_payload_hash then raise exception 'request_conflict'; end if;
    return cached.response;
  end if;
  jid=(p_data->>'job_id')::uuid;
  if p_operation='job_begin' then
    if exists(select 1 from ap_bill_jobs where workspace_id=p_workspace and lease_until>now() and state not in ('activated','abandoned')) then raise exception 'bill_conflict'; end if;
    if (p_data->>'compressed_size')::integer not between 1 and 33554432 or length(coalesce(p_data->>'filename','')) not between 1 and 1024 then raise exception 'bill_limit'; end if;
    insert into ap_bill_jobs(id,workspace_id,session_nonce,expected_import_version,metadata)
      values(jid,p_workspace,(p_data->>'session_nonce')::uuid,home.import_version,
        jsonb_build_object('filename',p_data->>'filename','compressed_size',(p_data->>'compressed_size')::integer,'as_of',p_data->>'as_of')) returning * into job;
    result=jsonb_build_object('job_id',job.id,'generation',job.generation,'expected_import_version',job.expected_import_version,'checkpoint',0,'state',job.state);
  else
    select * into job from ap_bill_jobs where id=jid and workspace_id=p_workspace for update;
    if not found or job.session_nonce is distinct from (p_data->>'session_nonce')::uuid or job.lease_until<=now() or job.state='abandoned' then raise exception 'bill_conflict'; end if;
    if p_operation='job_abandon' then
      if job.generation is distinct from (p_data->>'generation')::uuid or job.state='activated' then raise exception 'bill_conflict'; end if;
      update ap_bill_jobs set state='abandoned',reserved_bytes=0 where id=jid;
      result=jsonb_build_object('job_id',jid,'state','abandoned');
    elsif p_operation='quota_reserve' then
      if coalesce(p_data->>'bucket','')='' then raise exception 'bill_quota'; end if;
      perform pg_advisory_xact_lock(hashtext('ap-bill-quota:'||(p_data->>'bucket')));
      n=(p_data->>'requested_bytes')::bigint;
      select coalesce(sum((metadata->>'size')::bigint),0) into used from storage.objects where bucket_id=p_data->>'bucket';
      select coalesce(sum(reserved_bytes),0) into reserved from ap_bill_jobs where id<>jid and lease_until>now() and reservation_bucket=p_data->>'bucket';
      if n<0 or used+reserved+n>(p_data->>'budget_bytes')::bigint then raise exception 'bill_quota'; end if;
      update ap_bill_jobs set reserved_bytes=n,reservation_bucket=p_data->>'bucket' where id=jid;
      result=jsonb_build_object('used_bytes',used,'reserved_bytes',n,'warning',used+reserved+n>=0.8*(p_data->>'budget_bytes')::bigint);
    elsif p_operation='snapshot_stage' then
      if job.generation is distinct from (p_data->>'generation')::uuid or job.state='activated' then raise exception 'bill_conflict'; end if;
      mf=p_data->'manifest'; n=(mf->>'recordCount')::bigint;
      if mf->>'format'<>'snapshot-v2' or mf->>'parserVersion'<>'bill-csv-v1' or (mf->>'indexVersion')::integer<>1 or
        coalesce(mf->>'originalHash','') !~ '^[0-9a-f]{64}$' or n not between 1 and 500000 or
        (mf->>'originalBytes')::bigint not between 1 and 268435456 or
        (mf->>'sourceRowCount')::integer not between 1 and 750000 or
        n+(mf->>'collapsedRowCount')::integer+(mf->>'excludedRowCount')::integer<>(mf->>'sourceRowCount')::integer or
        (mf->'originalArchive'->>'bytes')::bigint not between 1 and 33554432 or
        (mf->'indexArchive'->>'bytes')::bigint not between 1 and 33554432 or
        (mf->'indexArchive'->>'expandedBytes')::bigint not between 1 and 536870912 or
        mf->'originalArchive'->>'key'<>p_workspace::text||'/bills/v2/'||(mf->>'originalHash')||'/'||(mf->'originalArchive'->>'hash')||'.csv.gz' or
        mf->'indexArchive'->>'key'<>p_workspace::text||'/bills/v2/'||(mf->>'originalHash')||'/'||(mf->'indexArchive'->>'hash')||'.sqlite.gz'
        then raise exception 'bill_incomplete'; end if;
      select * into source from ap_bill_imports where workspace_id=p_workspace and file_hash=mf->>'originalHash';
      reused=found;
      if not found then
        insert into ap_bill_imports(workspace_id,file_hash,original_object_key,metadata,record_count,state,storage_format,snapshot_manifest)
          values(p_workspace,mf->>'originalHash',mf->'originalArchive'->>'key',p_data->'metadata',n,'ready','snapshot-v2',mf) returning * into source;
      elsif source.state<>'ready' then raise exception 'bill_conflict'; end if;
      update ap_bill_jobs set state='prepared',import_id=source.id,original_hash=source.file_hash where id=jid;
      result=jsonb_build_object('job_id',jid,'import_id',source.id,'duplicate',reused,'alreadyCurrent',coalesce(home.active_import_id=source.id,false));
    elsif p_operation='snapshot_activate' then
      if job.state<>'prepared' or job.import_id is distinct from (p_data->>'import_id')::uuid then raise exception 'bill_incomplete'; end if;
      select * into source from ap_bill_imports where workspace_id=p_workspace and id=job.import_id and state='ready';
      if not found then raise exception 'bill_incomplete'; end if;
      if home.import_version is distinct from (p_data->>'expected_import_version')::bigint or home.import_version<>job.expected_import_version then raise exception 'bill_conflict'; end if;
      if source.created_at<job.created_at and home.active_import_id is distinct from source.id and coalesce((p_data->>'confirm_restore')::boolean,false) is not true then raise exception 'bill_conflict'; end if;
      update ap_workspaces set active_import_id=source.id where id=p_workspace returning * into home;
      update ap_bill_jobs set state='activated',reserved_bytes=0 where id=jid;
      result=jsonb_build_object('import_id',source.id,'import_version',home.import_version);
    elsif p_operation='job_checkpoint' then
      if job.generation is distinct from (p_data->>'generation')::uuid or job.checkpoint is distinct from (p_data->>'expected_checkpoint')::integer or job.state='activated' then raise exception 'bill_conflict'; end if;
      if p_data->>'next_checkpoint' is null or (p_data->>'next_checkpoint')::integer<>job.checkpoint+1 then raise exception 'bill_conflict'; end if;
      update ap_bill_jobs set checkpoint=checkpoint+1,state=p_data->>'state',counts=coalesce(p_data->'counts','{}'),lease_until=now()+interval '1 hour' where id=jid returning * into job;
      result=jsonb_build_object('job_id',jid,'generation',job.generation,'checkpoint',job.checkpoint,'state',job.state);
    else raise exception 'bill_incomplete'; end if;
  end if;
  insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,result);
  return result;
end $$;

do $$ declare operation text; begin
  foreach operation in array array['job_begin','job_checkpoint','job_abandon','snapshot_stage','snapshot_activate','quota_reserve'] loop
    execute format('create function public.ap_bill_%I(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb) returns jsonb language sql security definer set search_path=public,pg_temp as $fn$ select public.ap_bill_mutate(%L,p_workspace,p_request_id,p_payload_hash,p_data) $fn$',operation,operation);
    execute format('revoke all on function public.ap_bill_%I(uuid,uuid,text,jsonb) from public,anon,authenticated',operation);
    execute format('grant execute on function public.ap_bill_%I(uuid,uuid,text,jsonb) to service_role',operation);
  end loop;
end $$;
revoke all on function public.ap_bill_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_bill_mutate(text,uuid,uuid,text,jsonb) to service_role;
revoke all on function public.ap_bill_import_version() from public,anon,authenticated;
commit;
