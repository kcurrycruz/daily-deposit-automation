"""No component operation may bypass session authorization or validation."""
from .access import require_access
from .models import validate_request,ApValidationError
from .repository import ApStoreError

MESSAGES={'validation':'Check the fields and allowed size limits before retrying.',
    'denied':'AP access is locked or expired. Unlock AP again.',
    'conflict':'A colleague saved a newer version. Your edits were not overwritten. Reload latest before saving again.',
    'unavailable':'Shared storage is unavailable. Your work is not saved. Retry when the connection returns.',
    'not_saved':'Your work is not saved. Retry the same operation.'}

def dispatch_request(value,session,config,service,now):
    request_id=value.get('request_id') if type(value) is dict else None
    attempt=value.get('attempt',0) if type(value) is dict else 0
    reply={'version':1,'request_id':request_id,'attempt':attempt if type(attempt) is int and 0<=attempt<=1000000 else None,'ok':False,'data':None,'error':None}
    try:
        auth=require_access(session,config,now)
        request=validate_request(value)
        reply['data']=service.handle(request['action'],request['payload'],request['request_id'],auth)
        # A lock/expiry during an operation must not return financial values.
        require_access(session,config,service.clock() if hasattr(service,'clock') else now)
        reply['ok']=True
    except PermissionError: code='denied'
    except ApValidationError: code='validation'
    except ApStoreError as error: code=error.code if error.code in MESSAGES else 'unavailable'
    except Exception: code='unavailable'
    if not reply['ok']:
        reply['data']=None; reply['error']={'code':code,'message':MESSAGES[code]}
    return reply

