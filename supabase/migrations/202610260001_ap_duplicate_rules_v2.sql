-- Permit fresh results under the same-day digit-swap rules without altering
-- immutable v1 evidence or review history. Deploy before the v2 application.
begin;

alter table public.ap_duplicate_scans
  drop constraint if exists ap_duplicate_scans_rule_version_check;
alter table public.ap_duplicate_scans
  add constraint ap_duplicate_scans_rule_version_check
  check (rule_version in ('bill-duplicates-v1','bill-duplicates-v2'));

-- Preserve the deployed lifecycle/security checks and only generalize the
-- three v1-only ensure expressions. Fail closed on an unexpected definition;
-- accept the upgraded expressions so this migration can be retried safely.
do $migration$
declare
  definition text;
  originals text[] := array[
    $old$p_data->>'rule_version' is distinct from 'bill-duplicates-v1'$old$,
    $old$source.file_hash,'bill-duplicates-v1',home.import_version$old$,
    $old$and rule_version='bill-duplicates-v1'$old$
  ];
  replacements text[] := array[
    $new$coalesce(p_data->>'rule_version','') not in ('bill-duplicates-v1','bill-duplicates-v2')$new$,
    $new$source.file_hash,p_data->>'rule_version',home.import_version$new$,
    $new$and rule_version=p_data->>'rule_version'$new$
  ];
  i integer;
begin
  definition := pg_get_functiondef('public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)'::regprocedure);
  for i in 1..array_length(originals,1) loop
    if strpos(definition,originals[i])>0 then
      if length(definition)-length(replace(definition,originals[i],''))<>length(originals[i])
         or strpos(definition,replacements[i])>0 then
        raise exception 'unsupported_duplicate_rule_function';
      end if;
      definition := replace(definition,originals[i],replacements[i]);
    elsif length(definition)-length(replace(definition,replacements[i],''))<>length(replacements[i]) then
      raise exception 'unsupported_duplicate_rule_function';
    end if;
  end loop;
  execute definition;
end $migration$;

revoke all on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb) to service_role;
commit;
