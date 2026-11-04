begin;
alter table public.ap_mail_messages add column if not exists version bigint not null default 1;
alter table public.ap_mail_messages add column decision text check(decision in ('retry','skip'));

create function public.ap_mail_control(p_operation text,p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare cached ap_requests; c ap_mail_connections; r ap_mail_receipts; j ap_mail_jobs; s ap_statements; m ap_mail_messages;
 fields text; result jsonb; before_at timestamptz; after_at timestamptz; match jsonb;
begin
 fields=case p_operation when 'pause' then 'connection_id expected_version paused' when 'retry' then 'receipt_id expected_version'
  when 'history' then 'connection_id expected_version after before max_messages' when 'choice' then 'receipt_id expected_version choice'
  when 'message_retry' then 'connection_id message_id expected_version' when 'message_skip' then 'connection_id message_id expected_version' end;
 if fields is null or jsonb_typeof(p_data) is distinct from 'object' or p_data-string_to_array(fields,' ')<>'{}'::jsonb or
  not(p_data ?& string_to_array(fields,' ')) or octet_length(p_data::text)>8192 or p_request_id is null or
  coalesce(p_payload_hash,'') !~ '^[a-f0-9]{64}$' then raise exception 'invalid'; end if;
 perform pg_advisory_xact_lock(hashtext('ap-mail:'||p_workspace::text));
 perform 1 from ap_workspaces where id=p_workspace and mail_schema_version=1 for update;
 if not found then raise exception 'not_configured'; end if;
 select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
 if found then
  if cached.payload_hash<>p_payload_hash then raise exception 'conflict'; end if;
  return cached.response;
 end if;
 if p_operation in ('pause','history','message_retry','message_skip') then
  select * into c from ap_mail_connections where workspace_id=p_workspace and id=(p_data->>'connection_id')::uuid for update;
  if not found or not c.active then raise exception 'not_configured'; end if;
  if p_operation in ('pause','history') and c.version is distinct from (p_data->>'expected_version')::bigint then raise exception 'conflict'; end if;
 end if;
 if p_operation='pause' then return ap_mail_mutate('pause',p_workspace,p_request_id,p_payload_hash,p_data);
 elsif p_operation in ('retry','choice') then
  select * into r from ap_mail_receipts where workspace_id=p_workspace and id=(p_data->>'receipt_id')::uuid for update;
  if not found then raise exception 'not_found'; end if;
  if r.version is distinct from (p_data->>'expected_version')::bigint then raise exception 'conflict'; end if;
  select * into j from ap_mail_jobs where workspace_id=p_workspace and receipt_id=r.id;
  if j.state='running' and j.lease_until>now() then raise exception 'conflict'; end if;
  if p_operation='retry' then return ap_mail_mutate('retry',p_workspace,p_request_id,p_payload_hash,p_data); end if;
  if r.status<>'needs_attention' or r.reason<>'similar' or coalesce(p_data->>'choice','') not in ('existing','continue','skip') then raise exception 'invalid'; end if;
  if p_data->>'choice'='skip' then
   update ap_mail_receipts set status='skipped',reason=null,version=version+1,human_choice=jsonb_build_object('choice','skip'),updated_at=now() where id=r.id;
   update ap_mail_jobs set state='done' where receipt_id=r.id;
   result=jsonb_build_object('saved',true);
  else
   match=r.assessment->'match';
   select * into s from ap_statements where workspace_id=p_workspace and id=(match->>'id')::uuid for update;
   if s.id is null or s.version is distinct from (match->>'version')::integer or s.current_revision_id is distinct from (match->>'revision_id')::uuid then raise exception 'conflict'; end if;
   update ap_mail_receipts set human_choice=jsonb_build_object('choice',p_data->>'choice','match',match),updated_at=now() where id=r.id;
   -- The worker reassesses from current evidence; this endpoint cannot supply a claim.
   return ap_mail_mutate('retry',p_workspace,p_request_id,p_payload_hash,p_data-'choice');
  end if;
 elsif p_operation='history' then
  after_at=(p_data->>'after')::timestamptz;before_at=(p_data->>'before')::timestamptz;
  if after_at is null or before_at is null or after_at>=before_at or coalesce((p_data->>'max_messages')::integer,0) not between 1 and 1000 then raise exception 'invalid'; end if;
  update ap_mail_connections set history_request=jsonb_build_object('id',p_request_id,'after',after_at,'before',before_at,
    'max_messages',(p_data->>'max_messages')::integer),version=version+1 where id=c.id;
  result=jsonb_build_object('saved',true,'version',c.version+1);
 elsif p_operation in ('message_retry','message_skip') then
  select * into m from ap_mail_messages where workspace_id=p_workspace and connection_id=c.id and account_id=c.account_id and message_id=p_data->>'message_id' for update;
  if m.message_id is null then raise exception 'not_found'; end if;
  if m.version is distinct from (p_data->>'expected_version')::bigint then raise exception 'conflict'; end if;
  if p_operation='message_retry' then
   if c.paused then raise exception 'paused'; end if;
   if jsonb_array_length(coalesce(c.cursor->'manual_pending','[]'))>=100 then raise exception 'limit'; end if;
   update ap_mail_connections set cursor=jsonb_set(cursor,'{manual_pending}',coalesce(cursor->'manual_pending','[]')||jsonb_build_array(m.message_id)),version=version+1 where id=c.id;
  end if;
  update ap_mail_messages set error_code=null,decision=case when p_operation='message_retry' then 'retry' else 'skip' end,version=version+1
   where workspace_id=p_workspace and account_id=c.account_id and message_id=m.message_id;
  result=jsonb_build_object('saved',true);
 end if;
 insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,result);
 return result;
end $$;

create function public.ap_mail_control_read(p_operation text,p_workspace uuid,p_data jsonb)
returns jsonb language plpgsql stable security definer set search_path=public,pg_temp as $$
declare items jsonb; lim integer; c ap_mail_connections; counts jsonb;
begin
 if jsonb_typeof(p_data) is distinct from 'object' then raise exception 'invalid'; end if;
 if p_operation='status' then
  if p_data<>'{}'::jsonb then raise exception 'invalid'; end if;
  select * into c from ap_mail_connections where workspace_id=p_workspace and active;
  select coalesce(jsonb_object_agg(status,n),'{}') into counts from (
   select case when s.completed then 'reviewed' when s.archived then 'archived' else r.status end status,count(*) n
   from ap_mail_receipts r left join ap_statements s on s.workspace_id=r.workspace_id and s.id=r.statement_id
   where r.workspace_id=p_workspace group by 1) t;
  return jsonb_build_object('connection',case when c.id is null then null else jsonb_build_object('id',c.id,'email',c.email,'label',c.label_name,
    'paused',c.paused,'version',c.version,'generation',c.generation,'lastCheckedAt',c.last_checked_at,'lastSuccessAt',c.last_success_at,'error',c.error_code,
    'historical',c.cursor->'historical') end,'counts',counts||jsonb_build_object('message_attention',
     (ap_mail_read('status',p_workspace,'{}'))->'counts'->'message_attention'));
 end if;
 lim=coalesce((p_data->>'limit')::integer,50);
 if lim not between 1 and 50 or p_data-array['limit','cursor']<>'{}'::jsonb then raise exception 'invalid'; end if;
 if p_operation='receipts' then
  select coalesce(jsonb_agg(to_jsonb(t)),'[]') into items from (
   select r.id,r.version,r.filename,r.status,r.reason,r.statement_id,r.discovered_at,r.imported_at,m.received_at,m.sender,m.subject,
    case when s.completed then 'reviewed' when s.archived then 'archived' else r.status end display_status,
    r.sha256 is not null original_available,p.receipt_id is not null preliminary_available,
    jsonb_build_object('kind',r.assessment->'kind','repeated',r.assessment->'repeated','added',r.assessment->'added','match',r.assessment->'match') assessment,
    p.metadata preliminary
   from ap_mail_receipts r join ap_mail_messages m on m.workspace_id=r.workspace_id and m.account_id=r.account_id and m.message_id=r.message_id
   left join ap_mail_preliminary p on p.workspace_id=r.workspace_id and p.receipt_id=r.id
   left join ap_statements s on s.workspace_id=r.workspace_id and s.id=r.statement_id
   where r.workspace_id=p_workspace and (p_data->>'cursor' is null or (r.discovered_at,r.id)<
    ((p_data->'cursor'->>'discovered_at')::timestamptz,(p_data->'cursor'->>'id')::uuid))
   order by r.discovered_at desc,r.id desc limit lim) t;
  return jsonb_build_object('items',items,'nextCursor',case when jsonb_array_length(items)=lim then
   jsonb_build_object('id',items->-1->'id','discovered_at',items->-1->'discovered_at') else null end);
 elsif p_operation='messages' then
  select coalesce(jsonb_agg(to_jsonb(t)),'[]') into items from (
   select m.connection_id,m.message_id,m.version,m.received_at,m.discovered_at,m.sender,m.subject,m.error_code
   from ap_mail_messages m where m.workspace_id=p_workspace and m.error_code is not null and
    (p_data->>'cursor' is null or (m.connection_id,m.message_id)>((p_data->'cursor'->>'connection_id')::uuid,p_data->'cursor'->>'message_id'))
    order by m.connection_id,m.message_id limit lim) t;
  return jsonb_build_object('items',items,'nextCursor',case when jsonb_array_length(items)=lim then
   jsonb_build_object('connection_id',items->-1->'connection_id','message_id',items->-1->'message_id') else null end);
 end if;
 raise exception 'invalid';
end $$;
revoke all on function public.ap_mail_control(text,uuid,uuid,text,jsonb),public.ap_mail_control_read(text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.ap_mail_control(text,uuid,uuid,text,jsonb),public.ap_mail_control_read(text,uuid,jsonb) to service_role;
commit;
