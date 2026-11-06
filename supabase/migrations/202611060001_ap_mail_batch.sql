-- Read-only pull adapter for one mailbox. Existing queue/history stay unchanged.
begin;

create function public.ap_mail_batch_pending(
 p_workspace uuid, p_connection uuid, p_generation bigint,
 p_cursor uuid default null, p_limit integer default 25
) returns jsonb
language plpgsql stable security definer set search_path=public,pg_temp as $$
declare c ap_mail_connections%rowtype; rows jsonb; next_cursor text;
begin
 if p_workspace is null or p_connection is null or p_generation is null or p_generation<1
  or p_limit is null or p_limit not between 1 and 100 then raise exception 'invalid'; end if;
 select * into c from ap_mail_connections where workspace_id=p_workspace and id=p_connection;
 if not found then raise exception 'not_found'; end if;
 if c.generation<>p_generation then raise exception 'conflict'; end if;
 if not c.active or c.paused then return jsonb_build_object('items','[]'::jsonb,'nextCursor',null); end if;

 select coalesce(jsonb_agg(jsonb_build_object('job_id',pending.job_id,'receipt_id',pending.receipt_id,
  'dispatch_generation',pending.dispatch_generation,'mode',pending.mode) order by pending.job_id),'[]'::jsonb)
 into rows from (
  select j.id job_id,j.receipt_id,j.dispatch_generation,j.mode
  from ap_mail_jobs j
  join ap_mail_outbox o on o.workspace_id=j.workspace_id and o.job_id=j.id and o.dispatch_generation=j.dispatch_generation
  join ap_mail_receipts r on r.workspace_id=j.workspace_id and r.id=j.receipt_id
  where j.workspace_id=p_workspace and j.connection_id=c.id and j.connection_generation=c.generation
   and r.connection_id=c.id and r.account_id=c.account_id
   and j.state='queued' and j.attempts<3 and j.next_retry_at<=now()
   and o.state='pending' and o.next_attempt_at<=now() and (p_cursor is null or j.id>p_cursor)
  order by j.id limit p_limit+1
 ) pending;
 if jsonb_array_length(rows)>p_limit then
  next_cursor=rows->(p_limit-1)->>'job_id'; rows=rows-p_limit;
 end if;
 return jsonb_build_object('items',rows,'nextCursor',next_cursor);
end $$;

revoke all on function public.ap_mail_batch_pending(uuid,uuid,bigint,uuid,integer) from public,anon,authenticated;
grant execute on function public.ap_mail_batch_pending(uuid,uuid,bigint,uuid,integer) to service_role;
commit;
