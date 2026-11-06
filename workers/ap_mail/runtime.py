"""Fixed-workspace cloud adapters; no Streamlit import or AP password."""
from dataclasses import asdict
from datetime import datetime,timezone
import json
import logging
import os
import re
import threading
import time
import httpx
from app.ap_mail.contracts import MailConfig,MailError,bounded_text
from app.ap_mail.dispatch import DispatchConfig,TaskDispatcher
from app.ap_mail.gmail import GmailClient
from app.ap_mail.repository import MailRepository
from app.ap_mail.sync import MailSync
from .shared import BoundedTransport, DeferredGmail, GmailTokens, build_processor

class SecretStore:
    def __init__(self,client=None):
        if client is None:
            from google.cloud.secretmanager import SecretManagerServiceClient
            client=SecretManagerServiceClient()
        self.client=client
    def read(self,name):
        if not re.fullmatch(r'projects/[a-z][a-z0-9-]{4,62}/secrets/[A-Za-z0-9_-]{1,255}/versions/(?:[1-9][0-9]*|latest)',name):raise MailError('invalid')
        try:
            reply=self.client.access_secret_version(request={'name':name},timeout=10,retry=None)
            if len(reply.payload.data)>16384:raise MailError('limit')
            return json.loads(reply.payload.data)
        except MailError:raise
        except Exception:raise MailError('auth') from None
    def add(self,name,payload):
        if not re.fullmatch(r'projects/[a-z][a-z0-9-]{4,62}/secrets/[A-Za-z0-9_-]{1,255}',name) or len(payload)>16384:raise MailError('invalid')
        try:return self.client.add_secret_version(request={'parent':name,'payload':{'data':payload}},timeout=20,retry=None).name
        except Exception:raise MailError('storage') from None

class Tasks:
    def __init__(self,client=None):
        if client is None:
            from google.cloud.tasks import CloudTasksClient
            client=CloudTasksClient()
        self.client=client
    def _call(self,name,request):
        from google.api_core.exceptions import AlreadyExists,NotFound,ResourceExhausted
        try:return getattr(self.client,name)(request=request,timeout=20,retry=None)
        except AlreadyExists:raise MailError('conflict') from None
        except NotFound:raise MailError('not_found') from None
        except ResourceExhausted:raise MailError('quota') from None
        except Exception:raise MailError('unavailable') from None
    def create_task(self,request):return self._call('create_task',request)
    def get_task(self,request):return self._call('get_task',request)

class Runtime:
    @classmethod
    def from_environment(cls):
        # Never allow third-party HTTP/OAuth debug output to disclose request material.
        logging.disable(logging.CRITICAL)
        config=MailConfig(os.environ['AP_MAIL_SUPABASE_URL'],os.environ['AP_MAIL_SUPABASE_KEY'],os.environ['AP_MAIL_WORKSPACE_ID'],
            os.environ['AP_MAIL_BUCKET'],os.environ['AP_MAIL_CONNECTION_ID'],os.environ['AP_MAIL_ROLE'])
        from supabase import create_client
        from supabase.client import ClientOptions
        client=create_client(config.supabase_url,config.supabase_secret_key,ClientOptions(auto_refresh_token=False,persist_session=False,postgrest_client_timeout=10,storage_client_timeout=10))
        runtime=cls();runtime.config=config;runtime.repo=MailRepository(config,client)
        runtime.audience=bounded_text(os.environ['AP_MAIL_AUDIENCE'],1024);runtime.caller=bounded_text(os.environ['AP_MAIL_CALLER'],320)
        if not runtime.audience.startswith('https://') or not re.fullmatch(r'[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com',runtime.caller):raise MailError('invalid')
        runtime.secret_ref=bounded_text(os.environ['AP_MAIL_GMAIL_SECRET'],1024)
        runtime.secrets=SecretStore();runtime.dispatcher=None;runtime.processor=None;runtime.connection_key=None;runtime.caches=None
        if config.role=='checker':
            dc=DispatchConfig(os.environ['AP_MAIL_QUEUE'],os.environ['AP_MAIL_PROCESSOR_URL'],os.environ['AP_MAIL_TASK_CALLER'],os.environ['AP_MAIL_PROCESSOR_AUDIENCE'])
            runtime.dispatcher=TaskDispatcher(runtime.repo,Tasks(),dc)
        return runtime

    def gmail(self):
        connection=self.repo.connection()
        if not connection or not connection['active']:raise MailError('not_configured')
        if connection['secret_ref']!=self.secret_ref:raise MailError('denied')
        secret=self.secrets.read(self.secret_ref+'/versions/latest')
        return GmailClient(BoundedTransport(),GmailTokens(secret,connection),connection['account_id'],connection['email'],connection['label_id'])

    def poll(self,_):
        try:
            summary=MailSync(self.gmail(),self.repo,lambda:datetime.now(timezone.utc),time.monotonic).poll(self.config.connection_id,budget_seconds=20)
            result=asdict(summary)
        except MailError as error:
            home=self.repo.connection()
            if home:
                self.repo.mutate('sync_error',dict(connection_id=home['id'],expected_generation=home['generation'],reason=error.code))
                self.repo.queue_stale(50)
            result={'status':error.code}
        self.dispatcher.reconcile(budget_seconds=10);self.dispatcher.drain(budget_seconds=10)
        return {**result,'retry':result['status'] in ('unavailable','quota')}
    def reconcile(self,_):
        reply=self.dispatcher.reconcile(budget_seconds=20);sent=self.dispatcher.drain(budget_seconds=20);return dict(status='ok',recovered=reply.recovered,sent=sent.sent,failed=reply.failed+sent.failed)
    def process(self,data):
        processor,self.caches=build_processor(self.repo,self.gmail,self.caches)
        return processor.run(data['job_id'],data['dispatch_generation'])
