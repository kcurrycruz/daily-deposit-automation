"""Session-scoped AP access, checked on the server before every operation."""
from datetime import datetime, timedelta
import hashlib
import hmac
import json
from typing import Mapping, MutableMapping, Protocol
from uuid import uuid4
from .models import ApConfig, Authorization, AUTH_SECONDS, require_uuid

class AccessLimiter(Protocol):
    def begin_attempt(self, session_nonce: str, now: datetime) -> str | None: ...
    def finish_attempt(self, ticket: str, succeeded: bool, now: datetime) -> None: ...

def _fingerprint(config: ApConfig) -> str:
    data=json.dumps([config.password,config.supabase_url,config.workspace_id,config.bucket],ensure_ascii=False).encode('utf-8')
    return hmac.new(config.supabase_secret_key.encode('utf-8'),data,hashlib.sha256).hexdigest()

def attempt_unlock(session: MutableMapping, submitted: str, config: ApConfig, limiter: AccessLimiter, now: datetime) -> bool:
    session.pop('_ap_password',None)
    session.pop('_ap_authorization',None)
    if type(submitted) is not str or now.tzinfo is None or len(submitted.encode('utf-8'))>4096:
        return False
    nonce=session.setdefault('_ap_session_nonce',str(uuid4()))
    try:
        nonce=require_uuid(nonce)
        ticket=limiter.begin_attempt(nonce,now)
        if not ticket: return False
        correct=hmac.compare_digest(submitted.encode('utf-8'),config.password.encode('utf-8'))
        limiter.finish_attempt(ticket,correct,now)
        if not correct: return False
    except Exception:
        # Neither credentials nor backend exception text reaches the browser/log.
        return False
    session['_ap_authorization']=Authorization(config.workspace_id,nonce,now+timedelta(seconds=AUTH_SECONDS),_fingerprint(config))
    return True

def require_access(session: Mapping, config: ApConfig, now: datetime) -> Authorization:
    authorization=session.get('_ap_authorization')
    if (type(authorization) is not Authorization or now.tzinfo is None or
        authorization.workspace_id!=config.workspace_id or
        authorization.session_nonce!=session.get('_ap_session_nonce') or
        now>=authorization.expires_at or
        not hmac.compare_digest(authorization.credential_fingerprint,_fingerprint(config))):
        raise PermissionError('AP access is locked. Unlock AP Statements to continue.')
    return authorization

def lock_access(session: MutableMapping) -> None:
    for key in list(session):
        if key in ('_ap_authorization','_ap_session_nonce','_ap_password') or str(key).startswith('_ap_shared_'):
            session.pop(key,None)
