-- Additive private re-review support. Apply only to an authorized project.
begin;
alter table public.ap_workspaces add column rereview_schema_version integer not null default 1;

create function public.ap_rereview_statement(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare
  cached ap_requests%rowtype; item ap_statements%rowtype; previous ap_statement_revisions%rowtype;
  mode text; rid uuid; next_version integer; decisions jsonb; reply jsonb;
begin
  if p_payload_hash is null or p_payload_hash !~ '^[0-9a-f]{64}$' or
     jsonb_typeof(p_data) is distinct from 'object' or
     not (p_data ?& array['statement_id','expected_version','review_mode']) or
     exists(select 1 from jsonb_object_keys(p_data) k where k not in ('statement_id','expected_version','review_mode')) or
     coalesce(p_data->>'review_mode','') not in ('manual','latest') or
     coalesce(p_data->>'expected_version','') !~ '^[1-9][0-9]*$' then raise exception 'validation'; end if;
  perform 1 from ap_workspaces where id=p_workspace and rereview_schema_version=1 for update;
  if not found then raise exception 'conflict'; end if;
  select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
  if found then
    if cached.payload_hash<>p_payload_hash then raise exception 'request_conflict'; end if;
    return cached.response;
  end if;
  select * into item from ap_statements where workspace_id=p_workspace and id=(p_data->>'statement_id')::uuid for update;
  if not found or item.version is distinct from (p_data->>'expected_version')::integer or not item.completed then
    raise exception 'conflict';
  end if;
  select * into previous from ap_statement_revisions where workspace_id=p_workspace and id=item.current_revision_id and statement_id=item.id;
  if not found then raise exception 'conflict'; end if;
  mode=p_data->>'review_mode';rid=gen_random_uuid();next_version=item.version+1;
  if mode='manual' then decisions=previous.resolutions;
  else
    select coalesce(jsonb_object_agg(e.key,jsonb_build_object('note',coalesce(e.value->>'note',''))),'{}') into decisions
      from jsonb_each(previous.resolutions) e;
  end if;
  insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,resolutions,import_id,mapping_snapshot,results,rule_version)
    values(rid,p_workspace,item.id,next_version,previous.doc||jsonb_build_object('reviewMode',mode),decisions,
           previous.import_id,previous.mapping_snapshot,previous.results,previous.rule_version);
  insert into ap_completion_events(workspace_id,statement_id,revision_id,event,status)
    values(p_workspace,item.id,rid,'reopened','draft');
  update ap_statements set completed=false,archived=false,version=next_version,current_revision_id=rid,updated_at=now() where id=item.id;
  reply=jsonb_build_object('statement_id',item.id,'version',next_version,'revision_id',rid);
  insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,reply);
  return reply;
end;
$$;

create or replace function public.ap_reopen_statement(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language sql security definer set search_path=public,pg_temp as $$
  select case when p_data ? 'review_mode'
    then public.ap_rereview_statement(p_workspace,p_request_id,p_payload_hash,p_data)
    else public.ap_mutate('reopen_statement',p_workspace,p_request_id,p_payload_hash,p_data) end;
$$;
revoke all on function public.ap_rereview_statement(uuid,uuid,text,jsonb) from public,anon,authenticated;
revoke all on function public.ap_reopen_statement(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_rereview_statement(uuid,uuid,text,jsonb) to service_role;
grant execute on function public.ap_reopen_statement(uuid,uuid,text,jsonb) to service_role;

-- A manual check has its own server-owned time. Saving another item's decision,
-- statement notes or completion must not make an old check appear newly made.
create or replace function public.ap_save_revision(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare
  cached ap_requests%rowtype; previous ap_statement_revisions%rowtype;
  entry record; proof jsonb; old_proof jsonb; decisions jsonb='{}'; value jsonb;
begin
  if p_data->'doc'->>'reviewMode' is distinct from 'manual' then
    return public.ap_mutate('save_revision',p_workspace,p_request_id,p_payload_hash,p_data);
  end if;
  if p_payload_hash is null or p_payload_hash !~ '^[0-9a-f]{64}$' then raise exception 'validation'; end if;
  perform 1 from ap_workspaces where id=p_workspace and rereview_schema_version=1 for update;
  if not found then raise exception 'conflict'; end if;
  select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
  if found then
    if cached.payload_hash<>p_payload_hash then raise exception 'request_conflict'; end if;
    return cached.response;
  end if;
  select * into previous from ap_statement_revisions where workspace_id=p_workspace
    and statement_id=(p_data->>'statement_id')::uuid and version=(p_data->>'expected_version')::integer;
  if not found or previous.doc->>'reviewMode' is distinct from 'manual' then raise exception 'conflict'; end if;
  for entry in select * from jsonb_each(coalesce(p_data->'resolutions','{}')) loop
    value=entry.value;proof=value->'manualCheck';
    if proof is not null then
      old_proof=previous.resolutions->entry.key->'manualCheck';
      if proof ? 'checkedAt' then
        if proof is distinct from old_proof then raise exception 'validation'; end if;
      else
        proof=proof||jsonb_build_object('checkedAt',now());
      end if;
      value=jsonb_set(value,'{manualCheck}',proof);
    end if;
    decisions=decisions||jsonb_build_object(entry.key,value);
  end loop;
  return public.ap_mutate('save_revision',p_workspace,p_request_id,p_payload_hash,jsonb_set(p_data,'{resolutions}',decisions));
end;
$$;
revoke all on function public.ap_save_revision(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_save_revision(uuid,uuid,text,jsonb) to service_role;
commit;
