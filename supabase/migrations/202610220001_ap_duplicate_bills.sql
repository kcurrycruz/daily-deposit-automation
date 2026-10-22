-- Additive private duplicate reviews. Never applies changes to BILL.
begin;
alter table public.ap_workspaces add column duplicate_schema_version integer not null default 1;
alter table public.ap_workspaces add column duplicate_review_revision bigint not null default 0;

create table public.ap_duplicate_scans (
  id uuid primary key, workspace_id uuid not null references public.ap_workspaces(id), import_id uuid not null,
  source_digest text not null check(source_digest ~ '^[0-9a-f]{64}$'),
  rule_version text not null check(rule_version='bill-duplicates-v1'), expected_import_version bigint not null,
  state text not null default 'pending' check(state in ('pending','running','ready','failed','superseded','restart_required')),
  phase text not null default 'reading' check(phase in ('reading','candidates','packaging','complete')),
  generation uuid not null default gen_random_uuid(), checkpoint integer not null default 0 check(checkpoint>=0),
  progress jsonb not null default '{"recordsRead":0,"probes":0}', session_nonce uuid,
  lease_until timestamptz not null default '-infinity', manifest jsonb, error_code text,
  reserved_bytes bigint not null default 0 check(reserved_bytes>=0), reservation_bucket text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), completed_at timestamptz,
  unique(workspace_id,id), unique(workspace_id,import_id,rule_version),
  foreign key(workspace_id,import_id) references public.ap_bill_imports(workspace_id,id),
  check(state<>'ready' or (manifest is not null and completed_at is not null))
);
create table public.ap_duplicate_reviews (
  workspace_id uuid not null references public.ap_workspaces(id), key text not null check(key ~ '^[0-9a-f]{64}$'),
  decision text not null check(decision in ('confirmed_duplicate','not_duplicate','unreviewed')),
  initials text not null check(initials ~ '^[A-Z]{1,10}$'), note text not null default '' check(octet_length(note)<=16384),
  version integer not null check(version>0), at timestamptz not null default now(),
  reviewed_import_id uuid not null, scan_id uuid not null, primary key(workspace_id,key),
  foreign key(workspace_id,reviewed_import_id) references public.ap_bill_imports(workspace_id,id),
  foreign key(workspace_id,scan_id) references public.ap_duplicate_scans(workspace_id,id)
);
create table public.ap_duplicate_review_events (
  id uuid primary key default gen_random_uuid(), workspace_id uuid not null, key text not null,
  review jsonb not null, created_at timestamptz not null default now(),
  foreign key(workspace_id,key) references public.ap_duplicate_reviews(workspace_id,key)
);
create trigger ap_duplicate_event_immutable before update or delete on public.ap_duplicate_review_events
  for each row execute function public.ap_immutable_history();
create function public.ap_duplicate_ready_immutable() returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
  if old.state='ready' and (tg_op='DELETE' or to_jsonb(new) is distinct from to_jsonb(old)) then raise exception 'immutable_duplicate_scan'; end if;
  if tg_op='DELETE' then return old; end if; return new;
end $$;
create trigger ap_duplicate_scan_immutable before update or delete on public.ap_duplicate_scans
  for each row execute function public.ap_duplicate_ready_immutable();
alter table public.ap_duplicate_scans enable row level security;
alter table public.ap_duplicate_reviews enable row level security;
alter table public.ap_duplicate_review_events enable row level security;
revoke all on public.ap_duplicate_scans,public.ap_duplicate_reviews,public.ap_duplicate_review_events from public,anon,authenticated;
grant select,insert,update,delete on public.ap_duplicate_scans,public.ap_duplicate_reviews,public.ap_duplicate_review_events to service_role;

create function public.ap_storage_reserve(p_owner text,p_workspace uuid,p_job uuid,p_bucket text,p_requested bigint,p_budget bigint)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare used bigint; reserved bigint; code text;
begin
  code=case when p_owner='bill' then 'bill_quota' else 'duplicate_quota' end;
  if p_owner is null or p_owner not in ('bill','duplicate') or coalesce(p_bucket,'')='' or
     p_requested is null or p_requested<0 or p_budget is null or p_budget<0 then raise exception '%',code; end if;
  if p_owner='bill' and not exists(select 1 from ap_bill_jobs where workspace_id=p_workspace and id=p_job and lease_until>now())
     or p_owner='duplicate' and not exists(select 1 from ap_duplicate_scans where workspace_id=p_workspace and id=p_job and lease_until>now())
     then raise exception '%',code; end if;
  perform pg_advisory_xact_lock(hashtext('ap-bill-quota:'||p_bucket));
  select coalesce(sum((metadata->>'size')::bigint),0) into used from storage.objects where bucket_id=p_bucket;
  select coalesce(sum(n),0) into reserved from (
    select reserved_bytes n from ap_bill_jobs where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'bill' or id<>p_job)
    union all select reserved_bytes from ap_duplicate_scans where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'duplicate' or id<>p_job)
  ) all_reservations;
  if used+reserved+p_requested>p_budget then raise exception '%',code; end if;
  if p_owner='bill' then update ap_bill_jobs set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace;
  else update ap_duplicate_scans set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace; end if;
  return jsonb_build_object('used_bytes',used,'reserved_bytes',p_requested,'warning',used+reserved+p_requested>=0.8*p_budget);
end $$;
revoke all on function public.ap_storage_reserve(text,uuid,uuid,text,bigint,bigint) from public,anon,authenticated;
grant execute on function public.ap_storage_reserve(text,uuid,uuid,text,bigint,bigint) to service_role;

-- Preserve the deployed BILL function byte-for-byte except this quota branch.
-- Fail the migration instead of guessing if its expected structure has changed.
do $migration$
declare definition text; first_at integer; end_at integer;
begin
  definition=pg_get_functiondef('public.ap_bill_mutate(text,uuid,uuid,text,jsonb)'::regprocedure);
  first_at=strpos(definition,'elsif p_operation=''quota_reserve'' then');
  end_at=strpos(definition,'elsif p_operation=''snapshot_stage'' then');
  if first_at=0 or end_at<=first_at then raise exception 'unsupported_bill_quota_function'; end if;
  execute substring(definition from 1 for first_at-1) ||
    'elsif p_operation=''quota_reserve'' then
       result=public.ap_storage_reserve(''bill'',p_workspace,jid,p_data->>''bucket'',
         (p_data->>''requested_bytes'')::bigint,(p_data->>''budget_bytes'')::bigint);
     ' || substring(definition from end_at);
end $migration$;

create function public.ap_duplicate_mutate(p_operation text,p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare home ap_workspaces%rowtype; job ap_duplicate_scans%rowtype; source ap_bill_imports%rowtype;
  old_review ap_duplicate_reviews%rowtype; saved ap_duplicate_reviews%rowtype; cached ap_requests%rowtype;
  fields text[]; reply jsonb; mf jsonb; sid uuid; next_version integer;
begin
  if coalesce(p_payload_hash,'') !~ '^[0-9a-f]{64}$' or jsonb_typeof(p_data) is distinct from 'object' then raise exception 'duplicate_invalid_source'; end if;
  select * into home from ap_workspaces where id=p_workspace for update;
  if not found then raise exception 'duplicate_conflict'; end if;
  select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
  if found then
    if cached.payload_hash<>p_payload_hash then raise exception 'request_conflict'; end if; return cached.response;
  end if;
  fields=string_to_array(case p_operation
    when 'ensure' then 'scan_id import_id expected_import_version source_digest rule_version'
    when 'claim' then 'scan_id session_nonce'
    when 'checkpoint' then 'scan_id session_nonce generation expected_checkpoint next_checkpoint phase progress'
    when 'restart' then 'scan_id session_nonce expected_generation'
    when 'publish' then 'scan_id session_nonce generation expected_checkpoint expected_import_version manifest'
    when 'fail' then 'scan_id session_nonce generation expected_checkpoint error_code'
    when 'reserve' then 'scan_id session_nonce bucket requested_bytes budget_bytes'
    when 'review' then 'scan_id import_id expected_import_version finding_key expected_review_version decision initials note verified_key'
    else '' end,' ');
  if coalesce(array_length(fields,1),0)=0 or not p_data ?& fields or
    exists(select 1 from jsonb_object_keys(p_data) k where not k=any(fields)) then raise exception 'duplicate_invalid_source'; end if;
  sid=(p_data->>'scan_id')::uuid;
  if p_operation='ensure' then
    if home.active_import_id is distinct from (p_data->>'import_id')::uuid or
       home.import_version is distinct from (p_data->>'expected_import_version')::bigint or
       p_data->>'rule_version' is distinct from 'bill-duplicates-v1' then raise exception 'duplicate_conflict'; end if;
    select * into source from ap_bill_imports where id=home.active_import_id and workspace_id=p_workspace and state='ready';
    if not found or source.file_hash is distinct from p_data->>'source_digest' then raise exception 'duplicate_conflict'; end if;
    update ap_duplicate_scans set state='superseded',reserved_bytes=0,lease_until=now()
      where workspace_id=p_workspace and import_id<>source.id and state in ('pending','running','failed','restart_required');
    insert into ap_duplicate_scans(id,workspace_id,import_id,source_digest,rule_version,expected_import_version)
      values(sid,p_workspace,source.id,source.file_hash,'bill-duplicates-v1',home.import_version)
      on conflict(workspace_id,import_id,rule_version) do nothing;
    select * into job from ap_duplicate_scans where workspace_id=p_workspace and import_id=source.id and rule_version='bill-duplicates-v1';
    if job.id is distinct from sid then raise exception 'duplicate_conflict'; end if;
    reply=to_jsonb(job);
  else
    select * into job from ap_duplicate_scans where id=sid and workspace_id=p_workspace for update;
    if not found then raise exception 'duplicate_conflict'; end if;
    if p_operation='review' then
      if job.state<>'ready' or home.active_import_id is distinct from job.import_id or
         job.import_id is distinct from (p_data->>'import_id')::uuid or
         home.import_version is distinct from (p_data->>'expected_import_version')::bigint or
         coalesce(p_data->>'finding_key','') !~ '^[0-9a-f]{64}$' or
         p_data->>'verified_key' is distinct from p_data->>'finding_key' then raise exception 'duplicate_conflict'; end if;
      if coalesce(p_data->>'initials','') !~ '^[A-Z]{1,10}$' then raise exception 'initials_required'; end if;
      if coalesce(p_data->>'decision','') not in ('confirmed_duplicate','not_duplicate','unreviewed') or
         p_data->>'note' is null or octet_length(p_data->>'note')>16384 then raise exception 'duplicate_invalid_source'; end if;
      select * into old_review from ap_duplicate_reviews where workspace_id=p_workspace and key=p_data->>'finding_key' for update;
      if coalesce(old_review.version,0) is distinct from (p_data->>'expected_review_version')::integer then raise exception 'duplicate_conflict'; end if;
      next_version=coalesce(old_review.version,0)+1;
      insert into ap_duplicate_reviews(workspace_id,key,decision,initials,note,version,reviewed_import_id,scan_id)
        values(p_workspace,p_data->>'finding_key',p_data->>'decision',p_data->>'initials',p_data->>'note',next_version,job.import_id,job.id)
        on conflict(workspace_id,key) do update set decision=excluded.decision,initials=excluded.initials,note=excluded.note,
          version=excluded.version,at=now(),reviewed_import_id=excluded.reviewed_import_id,scan_id=excluded.scan_id returning * into saved;
      update ap_workspaces set duplicate_review_revision=duplicate_review_revision+1 where id=p_workspace returning * into home;
      reply=jsonb_build_object('review',jsonb_build_object('key',saved.key,'decision',saved.decision,'initials',saved.initials,
        'note',saved.note,'version',saved.version,'at',saved.at,'reviewedImportId',saved.reviewed_import_id),
        'reviewRevision',home.duplicate_review_revision);
      insert into ap_duplicate_review_events(workspace_id,key,review) values(p_workspace,saved.key,reply->'review');
    else
      if home.active_import_id is distinct from job.import_id then raise exception 'duplicate_conflict'; end if;
      if p_operation in ('claim','restart') then
        if job.state='ready' or job.session_nonce is distinct from (p_data->>'session_nonce')::uuid and job.lease_until>now() or
          exists(select 1 from ap_duplicate_scans where workspace_id=p_workspace and id<>job.id and state='running' and lease_until>now())
          then raise exception 'duplicate_conflict'; end if;
        if p_operation='restart' and job.generation is distinct from (p_data->>'expected_generation')::uuid then raise exception 'duplicate_conflict'; end if;
        update ap_duplicate_scans set state='running',session_nonce=(p_data->>'session_nonce')::uuid,
          generation=case when p_operation='restart' then gen_random_uuid() else generation end,
          checkpoint=case when p_operation='restart' then 0 else checkpoint end,
          phase=case when p_operation='restart' then 'reading' else phase end,
          progress=case when p_operation='restart' then '{"recordsRead":0,"probes":0}'::jsonb else progress end,
          error_code=null,lease_until=now()+interval '1 hour',expected_import_version=home.import_version,updated_at=now()
          where id=job.id returning * into job;
      else
        if job.state<>'running' or job.session_nonce is distinct from (p_data->>'session_nonce')::uuid or job.lease_until<=now() then raise exception 'duplicate_conflict'; end if;
        if p_operation='reserve' then
          reply=ap_storage_reserve('duplicate',p_workspace,job.id,p_data->>'bucket',(p_data->>'requested_bytes')::bigint,(p_data->>'budget_bytes')::bigint);
        else
          if job.generation is distinct from (p_data->>'generation')::uuid or job.checkpoint is distinct from (p_data->>'expected_checkpoint')::integer then raise exception 'duplicate_conflict'; end if;
          if p_operation='checkpoint' then
            if (p_data->>'next_checkpoint')::integer is distinct from job.checkpoint+1 or
              coalesce(p_data->>'phase','') not in ('reading','candidates','packaging') or
              jsonb_typeof(p_data->'progress') is distinct from 'object' or
              coalesce((p_data->'progress'->>'recordsRead')::bigint,-1)<coalesce((job.progress->>'recordsRead')::bigint,0) or
              coalesce((p_data->'progress'->>'recordsRead')::bigint,-1)>coalesce((job.progress->>'recordsRead')::bigint,0)+5000 or
              coalesce((p_data->'progress'->>'probes')::bigint,-1)<coalesce((job.progress->>'probes')::bigint,0) or
              coalesce((p_data->'progress'->>'probes')::bigint,-1)>coalesce((job.progress->>'probes')::bigint,0)+10000 then raise exception 'duplicate_conflict'; end if;
            update ap_duplicate_scans set checkpoint=checkpoint+1,phase=p_data->>'phase',progress=p_data->'progress',
              lease_until=now()+interval '1 hour',updated_at=now() where id=job.id returning * into job;
          elsif p_operation='fail' then
            if coalesce(p_data->>'error_code','') not in ('duplicate_unavailable','duplicate_conflict','duplicate_limit','duplicate_restart','duplicate_quota','duplicate_invalid_source') then raise exception 'duplicate_invalid_source'; end if;
            update ap_duplicate_scans set state=case when p_data->>'error_code'='duplicate_restart' then 'restart_required' else 'failed' end,
              error_code=p_data->>'error_code',reserved_bytes=0,lease_until=now(),updated_at=now() where id=job.id returning * into job;
          elsif p_operation='publish' then
            mf=p_data->'manifest';
            select * into source from ap_bill_imports where workspace_id=p_workspace and id=job.import_id;
            if job.phase<>'packaging' or home.import_version is distinct from (p_data->>'expected_import_version')::bigint or
              home.import_version<>job.expected_import_version or mf->>'format' is distinct from 'bill-duplicates-v1' or
              mf->>'ruleVersion' is distinct from job.rule_version or mf->>'sourceDigest' is distinct from job.source_digest or
              mf->>'importId' is distinct from job.import_id::text or
              coalesce(mf->>'hash','') !~ '^[0-9a-f]{64}$' or coalesce(mf->>'expandedHash','') !~ '^[0-9a-f]{64}$' or
              coalesce((mf->>'bytes')::bigint,0) not between 1 and 33554432 or
              coalesce((mf->>'expandedBytes')::bigint,0) not between 1 and 536870912 or
              coalesce((mf->>'findingCount')::bigint,-1) not between 0 and 100000 or
              (mf->>'recordCount')::integer is distinct from source.record_count or
              mf->>'key' is distinct from p_workspace::text||'/bill-duplicates/v1/'||job.import_id::text||'/'||job.rule_version||'/'||(mf->>'hash')||'.sqlite.gz'
              then raise exception 'duplicate_invalid_source'; end if;
            update ap_duplicate_scans set state='ready',phase='complete',manifest=mf,reserved_bytes=0,
              lease_until=now(),completed_at=now(),updated_at=now() where id=job.id returning * into job;
          else raise exception 'duplicate_invalid_source'; end if;
        end if;
      end if;
      reply=coalesce(reply,to_jsonb(job));
    end if;
  end if;
  insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,reply);
  return reply;
end $$;
revoke all on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) to service_role;
commit;
