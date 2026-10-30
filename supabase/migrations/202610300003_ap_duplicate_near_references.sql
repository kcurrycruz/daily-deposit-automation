-- Add same-date digit typo scan versions; retain immutable earlier evidence.
begin;
alter table public.ap_workspaces add column duplicate_near_schema_version integer not null default 0;
alter table public.ap_duplicate_scans drop constraint ap_duplicate_scans_rule_version_check;
alter table public.ap_duplicate_scans add constraint ap_duplicate_scans_rule_version_check check(rule_version in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3','bill-duplicates-v4','bill-duplicates-v5','bill-duplicates-v6'));
alter table public.ap_duplicate_scans drop constraint ap_duplicate_working_rule;
alter table public.ap_duplicate_scans add constraint ap_duplicate_working_rule check((rule_version in ('bill-duplicates-v4','bill-duplicates-v6'))=(working_set_id is not null) and (working_set_id is null)=(expected_working_version is null));
do $migration$
declare definition text; originals text[]:=array[
$old$p_data->>'rule_version'='bill-duplicates-v4'$old$,
$old$coalesce(p_data->>'rule_version','') not in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3','bill-duplicates-v4')$old$,
$old$job.rule_version='bill-duplicates-v4'$old$,
$old$job.rule_version='bill-duplicates-v3'$old$,
$old$  if p_operation='ensure' then$old$];
replacements text[]:=array[
$new$p_data->>'rule_version' in ('bill-duplicates-v4','bill-duplicates-v6')$new$,
$new$coalesce(p_data->>'rule_version','') not in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3','bill-duplicates-v4','bill-duplicates-v5','bill-duplicates-v6')$new$,
$new$job.rule_version in ('bill-duplicates-v4','bill-duplicates-v6')$new$,
$new$job.rule_version in ('bill-duplicates-v3','bill-duplicates-v5')$new$,
$new$  if p_operation='ensure' then
    if home.duplicate_near_schema_version=1 and p_data->>'rule_version' is distinct from
      (case when home.active_working_set_id is null then 'bill-duplicates-v5' else 'bill-duplicates-v6' end)
      then raise exception 'duplicate_conflict'; end if;$new$]; i integer; expected integer[]:=array[1,1,2,2,1];
begin
 definition=pg_get_functiondef('public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)'::regprocedure);
 for i in 1..array_length(originals,1) loop
  if length(definition)-length(replace(definition,originals[i],''))<>length(originals[i])*expected[i] then raise exception 'unsupported_duplicate_near_function:%',i; end if;
  definition=replace(definition,originals[i],replacements[i]);
 end loop;
 execute definition;
end $migration$;
revoke all on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) to service_role;
alter table public.ap_workspaces alter column duplicate_near_schema_version set default 1;
update public.ap_workspaces set duplicate_near_schema_version=1;
commit;
