"""Shared mailbox transport and processor composition; no cloud dispatch adapters."""
from datetime import datetime, timezone
import threading
import time
import httpx
from app.ap_mail.contracts import MailError

class BoundedTransport:
    def __init__(self,transport=None):self.transport=transport
    def request(self,method,url,*,headers,params,timeout,max_bytes):
        if method!='GET' or not url.startswith(('https://gmail.googleapis.com/','https://openidconnect.googleapis.com/')):raise MailError('denied')
        try:
            with httpx.Client(transport=self.transport,follow_redirects=False,trust_env=False,timeout=timeout) as client:
                with client.stream(method,url,headers=headers,params=params) as response:
                    size=0;body=bytearray()
                    if int(response.headers.get('content-length','0'))>max_bytes:raise MailError('limit')
                    for chunk in response.iter_bytes(65536):
                        size+=len(chunk)
                        if size>max_bytes:raise MailError('limit')
                        body.extend(chunk)
                    return httpx.Response(response.status_code,content=bytes(body))
        except MailError:raise
        except Exception:raise MailError('unavailable') from None

class DeferredGmail:
    """Persisted-extraction comparisons need no Gmail token or mailbox request."""
    def __init__(self,factory):self.factory=factory;self.client=None
    def __getattr__(self,name):
        if self.client is None:self.client=self.factory()
        return getattr(self.client,name)

class GmailTokens:
    def __init__(self,secret,connection):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        if secret.get('account_id')!=connection['account_id'] or secret.get('email','').casefold()!=connection['email'].casefold() or secret.get('label_id')!=connection['label_id']:raise MailError('wrong_account')
        if secret.get('token_uri')!='https://oauth2.googleapis.com/token':raise MailError('invalid')
        from .authorize import SCOPES
        if set(secret.get('scopes',[]))!=set(SCOPES):raise MailError('auth')
        self.credentials=Credentials(None,refresh_token=secret['refresh_token'],client_id=secret['client_id'],client_secret=secret['client_secret'],
            token_uri='https://oauth2.googleapis.com/token',scopes=SCOPES)
        self.request=Request();self.lock=threading.Lock()
    def __call__(self):
        try:
            with self.lock:
                if not self.credentials.valid:self.credentials.refresh(lambda *a,**kw:self.request(*a,**{**kw,'timeout':15}))
                return self.credentials.token
        except Exception:raise MailError('auth') from None


def build_processor(repository, gmail_factory, caches=None):
    from app.ap_mail.processor import MailProcessor
    from app.ap_mail.publication import MailPublication
    from app.ap_mail.sources import MailSources, SourceReadRepository, DomainAdapter
    from app.ap_mail.extraction import extract_private_pdf
    from app.ap_shared.bills.reads import BillReadAPI, ReadCaches
    reads_repository = SourceReadRepository(repository)
    if caches is None:
        caches = ReadCaches(reads_repository)
    processor = MailProcessor(repository, DeferredGmail(gmail_factory), extract_private_pdf,
                              None, None, time.monotonic)
    reads = BillReadAPI(reads_repository,
        lambda: processor.authorize(processor.lease.claim) if processor.lease else False,
        caches, preliminary=True)
    domain = DomainAdapter()
    processor.sources = MailSources(reads, domain, processor.authorize,
                                   lambda: datetime.now(timezone.utc))
    processor.publication = MailPublication(repository, domain, processor.authorize)
    return processor, caches
