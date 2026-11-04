"""Bounded private immutable object transfer; fixed host, no redirects or signed paths."""
import hashlib
import httpx
from .contracts import MailError,MAX_FILE_BYTES


class OriginalStore:
    def __init__(self,config,*,transport=None):self.config,self.transport=config,transport

    def _url(self,sha):
        from .contracts import digest
        key=self.config.workspace_id+'/pdf/'+digest(sha)+'.pdf'
        return self.config.supabase_url.rstrip('/')+'/storage/v1/object/'+self.config.bucket+'/'+key

    def _headers(self):return {'Authorization':'Bearer '+self.config.supabase_secret_key,'apikey':self.config.supabase_secret_key}

    def get(self,sha,size):
        from .contracts import natural
        natural(size,1,MAX_FILE_BYTES)
        try:
            with httpx.Client(transport=self.transport,timeout=20,follow_redirects=False,trust_env=False) as client:
                with client.stream('GET',self._url(sha),headers=self._headers()) as response:
                    if response.status_code!=200 or int(response.headers.get('content-length','0'))>size:raise MailError('storage')
                    result=bytearray()
                    for chunk in response.iter_bytes(65536):
                        if len(result)+len(chunk)>size:raise MailError('storage')
                        result.extend(chunk)
                    if len(result)!=size or not result.startswith(b'%PDF-') or hashlib.sha256(result).hexdigest()!=sha:raise MailError('storage')
                    return bytes(result)
        except MailError:raise
        except Exception:raise MailError('storage') from None

    def put(self,raw):
        if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_FILE_BYTES:raise MailError('limit')
        if not raw.startswith(b'%PDF-'):raise MailError('unreadable')
        sha=hashlib.sha256(raw).hexdigest();url=self._url(sha);headers=self._headers()
        try:
            with httpx.Client(transport=self.transport,timeout=20,follow_redirects=False,trust_env=False) as client:
                try:
                    with client.stream('POST',url,headers={**headers,'Content-Type':'application/pdf','x-upsert':'false'},content=raw) as response:
                        if response.status_code in (200,201):return sha
                except httpx.TransportError:pass
                # Unknown/lost upload response may have committed. Reuse only identical bytes.
                with client.stream('GET',url,headers=headers) as response:
                    if response.status_code!=200:raise MailError('storage')
                    if int(response.headers.get('content-length','0'))>MAX_FILE_BYTES:raise MailError('storage')
                    size=0;hasher=hashlib.sha256()
                    for chunk in response.iter_bytes(65536):
                        size+=len(chunk)
                        if size>len(raw):raise MailError('storage')
                        hasher.update(chunk)
                    if size!=len(raw) or hasher.hexdigest()!=sha:raise MailError('storage')
            return sha
        except MailError:raise
        except Exception:raise MailError('storage') from None
