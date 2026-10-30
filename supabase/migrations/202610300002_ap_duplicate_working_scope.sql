-- Scope-bound v4 results; preserve all earlier scans, reviews, leases and access rules.
begin;
alter table public.ap_duplicate_scans add column working_set_id uuid;
alter table public.ap_duplicate_scans add column expected_working_version bigint;
alter table public.ap_duplicate_scans add constraint ap_duplicate_working_fk foreign key(workspace_id,working_set_id) references public.ap_bill_working_sets(workspace_id,id);
alter table public.ap_duplicate_scans drop constraint ap_duplicate_scans_workspace_id_import_id_rule_version_key;
alter table public.ap_duplicate_scans add unique(workspace_id,import_id,rule_version,source_digest);
alter table public.ap_duplicate_scans drop constraint ap_duplicate_scans_rule_version_check;
alter table public.ap_duplicate_scans add constraint ap_duplicate_scans_rule_version_check check(rule_version in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3','bill-duplicates-v4'));
alter table public.ap_duplicate_scans add constraint ap_duplicate_working_rule check((rule_version='bill-duplicates-v4')=(working_set_id is not null) and (working_set_id is null)=(expected_working_version is null));
alter table public.ap_duplicate_reviews add column reviewed_working_set_id uuid;
alter table public.ap_duplicate_reviews add foreign key(workspace_id,reviewed_working_set_id) references public.ap_bill_working_sets(workspace_id,id);
do $migration$
declare definition text; originals text[]:=array[
$old$fields text[]; reply jsonb;$old$,
$old$  if coalesce(array_length(fields,1),0)=0$old$,
$old$coalesce(p_data->>'rule_version','') not in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3')$old$,
$old$if not found or source.file_hash is distinct from p_data->>'source_digest' then raise exception 'duplicate_conflict'; end if;$old$,
$old$and import_id<>source.id and state in ('pending','running','failed','restart_required')$old$,
$old$insert into ap_duplicate_scans(id,workspace_id,import_id,source_digest,rule_version,expected_import_version)$old$,
$old$values(sid,p_workspace,source.id,source.file_hash,p_data->>'rule_version',home.import_version)$old$,
$old$on conflict(workspace_id,import_id,rule_version) do nothing;$old$,
$old$and rule_version=p_data->>'rule_version';$old$,
$old$    if p_operation='review' then$old$,
$old$reviewed_import_id,scan_id)$old$,
$old$next_version,job.import_id,job.id)$old$,
$old$scan_id=excluded.scan_id returning * into saved;$old$,
$old$'reviewedImportId',saved.reviewed_import_id)$old$,
$old$expected_import_version=home.import_version,updated_at=now()$old$,
$old$mf->>'format' is distinct from (case when job.rule_version='bill-duplicates-v3' then 'bill-duplicates-v2' else 'bill-duplicates-v1' end)$old$,
$old$(mf->>'recordCount')::integer is distinct from source.record_count$old$,
$old$p_workspace::text||(case when job.rule_version='bill-duplicates-v3' then '/bill-duplicates/v2/' else '/bill-duplicates/v1/' end)$old$,
$old$            update ap_duplicate_scans set state='ready',phase='complete'$old$];
replacements text[]:=array[
$new$ws ap_bill_working_sets%rowtype; scoped boolean; fields text[]; reply jsonb;$new$,
$new$  scoped=(p_operation='ensure' and p_data->>'rule_version'='bill-duplicates-v4') or
    (p_operation='review' and exists(select 1 from ap_duplicate_scans where workspace_id=p_workspace and id=(p_data->>'scan_id')::uuid and working_set_id is not null));
  if scoped then fields=fields||array['working_set_id','expected_working_version']; end if;
  if coalesce(array_length(fields,1),0)=0$new$,
$new$coalesce(p_data->>'rule_version','') not in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3','bill-duplicates-v4')$new$,
$new$if not found then raise exception 'duplicate_conflict'; end if;
    if scoped then
      select * into ws from ap_bill_working_sets where workspace_id=p_workspace and id=home.active_working_set_id and source_import_id=source.id;
      if not found or ws.id is distinct from (p_data->>'working_set_id')::uuid or
        home.working_set_version is distinct from (p_data->>'expected_working_version')::bigint or
        home.working_protection_epoch is distinct from home.bill_protection_epoch or
        ws.manifest->>'workingDigest' is distinct from p_data->>'source_digest' then raise exception 'duplicate_conflict'; end if;
    elsif home.active_working_set_id is not null or source.file_hash is distinct from p_data->>'source_digest' then raise exception 'duplicate_conflict'; end if;$new$,
$new$and (import_id<>source.id or source_digest<>p_data->>'source_digest' or rule_version<>p_data->>'rule_version') and state in ('pending','running','failed','restart_required')$new$,
$new$insert into ap_duplicate_scans(id,workspace_id,import_id,source_digest,rule_version,expected_import_version,working_set_id,expected_working_version)$new$,
$new$values(sid,p_workspace,source.id,p_data->>'source_digest',p_data->>'rule_version',home.import_version,ws.id,case when scoped then home.working_set_version else null end)$new$,
$new$on conflict(workspace_id,import_id,rule_version,source_digest) do nothing;$new$,
$new$and rule_version=p_data->>'rule_version' and source_digest=p_data->>'source_digest';$new$,
$new$    if job.working_set_id is not null then
      select * into ws from ap_bill_working_sets where workspace_id=p_workspace and id=job.working_set_id;
      if not found or home.active_working_set_id is distinct from job.working_set_id or
        home.working_protection_epoch is distinct from home.bill_protection_epoch or
        (job.state<>'ready' and p_operation<>'restart' and job.expected_working_version is distinct from home.working_set_version) or
        (p_operation='review' and ((p_data->>'working_set_id')::uuid is distinct from job.working_set_id or
          (p_data->>'expected_working_version')::bigint is distinct from home.working_set_version)) then raise exception 'duplicate_conflict'; end if;
    elsif home.active_working_set_id is not null then raise exception 'duplicate_conflict'; end if;
    if p_operation='review' then$new$,
$new$reviewed_import_id,scan_id,reviewed_working_set_id)$new$,
$new$next_version,job.import_id,job.id,job.working_set_id)$new$,
$new$scan_id=excluded.scan_id,reviewed_working_set_id=excluded.reviewed_working_set_id returning * into saved;$new$,
$new$'reviewedImportId',saved.reviewed_import_id,'reviewedWorkingSetId',saved.reviewed_working_set_id)$new$,
$new$expected_import_version=home.import_version,expected_working_version=case when job.working_set_id is not null then home.working_set_version else null end,updated_at=now()$new$,
$new$mf->>'format' is distinct from (case when job.rule_version='bill-duplicates-v4' then 'bill-duplicates-v3' when job.rule_version='bill-duplicates-v3' then 'bill-duplicates-v2' else 'bill-duplicates-v1' end)$new$,
$new$(mf->>'recordCount')::integer is distinct from (case when job.working_set_id is not null then (ws.manifest->>'activeCount')::integer else source.record_count end)$new$,
$new$p_workspace::text||(case when job.rule_version='bill-duplicates-v4' then '/bill-duplicates/v3/' when job.rule_version='bill-duplicates-v3' then '/bill-duplicates/v2/' else '/bill-duplicates/v1/' end)$new$,
$new$            if job.working_set_id is not null and (
              mf->>'workingSetId' is distinct from job.working_set_id::text or mf->>'workingDigest' is distinct from job.source_digest or
              (mf->>'workingVersion')::bigint is distinct from home.working_set_version or
              mf->>'fullSourceDigest' is distinct from source.file_hash or (mf->>'fullRecordCount')::integer is distinct from source.record_count or
              mf->>'mappingDigest' is distinct from ws.manifest->>'mappingDigest') then raise exception 'duplicate_invalid_source'; end if;
            update ap_duplicate_scans set state='ready',phase='complete'$new$]; i integer;
begin
 definition=pg_get_functiondef('public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)'::regprocedure);
 for i in 1..array_length(originals,1) loop
  if length(definition)-length(replace(definition,originals[i],''))<>length(originals[i]) then raise exception 'unsupported_duplicate_working_function:%',i; end if;
  definition=replace(definition,originals[i],replacements[i]);
 end loop;
 execute definition;
end $migration$;
revoke all on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) to service_role;
commit;
