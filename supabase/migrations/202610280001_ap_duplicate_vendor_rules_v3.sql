-- Apply before the v3 application. Preserve immutable v1/v2 scans and reviews.
begin;

alter table public.ap_duplicate_scans
  drop constraint if exists ap_duplicate_scans_rule_version_check;
alter table public.ap_duplicate_scans
  add constraint ap_duplicate_scans_rule_version_check
  check (rule_version in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3'));

-- Only the supported ensure version list and rule-bound artifact format/path
-- change. Do not replace lifecycle, authorization, source, quota, or review code.
do $migration$
declare
  definition text;
  originals text[] := array[
    $old$coalesce(p_data->>'rule_version','') not in ('bill-duplicates-v1','bill-duplicates-v2')$old$,
    $old$mf->>'format' is distinct from 'bill-duplicates-v1'$old$,
    $old$p_workspace::text||'/bill-duplicates/v1/'||job.import_id::text$old$
  ];
  replacements text[] := array[
    $new$coalesce(p_data->>'rule_version','') not in ('bill-duplicates-v1','bill-duplicates-v2','bill-duplicates-v3')$new$,
    $new$mf->>'format' is distinct from (case when job.rule_version='bill-duplicates-v3' then 'bill-duplicates-v2' else 'bill-duplicates-v1' end)$new$,
    $new$p_workspace::text||(case when job.rule_version='bill-duplicates-v3' then '/bill-duplicates/v2/' else '/bill-duplicates/v1/' end)||job.import_id::text$new$
  ];
  i integer;
begin
  definition := pg_get_functiondef('public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)'::regprocedure);
  for i in 1..array_length(originals,1) loop
    if strpos(definition,originals[i])>0 then
      if length(definition)-length(replace(definition,originals[i],''))<>length(originals[i])
         or strpos(definition,replacements[i])>0 then
        raise exception 'unsupported_duplicate_vendor_function';
      end if;
      definition := replace(definition,originals[i],replacements[i]);
    elsif length(definition)-length(replace(definition,replacements[i],''))<>length(replacements[i]) then
      raise exception 'unsupported_duplicate_vendor_function';
    end if;
  end loop;
  execute definition;
end $migration$;

revoke all on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) to service_role;
commit;
