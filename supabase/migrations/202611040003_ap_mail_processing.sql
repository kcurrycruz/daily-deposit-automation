-- Shared private bucket budget includes every live writer.
begin;
create or replace function public.ap_storage_reserve(p_owner text,p_workspace uuid,p_job uuid,p_bucket text,p_requested bigint,p_budget bigint)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare used bigint; reserved bigint; code text;
begin
  code=case when p_owner in ('bill','working') then 'bill_quota' when p_owner='mail' then 'storage' else 'duplicate_quota' end;
  if p_owner is null or p_owner not in ('bill','duplicate','working','mail') or coalesce(p_bucket,'')='' or
    p_requested is null or p_requested<0 or p_budget is null or p_budget<0 then raise exception '%',code; end if;
  if p_owner='bill' and not exists(select 1 from ap_bill_jobs where workspace_id=p_workspace and id=p_job and lease_until>now())
    or p_owner='duplicate' and not exists(select 1 from ap_duplicate_scans where workspace_id=p_workspace and id=p_job and lease_until>now())
    or p_owner='working' and not exists(select 1 from ap_bill_working_jobs where workspace_id=p_workspace and id=p_job and lease_until>now() and state not in ('activated','cancelled'))
    or p_owner='mail' and not exists(select 1 from ap_mail_jobs where workspace_id=p_workspace and id=p_job and lease_until>now() and state='running')
    then raise exception '%',code; end if;
  perform pg_advisory_xact_lock(hashtext('ap-bill-quota:'||p_bucket));
  select coalesce(sum((metadata->>'size')::bigint),0) into used from storage.objects where bucket_id=p_bucket;
  select coalesce(sum(n),0) into reserved from (
    select reserved_bytes n from ap_bill_jobs where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'bill' or id<>p_job)
    union all select reserved_bytes from ap_duplicate_scans where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'duplicate' or id<>p_job)
    union all select reserved_bytes from ap_bill_working_jobs where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'working' or id<>p_job)
  union all select reserved_bytes from ap_mail_jobs where reservation_bucket=p_bucket and lease_until>now() and (p_owner<>'mail' or id<>p_job)
  ) reservations;
  if used+reserved+p_requested>p_budget then raise exception '%',code; end if;
  if p_owner='bill' then update ap_bill_jobs set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace;
  elsif p_owner='duplicate' then update ap_duplicate_scans set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace;
  elsif p_owner='working' then update ap_bill_working_jobs set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace;
  else update ap_mail_jobs set reserved_bytes=p_requested,reservation_bucket=p_bucket where id=p_job and workspace_id=p_workspace; end if;
  return jsonb_build_object('used_bytes',used,'reserved_bytes',p_requested,'warning',used+reserved+p_requested>=0.8*p_budget);
end $$;

create function public.ap_mail_reserve(p_workspace uuid,p_claim jsonb,p_bucket text,p_requested bigint,p_budget bigint)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
begin
 perform ap_mail_mutate('heartbeat',p_workspace,gen_random_uuid(),repeat('a',64),jsonb_build_object('claim',p_claim));
 return ap_storage_reserve('mail',p_workspace,(p_claim->>'job_id')::uuid,p_bucket,p_requested,p_budget);
end $$;

alter table public.ap_mail_connections add column recompare_cursor uuid;
create function public.ap_mail_queue_stale(p_workspace uuid,p_connection uuid,p_limit integer)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare h ap_workspaces; c ap_mail_connections; item record; last_id uuid; n integer=0;
begin
 if p_limit is null or p_limit not between 1 and 50 then raise exception 'invalid'; end if;
 perform pg_advisory_xact_lock(hashtext('ap-mail:'||p_workspace::text));
 select * into h from ap_workspaces where id=p_workspace for update;
 select * into c from ap_mail_connections where workspace_id=p_workspace and id=p_connection for update;
 if c.id is null then raise exception 'not_configured'; end if;
 if not c.active or c.paused then return jsonb_build_object('queued',0); end if;
 for item in select r.id,j.id job_id,j.dispatch_generation from ap_mail_receipts r
  join ap_mail_preliminary p on p.workspace_id=r.workspace_id and p.receipt_id=r.id
  join ap_statements s on s.workspace_id=r.workspace_id and s.id=r.statement_id
  join ap_statement_revisions v on v.workspace_id=s.workspace_id and v.id=s.current_revision_id
  join ap_mail_jobs j on j.workspace_id=r.workspace_id and j.receipt_id=r.id
  where r.workspace_id=p_workspace and r.connection_id=c.id and r.account_id=c.account_id and j.state='done'
   and s.current_revision_id=r.owned_revision_id and s.version=1 and not s.completed and not s.archived
   and v.doc=r.extraction and v.doc->'confirmed'='false'::jsonb
   and (c.recompare_cursor is null or r.id>c.recompare_cursor)
   and (p.source_pin->>'import_id' is distinct from h.active_import_id::text or
        p.source_pin->>'import_version' is distinct from h.import_version::text or
        p.source_pin->>'working_set_id' is distinct from h.active_working_set_id::text or
        p.source_pin->>'working_version' is distinct from h.working_set_version::text or
        p.source_pin->>'protection_epoch' is distinct from h.bill_protection_epoch::text or
        p.source_pin->>'rule_version' is distinct from 'ap-match-v4')
   order by r.id limit p_limit for update of r,j loop
  -- A finished comparison is new work; dispatch repair never resets a failed cycle.
  update ap_mail_jobs set state='queued',mode='recompare',attempts=0,dispatch_generation=dispatch_generation+1,
   connection_generation=c.generation,lease_until='-infinity',next_retry_at=now(),updated_at=now() where id=item.job_id;
  update ap_mail_receipts set status='queued',reason=null,version=version+1,updated_at=now() where id=item.id;
  insert into ap_mail_outbox(workspace_id,job_id,dispatch_generation) values(p_workspace,item.job_id,item.dispatch_generation+1);
  last_id=item.id;n=n+1;
 end loop;
 update ap_mail_connections set recompare_cursor=last_id where id=c.id;
 return jsonb_build_object('queued',n);
end $$;
revoke all on function public.ap_mail_reserve(uuid,jsonb,text,bigint,bigint),public.ap_mail_queue_stale(uuid,uuid,integer) from public,anon,authenticated;
grant execute on function public.ap_mail_reserve(uuid,jsonb,text,bigint,bigint),public.ap_mail_queue_stale(uuid,uuid,integer) to service_role;
commit;

