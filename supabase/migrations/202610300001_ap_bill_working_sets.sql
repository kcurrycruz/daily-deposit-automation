-- Additive derived coverage. Original imports, statements and reviews are retained.
begin;
alter table public.ap_workspaces add column bill_working_schema_version integer not null default 1;
alter table public.ap_workspaces add column active_working_set_id uuid;
alter table public.ap_workspaces add column working_set_version bigint not null default 0;
alter table public.ap_workspaces add column bill_protection_epoch bigint not null default 0;
alter table public.ap_workspaces add column working_protection_epoch bigint;

create table public.ap_bill_working_sets (
  id uuid primary key, workspace_id uuid not null references public.ap_workspaces(id), source_import_id uuid not null,
  working_digest text not null check(working_digest ~ '^[0-9a-f]{64}$'),
  protection_digest text not null check(protection_digest ~ '^[0-9a-f]{64}$'),
  source_digest text not null check(source_digest ~ '^[0-9a-f]{64}$'), policy jsonb not null,
  full_record_count integer not null check(full_record_count between 1 and 500000),
  active_count integer not null check(active_count between 0 and 500000),
  archived_count integer not null check(archived_count>=0), manifest jsonb not null,
  created_at timestamptz not null default now(), unique(workspace_id,id), unique(workspace_id,working_digest),
  foreign key(workspace_id,source_import_id) references public.ap_bill_imports(workspace_id,id),
  check(active_count+archived_count=full_record_count)
);
create function public.ap_bill_working_immutable() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin raise exception 'import_immutable'; end $$;
create trigger ap_bill_working_set_immutable before update or delete on public.ap_bill_working_sets
  for each row execute function public.ap_bill_working_immutable();
alter table public.ap_workspaces add constraint ap_active_working_set_fk
  foreign key(id,active_working_set_id) references public.ap_bill_working_sets(workspace_id,id);
alter table public.ap_statement_revisions add column working_set_id uuid;
alter table public.ap_statement_revisions add constraint ap_revision_working_set_fk
  foreign key(workspace_id,working_set_id) references public.ap_bill_working_sets(workspace_id,id);

create table public.ap_bill_working_jobs (
  id uuid primary key, workspace_id uuid not null references public.ap_workspaces(id), source_import_id uuid not null,
  session_nonce uuid not null, generation uuid not null default gen_random_uuid(),
  expected_import_version bigint not null, expected_working_version bigint not null,
  protection_epoch bigint not null, protection_digest text not null check(protection_digest ~ '^[0-9a-f]{64}$'),
  policy jsonb not null, upload_job_id uuid, working_set_id uuid,
  state text not null default 'building' check(state in ('building','packaging','prepared','activated','cancelled')),
  checkpoint integer not null default 0 check(checkpoint>=0), progress jsonb not null default '{}',
  reserved_bytes bigint not null default 0 check(reserved_bytes>=0), reservation_bucket text,
  lease_until timestamptz not null default now()+interval '1 hour', created_at timestamptz not null default now(),
  unique(workspace_id,id), foreign key(workspace_id,source_import_id) references public.ap_bill_imports(workspace_id,id),
  foreign key(workspace_id,working_set_id) references public.ap_bill_working_sets(workspace_id,id),
  foreign key(workspace_id,upload_job_id) references public.ap_bill_jobs(workspace_id,id)
);
alter table public.ap_bill_working_sets enable row level security;
alter table public.ap_bill_working_jobs enable row level security;
revoke all on public.ap_bill_working_sets,public.ap_bill_working_jobs from public,anon,authenticated;
grant select,insert on public.ap_bill_working_sets to service_role;
grant select,insert,update,delete on public.ap_bill_working_jobs to service_role;

create function public.ap_bill_working_version() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
  if new.active_import_id is distinct from old.active_import_id and
     new.active_working_set_id is not distinct from old.active_working_set_id then new.active_working_set_id=null; end if;
  if new.active_working_set_id is not null and not exists(select 1 from ap_bill_working_sets
      where workspace_id=new.id and id=new.active_working_set_id and source_import_id=new.active_import_id) then
    raise exception 'bill_conflict';
  end if;
  if new.active_working_set_id is null then new.working_protection_epoch=null; end if;
  new.working_set_version=old.working_set_version+case when new.active_working_set_id is distinct from old.active_working_set_id then 1 else 0 end;
  return new;
end $$;
create trigger ap_bill_working_version before update on public.ap_workspaces for each row execute function public.ap_bill_working_version();

-- All writers serialize on the workspace row before changing protection inputs.
create function public.ap_bill_protection_changed() returns trigger language plpgsql set search_path=public,pg_temp as $$
declare wid uuid;
begin
  wid=case when tg_op='DELETE' then old.workspace_id else new.workspace_id end;
  update ap_workspaces set bill_protection_epoch=bill_protection_epoch+1 where id=wid;
  if tg_op='DELETE' then return old; end if;
  return new;
end $$;
create trigger ap_statement_protection before insert or update or delete on public.ap_statements
  for each row execute function public.ap_bill_protection_changed();
create trigger ap_mapping_protection before insert or update or delete on public.ap_vendor_mappings
  for each row execute function public.ap_bill_protection_changed();
create trigger ap_duplicate_protection before insert or update or delete on public.ap_duplicate_reviews
  for each row execute function public.ap_bill_protection_changed();

create function public.ap_revision_working_source() returns trigger language plpgsql set search_path=public,pg_temp as $$
declare previous ap_statement_revisions%rowtype; scope text;
begin
  scope=coalesce(current_setting('ap.revision_working_scope',true),'');
  if scope<>'' and scope<>'full' then
    new.working_set_id=scope::uuid;
  elsif scope<>'full' and new.working_set_id is null then
    select r.* into previous from ap_statements s join ap_statement_revisions r on r.id=s.current_revision_id
      where s.workspace_id=new.workspace_id and s.id=new.statement_id;
    if found and new.import_id is not distinct from previous.import_id and new.results=previous.results and
      new.mapping_snapshot=previous.mapping_snapshot then new.working_set_id=previous.working_set_id; end if;
  end if;
  if new.working_set_id is not null and not exists(select 1 from ap_bill_working_sets
    where workspace_id=new.workspace_id and id=new.working_set_id and source_import_id=new.import_id) then
    raise exception 'bill_conflict';
  end if;
  return new;
end $$;
create trigger ap_revision_working_source before insert on public.ap_statement_revisions for each row execute function public.ap_revision_working_source();

create function public.ap_working_policy_valid(p jsonb) returns boolean language plpgsql immutable set search_path=public,pg_temp as $$
declare d date;
begin
  if jsonb_typeof(p) is distinct from 'object' or (select count(*) from jsonb_object_keys(p))<>4 or
     p->>'version' is distinct from 'ap-active-range-v1' or coalesce(p->>'mode','') not in ('all','last_12_months') or
     coalesce(p->>'asOfDate','') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then return false; end if;
  d=(p->>'asOfDate')::date;
  return case when p->>'mode'='all' then p->>'cutoffDate'='' else
    p->>'cutoffDate'=to_char(d-interval '1 year','YYYY-MM-DD') end;
exception when others then return false;
end $$;

-- Include derived-build reservations in the same bucket-wide budget.
create or replace function public.ap_storage_reserve(p_owner text,p_workspace uuid,p_job uuid,p_bucket text,p_requested bigint,p_budget bigint)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare used bigint; reserved bigint; code text;
begin
  code=case when p_owner in ('bill','working') then 'bill_quota' else 'duplicate_quota' end;
  if p_owner is null or p_owner not in ('bill','duplicate','working') or coalesce(p_bucket,'')='' or
    p_requested is null or p_requested<0 or p_budget is null or p_budget<0 then raise exception '%',code; end if;
  if p_owner='bill' and not exists(select 1 from ap_bill_jobs where workspace_id=p_workspace and id=p_job and lease_until>now())
    or p_owner='duplicate' and not exists(select 1 from ap_duplicate_scans where workspace_id=p_workspace and id=p_job and lease_until>now())
    or p_owner='working' and not exists(select 1 from ap_bill_working_jobs where workspace_id=p_workspace and id=p_job and lease_until>now() and state not in ('activated','cancelled'))
    then raise exception '%',code; end if;
  perform pg_advisory_xact_lock(hashtext('ap-bill-quota:'||p_bucket));
  select coalesce(sum((metadata->>'size')::bigint),0) into used from storage.objects where bucket_id=p_bucket;
  select coalesce(sum(n),0) into reserved from (
    select reserved_bytes n from ap_bill_jobs where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'bill' or id<>p_job)
    union all select reserved_bytes from ap_duplicate_scans where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'duplicate' or id<>p_job)
    union all select reserved_bytes from ap_bill_working_jobs where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'working' or id<>p_job)
  ) reservations;
  if used+reserved+p_requested>p_budget then raise exception '%',code; end if;
  if p_owner='bill' then update ap_bill_jobs set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace;
  elsif p_owner='duplicate' then update ap_duplicate_scans set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace;
  else update ap_bill_working_jobs set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace; end if;
  return jsonb_build_object('used_bytes',used,'reserved_bytes',p_requested,'warning',used+reserved+p_requested>=0.8*p_budget);
end $$;

create function public.ap_bill_working_mutate(p_operation text,p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare home ap_workspaces%rowtype; job ap_bill_working_jobs%rowtype; source ap_bill_imports%rowtype;
  ws ap_bill_working_sets%rowtype; cached ap_requests%rowtype; jid uuid; mf jsonb; a jsonb; result jsonb; artifact_name text;
begin
  if p_payload_hash is null or p_payload_hash !~ '^[0-9a-f]{64}$' or jsonb_typeof(p_data) is distinct from 'object' then raise exception 'bill_incomplete'; end if;
  select * into home from ap_workspaces where id=p_workspace for update;
  if not found then raise exception 'bill_conflict'; end if;
  select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
  if found then
    if cached.payload_hash<>p_payload_hash then raise exception 'request_conflict'; end if;
    return cached.response;
  end if;
  jid=(p_data->>'job_id')::uuid;
  if p_operation='begin' then
    if exists(select 1 from ap_bill_working_jobs where workspace_id=p_workspace and lease_until>now() and state not in ('activated','cancelled')) then raise exception 'bill_conflict'; end if;
    if home.import_version is distinct from (p_data->>'expected_import_version')::bigint or
      home.working_set_version is distinct from (p_data->>'expected_working_version')::bigint or
      home.bill_protection_epoch is distinct from (p_data->>'protection_epoch')::bigint or
      not coalesce(ap_working_policy_valid(p_data->'policy'),false) or
      coalesce(p_data->>'protection_digest','') !~ '^[0-9a-f]{64}$' or p_data->>'session_nonce' is null then raise exception 'bill_conflict'; end if;
    select * into source from ap_bill_imports where workspace_id=p_workspace and id=(p_data->>'source_import_id')::uuid and state='ready';
    if not found then raise exception 'bill_incomplete'; end if;
    if home.active_import_id is distinct from source.id and not exists(select 1 from ap_bill_jobs
      where workspace_id=p_workspace and id=(p_data->>'upload_job_id')::uuid and import_id=source.id and state='prepared'
      and session_nonce=(p_data->>'session_nonce')::uuid and expected_import_version=home.import_version and lease_until>now()) then raise exception 'bill_conflict'; end if;
    insert into ap_bill_working_jobs(id,workspace_id,source_import_id,session_nonce,expected_import_version,expected_working_version,
      protection_epoch,protection_digest,policy,upload_job_id) values(jid,p_workspace,source.id,(p_data->>'session_nonce')::uuid,
      home.import_version,home.working_set_version,home.bill_protection_epoch,p_data->>'protection_digest',p_data->'policy',(p_data->>'upload_job_id')::uuid)
      returning * into job;
    result=jsonb_build_object('job_id',job.id,'generation',job.generation,'checkpoint',0,'state',job.state,'policy',job.policy);
  else
    select * into job from ap_bill_working_jobs where workspace_id=p_workspace and id=jid for update;
    if not found or job.session_nonce is distinct from (p_data->>'session_nonce')::uuid or
      job.generation is distinct from (p_data->>'generation')::uuid then raise exception 'bill_conflict'; end if;
    if p_operation='cancel' then
      if job.state='activated' then raise exception 'bill_conflict'; end if;
      update ap_bill_working_jobs set state='cancelled',reserved_bytes=0 where id=jid;
      result=jsonb_build_object('cancelled',true);
    else
      if job.state='cancelled' or (job.lease_until<=now() and p_operation<>'restart') then raise exception 'bill_conflict'; end if;
      if p_operation='restart' then
        if job.state='activated' or job.checkpoint is distinct from (p_data->>'expected_checkpoint')::integer or
          home.import_version<>job.expected_import_version or home.working_set_version<>job.expected_working_version or
          home.bill_protection_epoch<>job.protection_epoch then raise exception 'bill_conflict'; end if;
        update ap_bill_working_jobs set generation=gen_random_uuid(),checkpoint=0,state='building',progress='{}',working_set_id=null,
          lease_until=now()+interval '1 hour' where id=jid returning * into job;
        result=jsonb_build_object('job_id',job.id,'generation',job.generation,'checkpoint',0,'state',job.state,'policy',job.policy);
      elsif p_operation='checkpoint' then
        if job.state not in ('building','packaging') or job.checkpoint is distinct from (p_data->>'expected_checkpoint')::integer or
          (p_data->>'next_checkpoint')::integer is distinct from job.checkpoint+1 or coalesce(p_data->>'state','') not in ('building','packaging') then raise exception 'bill_conflict'; end if;
        update ap_bill_working_jobs set checkpoint=checkpoint+1,state=p_data->>'state',progress=coalesce(p_data->'progress','{}'),lease_until=now()+interval '1 hour' where id=jid returning * into job;
        result=jsonb_build_object('checkpoint',job.checkpoint,'state',job.state);
      elsif p_operation='stage' then
        if job.state<>'packaging' or job.checkpoint is distinct from (p_data->>'expected_checkpoint')::integer then raise exception 'bill_conflict'; end if;
        select * into source from ap_bill_imports where workspace_id=p_workspace and id=job.source_import_id and state='ready';
        mf=p_data->'manifest';
        if mf->>'format' is distinct from 'ap-bill-working-v1' or mf->>'trainingVersion' is distinct from 'vendor-history-v1' or
          coalesce(mf->>'workingDigest','') !~ '^[0-9a-f]{64}$' or coalesce(mf->>'vendorDigest','') !~ '^[0-9a-f]{64}$' or coalesce(mf->>'archiveVendorDigest','') !~ '^[0-9a-f]{64}$' or
          mf->'source'->>'importId' is distinct from source.id::text or mf->'source'->>'sourceDigest' is distinct from source.file_hash or
          (mf->'source'->>'recordCount')::integer is distinct from source.record_count or mf->'policy' is distinct from job.policy or
          mf->>'protectionDigest' is distinct from job.protection_digest or (mf->>'fullRecordCount')::integer is distinct from source.record_count or
          coalesce((mf->>'activeCount')::integer,-1) not between 0 and source.record_count or
          (mf->>'activeCount')::integer+(mf->>'archivedCount')::integer is distinct from source.record_count then raise exception 'bill_incomplete'; end if;
        foreach artifact_name in array array['indexArchive','contextArchive'] loop
          a=mf->artifact_name;
          if coalesce(a->>'hash','') !~ '^[0-9a-f]{64}$' or coalesce(a->>'expandedHash','') !~ '^[0-9a-f]{64}$' or
            coalesce((a->>'bytes')::bigint,0) not between 1 and 33554432 or coalesce((a->>'expandedBytes')::bigint,0) not between 1 and 536870912 or
            a->>'key' is distinct from p_workspace::text||'/bill-working/v1/'||(mf->>'workingDigest')||'/'||(a->>'hash')||'.sqlite.gz' then raise exception 'bill_incomplete'; end if;
        end loop;
        select * into ws from ap_bill_working_sets where workspace_id=p_workspace and working_digest=mf->>'workingDigest';
        if not found then
          insert into ap_bill_working_sets(id,workspace_id,source_import_id,working_digest,protection_digest,source_digest,policy,
            full_record_count,active_count,archived_count,manifest) values((mf->>'workingSetId')::uuid,p_workspace,source.id,mf->>'workingDigest',job.protection_digest,source.file_hash,job.policy,
            source.record_count,(mf->>'activeCount')::integer,(mf->>'archivedCount')::integer,mf) returning * into ws;
        elsif ws.manifest-'workingSetId' is distinct from mf-'workingSetId' then raise exception 'bill_conflict'; end if;
        update ap_bill_working_jobs set state='prepared',working_set_id=ws.id where id=jid;
        result=jsonb_build_object('working_set_id',ws.id,'manifest',ws.manifest);
      elsif p_operation='activate' then
        if job.state='activated' then
          result=jsonb_build_object('working_set_id',job.working_set_id,'superseded',home.active_working_set_id is distinct from job.working_set_id,'import_version',home.import_version,'working_version',home.working_set_version);
        else
          if job.state<>'prepared' then raise exception 'bill_incomplete'; end if;
          if home.import_version<>job.expected_import_version or home.working_set_version<>job.expected_working_version or
            home.bill_protection_epoch<>job.protection_epoch then raise exception 'bill_conflict'; end if;
          update ap_workspaces set active_import_id=job.source_import_id,active_working_set_id=job.working_set_id,
            working_protection_epoch=home.bill_protection_epoch where id=p_workspace returning * into home;
          update ap_bill_working_jobs set state='activated',reserved_bytes=0 where id=jid;
          if job.upload_job_id is not null then update ap_bill_jobs set state='activated',reserved_bytes=0 where id=job.upload_job_id; end if;
          result=jsonb_build_object('working_set_id',job.working_set_id,'import_id',job.source_import_id,'import_version',home.import_version,'working_version',home.working_set_version);
        end if;
      elsif p_operation='reserve' then
        result=ap_storage_reserve('working',p_workspace,jid,p_data->>'bucket',(p_data->>'requested_bytes')::bigint,(p_data->>'budget_bytes')::bigint);
      else raise exception 'bill_incomplete'; end if;
    end if;
  end if;
  insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,result);
  return result;
end $$;
revoke all on function public.ap_bill_working_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_bill_working_mutate(text,uuid,uuid,text,jsonb) to service_role;
revoke all on function public.ap_working_policy_valid(jsonb),public.ap_bill_working_version(),public.ap_bill_protection_changed(),public.ap_revision_working_source(),public.ap_bill_working_immutable() from public,anon,authenticated;
grant execute on function public.ap_working_policy_valid(jsonb) to service_role;

-- Keep the existing manual-evidence/time-stamping implementation behind a
-- source/scope guard. The original request hash still pins the complete payload.
alter function public.ap_save_revision(uuid,uuid,text,jsonb) rename to ap_save_revision_before_working;
revoke all on function public.ap_save_revision_before_working(uuid,uuid,text,jsonb) from public,anon,authenticated,service_role;
create function public.ap_save_revision(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare home ap_workspaces%rowtype; previous ap_statement_revisions%rowtype; cached ap_requests%rowtype;
  scope_id uuid; setting_before text; reply jsonb;
begin
  if p_payload_hash is null or p_payload_hash !~ '^[0-9a-f]{64}$' or jsonb_typeof(p_data) is distinct from 'object' then raise exception 'validation'; end if;
  select * into home from ap_workspaces where id=p_workspace for update;
  if not found then raise exception 'bill_conflict'; end if;
  select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
  if found then
    if cached.payload_hash<>p_payload_hash then raise exception 'request_conflict'; end if;
    return cached.response;
  end if;
  if p_data->'doc'->>'reviewMode'='manual' then
    select * into previous from ap_statement_revisions where workspace_id=p_workspace and
      statement_id=(p_data->>'statement_id')::uuid and version=(p_data->>'expected_version')::integer;
    if not found then raise exception 'bill_conflict'; end if;
    scope_id=previous.working_set_id;
    if p_data ? 'working_set_id' and (p_data->>'working_set_id')::uuid is distinct from scope_id then raise exception 'bill_conflict'; end if;
  else
    scope_id=(p_data->>'working_set_id')::uuid;
    if scope_id is not null and (home.active_working_set_id is distinct from scope_id or
      home.active_import_id is distinct from (p_data->>'import_id')::uuid or
      home.working_set_version is distinct from (p_data->>'working_version')::bigint or
      home.working_protection_epoch is distinct from home.bill_protection_epoch) then raise exception 'bill_conflict'; end if;
  end if;
  setting_before=coalesce(current_setting('ap.revision_working_scope',true),'');
  perform set_config('ap.revision_working_scope',coalesce(scope_id::text,'full'),true);
  reply=ap_save_revision_before_working(p_workspace,p_request_id,p_payload_hash,p_data-'working_set_id'-'working_version');
  perform set_config('ap.revision_working_scope',setting_before,true);
  return reply;
end $$;
revoke all on function public.ap_save_revision(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_save_revision(uuid,uuid,text,jsonb) to service_role;
commit;
