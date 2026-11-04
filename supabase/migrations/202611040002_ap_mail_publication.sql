-- Automated evidence is separate from immutable human review history.
begin;
alter table public.ap_mail_preliminary add column metadata jsonb not null default '{}';

create function public.ap_mail_candidates(p_workspace uuid,p_cursor uuid,p_limit integer)
returns jsonb language plpgsql stable security definer set search_path=public,pg_temp as $$
declare h ap_workspaces; item record; items jsonb='[]'; last_id uuid; more boolean;
begin
 if p_limit is null or p_limit not between 1 and 50 then raise exception 'invalid'; end if;
 select * into h from ap_workspaces where id=p_workspace;
 if not found then raise exception 'not_found'; end if;
 for item in select s.id,s.version,s.current_revision_id revision_id,s.completed,s.archived,r.doc
  from ap_statements s join ap_statement_revisions r on r.workspace_id=s.workspace_id and r.id=s.current_revision_id
  where s.workspace_id=p_workspace and (p_cursor is null or s.id>p_cursor) order by s.id limit p_limit loop
  if octet_length((items||jsonb_build_array(to_jsonb(item)))::text)>800000 then
   if items='[]'::jsonb then raise exception 'limit'; end if;
   exit;
  end if;
  items=items||jsonb_build_array(to_jsonb(item));last_id=item.id;
 end loop;
 select exists(select 1 from ap_statements where workspace_id=p_workspace and current_revision_id is not null
   and id>coalesce(last_id,p_cursor,'00000000-0000-0000-0000-000000000000'::uuid)) into more;
 return jsonb_build_object('epoch',h.bill_protection_epoch,'items',items,'nextCursor',case when more then last_id else null end,
  'mappings',(select coalesce(jsonb_object_agg(vendor,bill_vendor),'{}') from ap_vendor_mappings where workspace_id=p_workspace),
  'mappingVersions',(select coalesce(jsonb_object_agg(vendor,version),'{}') from ap_vendor_mappings where workspace_id=p_workspace));
end $$;

create function public.ap_mail_publish(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare h ap_workspaces; j ap_mail_jobs; r ap_mail_receipts; c ap_mail_connections; slot ap_mail_processor_slots;
 cached ap_requests; target ap_statements; revision ap_statement_revisions; f jsonb; pin jsonb; v_assessment jsonb;
 doc jsonb; evidence jsonb; result jsonb; kind text; v_state text; revision_id uuid; versions jsonb;
begin
 if p_workspace is null or p_request_id is null or coalesce(p_payload_hash,'') !~ '^[a-f0-9]{64}$' or
  jsonb_typeof(p_data) is distinct from 'object' or octet_length(p_data::text)>1048576 or
  p_data-array['doc','assessment','evidence','claim','pin']<>'{}'::jsonb or
  not(p_data ?& array['doc','assessment','evidence','claim','pin']) then raise exception 'invalid'; end if;
 -- Same lock order as mail controls, then the lock all human financial writers use.
 perform pg_advisory_xact_lock(hashtext('ap-mail:'||p_workspace::text));
 select * into h from ap_workspaces where id=p_workspace for update;
 if not found or h.mail_schema_version<>1 then raise exception 'not_configured'; end if;
 select * into cached from ap_requests where workspace_id=p_workspace and request_id=p_request_id;
 if found then
  if cached.payload_hash<>p_payload_hash then raise exception 'conflict'; end if;
  return cached.response;
 end if;
 f=p_data->'claim';pin=p_data->'pin';doc=p_data->'doc';evidence=p_data->'evidence';v_assessment=p_data->'assessment';kind=v_assessment->>'kind';
 select * into j from ap_mail_jobs where workspace_id=p_workspace and id=(f->>'job_id')::uuid for update;
 select * into slot from ap_mail_processor_slots where workspace_id=p_workspace for update;
 select * into c from ap_mail_connections where workspace_id=p_workspace and id=j.connection_id;
 if j.id is null or slot.job_id is distinct from j.id or j.state<>'running' or j.lease_until<=now() or slot.lease_until<=now() or
  j.receipt_id is distinct from (f->>'receipt_id')::uuid or
  j.connection_generation is distinct from (f->>'connection_generation')::bigint or c.generation<>j.connection_generation or not c.active or
  j.dispatch_generation is distinct from (f->>'dispatch_generation')::bigint or j.mode is distinct from f->>'mode' or
  j.lease_generation is distinct from (f->>'lease_generation')::bigint or
  slot.generation is distinct from (f->>'slot_generation')::bigint or j.slot_generation<>slot.generation then raise exception 'stale_claim'; end if;
 select * into r from ap_mail_receipts where workspace_id=p_workspace and id=j.receipt_id for update;
 if r.extraction is null or doc is distinct from r.extraction or doc->'confirmed' is distinct from 'false'::jsonb or
  coalesce(r.sha256,'') !~ '^[a-f0-9]{64}$' or r.original_object_key is distinct from p_workspace::text||'/pdf/'||r.sha256||'.pdf' or
  r.actual_size is null or r.extraction_digest is null or r.parser_version is null or
  evidence->'preliminary' is distinct from 'true'::jsonb or jsonb_typeof(evidence->'rows') is distinct from 'array' or
  kind is null or kind not in ('new','duplicate','similar','overlap') then raise exception 'invalid'; end if;
 if h.active_import_id is distinct from (pin->>'import_id')::uuid or h.import_version is distinct from (pin->>'import_version')::bigint or
  h.active_working_set_id is distinct from (pin->>'working_set_id')::uuid or h.working_set_version is distinct from (pin->>'working_version')::bigint or
  h.bill_protection_epoch is distinct from (pin->>'protection_epoch')::bigint or pin->>'rule_version' is distinct from 'ap-match-v4' then raise exception 'stale_source'; end if;
 if h.active_import_id is not null and not exists(select 1 from ap_bill_imports where workspace_id=p_workspace and id=h.active_import_id
  and state='ready' and file_hash=pin->>'source_digest') then raise exception 'stale_source'; end if;
 if h.active_working_set_id is not null and not exists(select 1 from ap_bill_working_sets where workspace_id=p_workspace and id=h.active_working_set_id
  and source_import_id=h.active_import_id and manifest->>'workingDigest'=pin->>'working_digest') then raise exception 'stale_source'; end if;
 select coalesce(jsonb_object_agg(vendor,version),'{}') into versions from ap_vendor_mappings where workspace_id=p_workspace;
 if versions is distinct from pin->'mapping_versions' then raise exception 'stale_source'; end if;

 if r.owned_revision_id is not null then
  select * into target from ap_statements where workspace_id=p_workspace and id=r.statement_id for update;
  select * into revision from ap_statement_revisions where workspace_id=p_workspace and id=target.current_revision_id;
  if target.id is null or target.current_revision_id is distinct from r.owned_revision_id or target.version<>1 or target.completed or target.archived or
   revision.doc is distinct from r.extraction or revision.doc->'confirmed' is distinct from 'false'::jsonb then raise exception 'conflict'; end if;
  revision_id=revision.id;v_state='awaiting_review';
 else
  select * into target from ap_statements where workspace_id=p_workspace and file_hash=r.sha256 for update;
  if target.id is not null then v_state='already_imported';
  else
   if kind<>'new' then
    select * into target from ap_statements where workspace_id=p_workspace and id=(v_assessment->'match'->>'id')::uuid for update;
    if target.id is null or target.current_revision_id is distinct from (v_assessment->'match'->>'revision_id')::uuid or
      target.version is distinct from (v_assessment->'match'->>'version')::integer then raise exception 'conflict'; end if;
   end if;
   if kind='duplicate' or (kind='similar' and r.human_choice->>'choice'='existing') then v_state='already_imported';
   elsif kind='similar' and r.human_choice->>'choice' is distinct from 'continue' then v_state='needs_attention';
   else
    -- No machine comparison is saved as a human review result.
    insert into ap_statements(id,workspace_id,file_hash,original_object_key,filename)
     values((doc->>'id')::uuid,p_workspace,r.sha256,r.original_object_key,r.filename) returning * into target;
    revision_id=gen_random_uuid();perform set_config('ap.revision_working_scope','full',true);
    insert into ap_statement_revisions(id,workspace_id,statement_id,version,doc,rule_version)
     values(revision_id,p_workspace,target.id,1,doc,pin->>'rule_version');
    update ap_statements set version=1,current_revision_id=revision_id,updated_at=now() where id=target.id returning * into target;
    v_state='awaiting_review';
   end if;
  end if;
 end if;
 if v_state='awaiting_review' then
  insert into ap_mail_preliminary(workspace_id,receipt_id,statement_id,revision_id,source_pin,parser_version,extraction_digest,rows,metadata)
   values(p_workspace,r.id,target.id,revision_id,pin,r.parser_version,r.extraction_digest,evidence->'rows',evidence-'rows')
   on conflict(workspace_id,receipt_id) do update set source_pin=excluded.source_pin,rows=excluded.rows,metadata=excluded.metadata,created_at=now();
 end if;
 update ap_mail_receipts set status=v_state,reason=case when v_state='needs_attention' then 'similar' else null end,
  statement_id=case when v_state='needs_attention' then null else target.id end,
  owned_revision_id=case when v_state='awaiting_review' then revision_id else null end,assessment=v_assessment,
  imported_at=case when v_state<>'needs_attention' then coalesce(imported_at,now()) else imported_at end,version=version+1,updated_at=now() where id=r.id;
 update ap_mail_jobs set state=case when v_state='needs_attention' then 'attention' else 'done' end,lease_until='-infinity',updated_at=now() where id=j.id;
 update ap_mail_processor_slots set job_id=null,lease_until='-infinity' where workspace_id=p_workspace;
 insert into ap_mail_attempts(workspace_id,job_id,dispatch_generation,lease_generation,slot_generation,event)
  values(p_workspace,j.id,j.dispatch_generation,j.lease_generation,slot.generation,'published');
 result=jsonb_build_object('status',v_state,'statement_id',case when v_state='needs_attention' then null else target.id end,
  'version',case when v_state='needs_attention' then null else target.version end);
 insert into ap_requests(workspace_id,request_id,payload_hash,response) values(p_workspace,p_request_id,p_payload_hash,result);
 return result;
end $$;
revoke all on function public.ap_mail_candidates(uuid,uuid,integer),public.ap_mail_publish(uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.ap_mail_candidates(uuid,uuid,integer),public.ap_mail_publish(uuid,uuid,text,jsonb) to service_role;
commit;
