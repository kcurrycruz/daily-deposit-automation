"""Opt-in synthetic cloud acceptance. No migration, queue enable or email sending."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import re
import threading
import time
from urllib.parse import urlparse
from uuid import uuid4
from app.ap_mail.contracts import MailConfig,MailError,ReceiptKey,receipt_id

PRODUCTION_REF='uhwpnbntjsopuilouize'

def integration_target(env):
    if env.get('AP_MAIL_SYNTHETIC_INTEGRATION')!='1':return None
    ref=env.get('AP_MAIL_ALLOW_TEST_PROJECT','');workspace=env.get('AP_MAIL_ALLOW_TEST_WORKSPACE','')
    if (env.get('AP_MAIL_SYNTHETIC_ATTESTATION')!='synthetic-only' or not ref or ref==PRODUCTION_REF or
        env.get('AP_MAIL_SUPABASE_URL')!='https://'+ref+'.supabase.co' or
        PRODUCTION_REF in env.get('AP_MAIL_SUPABASE_URL','') or not workspace or env.get('AP_MAIL_WORKSPACE_ID')!=workspace):raise MailError('denied')
    from app.ap_mail.contracts import identifier
    identifier(workspace)
    return {'project_ref':ref,'workspace_id':workspace}

def run_integration(env):
    integration_target(env)
    try:return _run_integration(env)
    except MailError:raise
    except Exception:raise MailError('unavailable') from None

def _run_integration(env):
    target=integration_target(env)
    if target is None:raise MailError('denied')
    import logging
    logging.disable(logging.CRITICAL)
    # Imports/credentials/network are below the explicit production/allowlist gate.
    from dataclasses import asdict
    import httpx
    from supabase import create_client
    from supabase.client import ClientOptions
    from app.ap_mail.repository import MailRepository
    from app.ap_mail.gmail import GmailClient,attachment_parts
    from app.ap_mail.dispatch import TaskDispatcher,DispatchConfig
    from workers.ap_mail.runtime import BoundedTransport,GmailTokens,SecretStore,Tasks
    from workers.ap_mail.smoke import synthetic_pdf
    config=MailConfig(env['AP_MAIL_SUPABASE_URL'],env['AP_MAIL_SUPABASE_KEY'],target['workspace_id'],env['AP_MAIL_BUCKET'],env['AP_MAIL_CONNECTION_ID'],'processor')
    project=env['AP_MAIL_GOOGLE_PROJECT']
    if project!=env['AP_MAIL_ALLOW_GOOGLE_PROJECT'] or not re.fullmatch(r'[a-z][a-z0-9-]{4,62}',project):raise MailError('denied')
    dispatch_config=DispatchConfig(env['AP_MAIL_QUEUE'],env['AP_MAIL_PROCESSOR_URL'],env['AP_MAIL_TASK_CALLER'],env['AP_MAIL_PROCESSOR_AUDIENCE'])
    if not dispatch_config.queue.startswith('projects/'+project+'/') or not env['AP_MAIL_GMAIL_SECRET'].startswith('projects/'+project+'/secrets/'):raise MailError('denied')
    def repository():return MailRepository(config,create_client(config.supabase_url,config.supabase_secret_key,
        ClientOptions(auto_refresh_token=False,persist_session=False,postgrest_client_timeout=10,storage_client_timeout=10)))
    repo=repository();connection=repo.connection()
    if not connection or not connection['active'] or connection['paused'] or connection['secret_ref']!=env['AP_MAIL_GMAIL_SECRET']:raise MailError('not_configured')
    secret=SecretStore().read(env['AP_MAIL_GMAIL_SECRET']+'/versions/latest')
    gmail=GmailClient(BoundedTransport(),GmailTokens(secret,connection),connection['account_id'],connection['email'],connection['label_id'])
    gmail.profile();gmail.labels();mid=env['AP_MAIL_SYNTHETIC_MESSAGE_ID'];message=gmail.message(mid)
    if gmail.label_id not in message.get('labelIds',[]):raise MailError('withdrawn')
    parts=attachment_parts(message)
    if len(parts)!=1:raise MailError('invalid')
    part=parts[0];raw=part.inline_bytes if part.inline_bytes is not None else gmail.attachment(mid,part.attachment_id)
    expected=hashlib.sha256(synthetic_pdf()).hexdigest()
    if hashlib.sha256(raw).hexdigest()!=expected:raise MailError('denied') # Never persist a financial/company PDF in this test.
    real_id=receipt_id(ReceiptKey(config.workspace_id,connection['account_id'],mid,part.part_path));contender=str(uuid4())
    try:repo.receipt(real_id)
    except MailError as error:
        if error.code!='not_found':raise
    else:raise MailError('conflict') # Acceptance needs a fresh owner-selected synthetic email, not an old result.
    meta=dict(message_id=mid,thread_id=message['threadId'],received_at=datetime.fromtimestamp(int(message['internalDate'])/1000,timezone.utc).isoformat(),
        sender='Synthetic acceptance',subject='Synthetic acceptance',eligible=True,error_code=None)
    def receipt(rid,path):return dict(id=rid,message_id=mid,part_path=path,filename=part.filename,mime_type='application/pdf',declared_size=part.size,
        attachment_id=part.attachment_id,status='queued',reason=None)
    # Test-only contender is deliberately never dispatched/read from Gmail.
    repo.inventory_commit(connection,[meta],[receipt(real_id,part.part_path),receipt(contender,'0.999')],connection['cursor'])
    barrier=threading.Barrier(2)
    def claim(job):
        separate=repository();barrier.wait(timeout=10)
        return separate.mutate('claim',dict(job_id=job,dispatch_generation=1))['claim']
    with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(claim,[real_id,contender]))
    winners=[item for item in claims if item]
    if len(winners)!=1:raise MailError('conflict')
    winner=winners[0]
    repo.mutate('needs_attention',dict(claim=winner,reason='unavailable'))
    other=contender if winner['receipt_id']==real_id else real_id
    if other==contender:
        skipped=repo.mutate('claim',dict(job_id=contender,dispatch_generation=1))['claim']
        repo.mutate('finish',dict(claim=skipped,status='skipped'))
    else:
        r=repo.receipt(contender)
        repo.mutate('retry',dict(receipt_id=contender,expected_version=r['version']))
        skipped=repo.mutate('claim',dict(job_id=contender,dispatch_generation=2))['claim']
        repo.mutate('finish',dict(claim=skipped,status='skipped'))
    actual=repo.receipt(real_id)
    if actual['status']=='needs_attention':repo.mutate('retry',dict(receipt_id=real_id,expected_version=actual['version']))
    # A real HTTP/Tasks invocation proves the platform + application principal/audience path.
    dispatcher=TaskDispatcher(repo,Tasks(),dispatch_config);dispatcher.drain()
    unsigned=httpx.post(env['AP_MAIL_PROCESSOR_URL'],json={'job_id':real_id,'dispatch_generation':1},timeout=20,follow_redirects=False)
    if unsigned.status_code not in (401,403,404):raise MailError('denied')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        actual=repo.receipt(real_id)
        if actual['status'] in ('awaiting_review','already_imported','needs_attention'):break
        time.sleep(2)
    if actual['status']!='awaiting_review':raise MailError('unavailable')
    saved=repo.original_bytes(actual)
    if hashlib.sha256(saved).hexdigest()!=expected:raise MailError('storage')
    detail=repo.storage.statement(config.workspace_id,actual['statement_id'])
    if detail['doc']['confirmed'] is not False or detail['resolutions'] or detail['results'] or detail['completed']:raise MailError('conflict')
    return dict(concurrent_claims=len(winners),private_storage_verified=True,unsigned_call_denied=True,status=actual['status'])
