"""One renewable workspace slot; every external boundary precedes a fenced write."""
from dataclasses import asdict
import os
from pathlib import Path
import tempfile
import threading
from .contracts import Claim,MailError,MAX_FILE_BYTES,normalize_extraction,payload_digest
from .gmail import attachment_parts

PARSER_VERSION='statement-pdf-v1'
TRANSIENT=frozenset(('unavailable','quota','conflict','stale_source'))


class LeaseGuard:
    def __init__(self,repository,claim,clock):
        self.repo,self.claim,self.clock=repository,claim,clock;self.deadline=clock()+590
        self.stop=threading.Event();self.failure=None;self.thread=None
    def renew(self):
        self.check();self.repo.mutate('heartbeat',{'claim':asdict(self.claim)});self.check()
        return True
    def check(self,claim=None):
        if claim is not None and claim!=self.claim:raise MailError('stale_claim')
        if self.failure:raise MailError(self.failure)
        if self.clock()>=self.deadline:raise MailError('unavailable')
        return True
    def _loop(self):
        while not self.stop.wait(15):
            try:self.renew()
            except Exception as error:
                self.failure=error.code if isinstance(error,MailError) else 'unavailable';return
    def __enter__(self):
        self.renew();self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set()
        if self.thread:self.thread.join(timeout=21)


class MailProcessor:
    def __init__(self,repository,gmail,extractor,sources,publication,clock):
        self.repo,self.gmail,self.extract,self.sources,self.publication,self.clock=repository,gmail,extractor,sources,publication,clock
        self.lease=None

    def authorize(self,claim):
        if self.lease is None:raise MailError('stale_claim')
        return self.lease.check(claim)

    def _download(self,receipt):
        if receipt.get('account_id')!=self.gmail.account_id:raise MailError('wrong_account')
        self.gmail.profile()
        message=self.gmail.message(receipt['message_id'])
        if self.gmail.label_id not in message.get('labelIds',[]):raise MailError('withdrawn')
        parts=attachment_parts(message,on_error=lambda code:None);part=next((p for p in parts if p.part_path==receipt['part_path']),None)
        if not part or part.size!=receipt['declared_size'] or part.filename!=receipt['filename']:raise MailError('withdrawn')
        if part.attachment_id!=receipt.get('attachment_id',part.attachment_id):raise MailError('withdrawn')
        self.lease.check()
        raw=part.inline_bytes if part.inline_bytes is not None else self.gmail.attachment(receipt['message_id'],part.attachment_id)
        if not isinstance(raw,bytes) or len(raw)>MAX_FILE_BYTES:raise MailError('limit')
        if len(raw)!=part.size or not raw.startswith(b'%PDF-'):raise MailError('unreadable')
        return raw

    def run(self,job_id,dispatch_generation):
        claim=None
        try:
            reply=self.repo.mutate('claim',dict(job_id=job_id,dispatch_generation=dispatch_generation))
            if not reply.get('claim'):return dict(status='not_claimed',retry=reply.get('retry',True))
            claim=Claim(**reply['claim'])
            self.lease=LeaseGuard(self.repo,claim,self.clock)
            with self.lease:
                receipt=self.repo.receipt(claim.receipt_id);self.lease.check()
                doc=receipt.get('extraction')
                if doc is None:
                    if claim.mode=='recompare':raise MailError('invalid')
                    if receipt.get('sha256'):
                        raw=self.repo.original_bytes(receipt);sha=receipt['sha256']
                    else:
                        self.repo.reserve_original(claim,receipt['declared_size'])
                        raw=self._download(receipt);self.lease.renew()
                        sha=self.repo.copy_original(claim,raw)
                    self.lease.check()
                    with tempfile.TemporaryDirectory(prefix='ap-mail-original-') as folder:
                        os.chmod(folder,0o700);path=Path(folder)/'statement.pdf';path.write_bytes(raw);os.chmod(path,0o600)
                        del raw
                        doc=self.extract(path,receipt['filename'],timeout_seconds=max(1,min(580,self.lease.deadline-self.clock())),heartbeat=self.lease.check)
                    doc=normalize_extraction(doc,claim.receipt_id,sha);self.lease.renew()
                    self.repo.mutate('save_extraction',dict(claim=asdict(claim),doc=doc,parser_version=PARSER_VERSION,extraction_digest=payload_digest(doc)))
                self.lease.check();source=self.sources.prepare(doc,claim)
                assessment=self.publication.assess(doc,claim,source['pin']);self.lease.check()
                self.sources.assert_current(source['pin'],claim);self.lease.renew()
                evidence={**source['evidence'],'freshness':source.get('freshness')}
                result=self.publication.publish(doc,assessment,evidence,claim,source['pin'])
                return {**result,'retry':False}
        except Exception as error:
            code=error.code if isinstance(error,MailError) else 'unavailable'
            if claim and code!='stale_claim':
                try:
                    payload=dict(claim=asdict(claim),reason=code)
                    if code in TRANSIENT:self.repo.mutate('release_retry',{**payload,'delay_seconds':60})
                    else:self.repo.mutate('needs_attention',payload)
                except MailError:pass # Lost ownership: reconciler repairs the old attempt.
            return dict(status='retry' if code in TRANSIENT else 'needs_attention',code=code,retry=claim is None and code in TRANSIENT)
        finally:self.lease=None
