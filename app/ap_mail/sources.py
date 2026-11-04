"""Pinned read facade and shared JavaScript comparison; no human session forgery."""
from datetime import datetime,timezone
from pathlib import Path
import shutil
from .contracts import MailError
from .process import run_json


class SourceReadRepository:
    def __init__(self,mail_repository):
        from app.ap_shared.bills.repository import BillRepository
        from app.ap_shared.bills.working.repository import WorkingRepository
        self.mail=mail_repository;self.base=mail_repository.storage;self.config=mail_repository.config
        self.snapshot=BillRepository(self.base);self.working=WorkingRepository(self.base)

    def read_context(self):
        value=self.mail._read('source_context',{})
        if value.get('home',{}).get('id')!=self.config.workspace_id:raise MailError('denied')
        source=value.get('source')
        if source and source.get('workspace_id')!=self.config.workspace_id:raise MailError('denied')
        return value


class DomainAdapter:
    def run(self,mode,payload,*,read=None,heartbeat=lambda:True):
        if mode not in ('prepare','compare','assess'):raise MailError('invalid')
        node=shutil.which('node')
        if not node:raise MailError('not_configured')
        script=Path(__file__).resolve().parents[2]/'workers/ap_mail/domain.mjs'
        return run_json([node,str(script)],{'mode':mode,**payload},timeout_seconds=120,heartbeat=heartbeat,
                        on_request=read or (lambda action,payload:(_ for _ in ()).throw(MailError('denied'))))


class MailSources:
    def __init__(self,read_api,domain,authorize,clock):
        self.reads,self.domain,self.authorize,self.clock=read_api,domain,authorize,clock

    def _check(self,claim):
        if self.authorize(claim) is False:raise MailError('stale_claim')
        return True

    def assert_current(self,pin,claim):
        self._check(claim);self.reads.assert_current(pin);self._check(claim)

    def _page(self,pin,claim,action,payload):
        self._check(claim)
        # Deliberately no generic service.handle/RPC dispatch in the child protocol.
        if action=='bill_vendors_page':
            if payload.get('import_id')!=pin.import_id or payload.get('working_set_id')!=pin.working_set_id:raise MailError('stale_source')
            return self.reads.vendors_page(pin,payload.get('cursor'),payload.get('limit',500),payload.get('include_archived',False))
        if action=='bill_candidates_page':
            return self.reads.candidates_page(pin,payload.get('query'),payload.get('cursor'),payload.get('limit',500))
        if action=='bill_archived_candidates_page':
            if payload.get('import_id')!=pin.import_id:raise MailError('stale_source')
            return self.reads.archived_references_page(pin,payload.get('references'),payload.get('cursor'),payload.get('limit',500))
        raise MailError('denied')

    def prepare(self,doc,claim):
        self._check(claim);pin=self.reads.pin();info=self.reads.description(pin);mappings=self.reads.mappings(pin)
        result=self.domain.run('prepare',dict(doc=doc,info=info,mappings=mappings),
            read=lambda action,payload:self._page(pin,claim,action,payload),heartbeat=lambda:self._check(claim))
        self.assert_current(pin,claim)
        freshness={'uploadedAt':None,'daysOld':None,'stale':None}
        if info and info.get('created_at'):
            try:
                uploaded=datetime.fromisoformat(info['created_at'].replace('Z','+00:00'))
                if uploaded.utcoffset() is not None:
                    age=max(0,(self.clock().astimezone(timezone.utc)-uploaded).days)
                    freshness=dict(uploadedAt=info['created_at'],daysOld=age,stale=age>=7)
            except (TypeError,ValueError):pass
        return dict(provider=result['provider'],evidence=result['evidence'],mappings=mappings,pin=pin,freshness=freshness)
