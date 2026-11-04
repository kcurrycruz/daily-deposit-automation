"""Durable outbox dispatch. The database, not task retention, owns job identity."""
from dataclasses import dataclass
import re
from urllib.parse import urlparse

from .contracts import MailError, canonical, identifier, natural, payload_digest


@dataclass(frozen=True)
class DispatchConfig:
    queue: str
    processor_url: str
    service_account: str
    audience: str

    def __post_init__(self):
        match=re.fullmatch(r'projects/([a-z][a-z0-9-]{4,62})/locations/[a-z0-9-]+/queues/[A-Za-z0-9_-]{1,100}',self.queue)
        url=urlparse(self.processor_url)
        if (not match or url.scheme!='https' or not url.hostname or not url.hostname.endswith('.run.app') or
                url.username or url.password or url.port is not None or url.path!='/process' or url.query or url.fragment or
                self.audience!='https://'+url.hostname):raise MailError('invalid')
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,62}@'+re.escape(match[1])+r'\.iam\.gserviceaccount\.com',self.service_account):
            raise MailError('invalid')


@dataclass(frozen=True)
class DispatchSummary:
    sent: int = 0
    failed: int = 0
    recovered: int = 0


class TaskDispatcher:
    """Tasks adapter maps AlreadyExists/NotFound/quota to safe MailError codes."""
    def __init__(self, repository, tasks_client, config):
        self.repo,self.tasks,self.config=repository,tasks_client,config

    def _name(self, row):
        if row['workspace_id']!=self.repo.config.workspace_id:raise MailError('denied')
        ident=identifier(row['job_id']);generation=natural(row['dispatch_generation'],1)
        key=payload_digest([self.repo.config.workspace_id,ident,generation])
        return self.config.queue+'/tasks/'+key

    def _request(self, row, name):
        return dict(parent=self.config.queue,task=dict(name=name,dispatch_deadline={'seconds':600},
            http_request=dict(http_method='POST',url=self.config.processor_url,
                headers={'Content-Type':'application/json'},
                body=canonical(dict(job_id=row['job_id'],dispatch_generation=row['dispatch_generation'])).encode('utf-8'),
                oidc_token=dict(service_account_email=self.config.service_account,audience=self.config.audience))))

    def _active(self):
        conn=self.repo.connection()
        return bool(conn and conn['active'] and not conn['paused'])

    def drain(self, limit=100):
        natural(limit,1,100)
        if not self._active():return DispatchSummary()
        page=self.repo.outbox_page(limit=limit);sent=failed=0
        for row in page['items']:
            name=self._name(row)
            if row['state']!='pending':continue
            try:
                try:
                    result=self.tasks.create_task(request=self._request(row,name))
                    actual=result.get('name') if isinstance(result,dict) else getattr(result,'name',None)
                    if actual!=name:raise MailError('unavailable')
                except MailError as error:
                    if error.code!='conflict':raise
                self.repo.mutate('outbox_sent',dict(job_id=row['job_id'],dispatch_generation=row['dispatch_generation'],task_name=name))
                sent+=1
            except MailError:
                failed+=1
                # An unknown create outcome stays pending; deterministic naming handles its retry.
                self.repo.mutate('outbox_delay',dict(job_id=row['job_id'],dispatch_generation=row['dispatch_generation'],delay_seconds=60))
        return DispatchSummary(sent,failed)

    def reconcile(self, limit=100):
        natural(limit,1,100)
        # Expired jobs must leave Scanning even while discovery is paused.
        repaired=self.repo.mutate('reconcile',{'limit':limit})
        recovered=repaired.get('recovered',0);failed=0
        if not self._active():return DispatchSummary(recovered=recovered)
        connection=self.repo.connection()
        page=self.repo.outbox_page(cursor=connection.get('dispatch_cursor'),limit=limit,state='sent')
        for row in page['items']:
            name=self._name(row)
            if row['state']!='sent':continue
            if row.get('task_name')!=name:raise MailError('invalid')
            try:
                result=self.tasks.get_task(request={'name':name})
                actual=result.get('name') if isinstance(result,dict) else getattr(result,'name',None)
                if actual!=name:raise MailError('unavailable')
            except MailError as error:
                if error.code!='not_found':failed+=1;continue
                result=self.repo.mutate('dispatch_missing',dict(job_id=row['job_id'],dispatch_generation=row['dispatch_generation']))
                recovered+=int(result.get('requeued',False))
        self.repo.mutate('dispatch_checkpoint',dict(connection_id=connection['id'],expected_generation=connection['generation'],cursor=page['nextCursor']))
        return DispatchSummary(failed=failed,recovered=recovered)
