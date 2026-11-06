"""Fixed-repository Gmail grant adapters. Secret values never enter argv or files."""
import json
import os
import subprocess
from app.ap_mail.contracts import MailError, bounded_text

REPOSITORY = 'kcurrycruz/daily-deposit-automation'
SECRET_NAME = 'AP_MAIL_GMAIL_GRANT'
MAX_GRANT_BYTES = 16384


def grant_reference(repository):
    if repository != REPOSITORY:
        raise MailError('denied')
    return 'github:'+REPOSITORY+':'+SECRET_NAME


def _pairs(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise MailError('invalid')
        result[key] = value
    return result


def _grant(payload):
    from .authorize import SCOPES, TOKEN_URI
    try:
        if not isinstance(payload,(str,bytes)) or len(payload.encode() if isinstance(payload,str) else payload)>MAX_GRANT_BYTES:
            raise MailError('limit')
        value=json.loads(payload,object_pairs_hook=_pairs)
        expected={'refresh_token','client_id','client_secret','token_uri','account_id','email','label_id','scopes'}
        if type(value) is not dict or set(value)!=expected:
            raise MailError('invalid')
        for key in expected-{'scopes'}:
            bounded_text(value[key],8192 if key=='client_secret' else 4096)
        if (value['token_uri']!=TOKEN_URI or type(value['scopes']) is not list or
            len(value['scopes'])!=len(SCOPES) or set(value['scopes'])!=set(SCOPES)):
            raise MailError('auth')
        bounded_text(value['account_id'],256);bounded_text(value['email'],320);bounded_text(value['label_id'],256)
        return value
    except MailError:
        raise
    except Exception:
        raise MailError('invalid') from None


class EnvironmentGrantStore:
    def __init__(self,reference,payload):
        if reference!=grant_reference(REPOSITORY):
            raise MailError('denied')
        self.reference,self.payload=reference,payload

    def read(self,reference):
        if reference!=self.reference:
            raise MailError('denied')
        return _grant(self.payload)


class GitHubSecretStore:
    def __init__(self,repository,run=subprocess.run):
        self.reference=grant_reference(repository)
        self.repository,self.run,self.validated=repository,run,False

    def _call(self,args,payload=None):
        # CLI debug/tracing must not turn the stdin body into a diagnostic.
        env={key:value for key,value in os.environ.items()
             if key not in {'GH_DEBUG','DEBUG','GIT_TRACE','GIT_TRACE_CURL','GIT_CURL_VERBOSE'}}
        env['GH_PROMPT_DISABLED']='1'
        env['GH_HOST']='github.com'
        try:
            result=self.run(['gh',*args],input=payload,capture_output=True,timeout=30,
                            env=env,check=False)
            if result.returncode!=0:
                raise MailError('storage' if payload is not None else 'auth')
            if payload is not None:
                return b''
            if len(result.stdout)>MAX_GRANT_BYTES:
                raise MailError('limit')
            return result.stdout
        except MailError:
            raise
        except Exception:
            raise MailError('storage' if payload is not None else 'auth') from None

    def validate(self):
        self._call(['auth','status','--active','--hostname','github.com'])
        try:
            meta=json.loads(self._call(['repo','view',self.repository,'--json','nameWithOwner,isPrivate,viewerPermission']))
            if (meta.get('nameWithOwner')!=self.repository or meta.get('isPrivate') is not False or
                meta.get('viewerPermission') not in ('WRITE','MAINTAIN','ADMIN')):
                raise MailError('denied')
        except MailError:
            raise
        except Exception:
            raise MailError('auth') from None
        self.validated=True

    def add(self,reference,payload):
        if reference!=self.reference:
            raise MailError('denied')
        _grant(payload)
        if not self.validated:
            self.validate()
        self._call(['secret','set',SECRET_NAME,'--repo',self.repository],payload)
        return self.reference
