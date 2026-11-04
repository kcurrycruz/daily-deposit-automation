"""Fixed-workspace human control adapter. No OAuth configuration surface."""
from datetime import datetime,timedelta,timezone
from urllib.parse import unquote,urlparse
from ...ap_mail.contracts import MailError,payload_digest,digest

class MailControlsRepository:
    def __init__(self,base):self.base,self.config=base,base.config
    def _rpc(self,name,args):
        try:
            result=self.base.client.rpc(name,{'p_workspace':self.config.workspace_id,**args}).execute().data
            if not isinstance(result,dict):raise MailError('unavailable')
            return result
        except MailError:raise
        except Exception as error:
            from ...ap_mail.contracts import CODES
            code=getattr(error,'message','');raise MailError(code if code in CODES else 'unavailable') from None
    def enabled(self):
        try:
            rows=self.base.client.table('ap_workspaces').select('mail_schema_version').eq('id',self.config.workspace_id).limit(1).execute().data
            return len(rows)==1 and rows[0].get('mail_schema_version')==1
        except Exception:return False
    def read(self,action,payload):return self._rpc('ap_mail_control_read',dict(p_operation=action,p_data=payload))
    def control(self,action,payload,request_id):
        return self._rpc('ap_mail_control',dict(p_operation=action,p_data=payload,p_request_id=request_id,
            p_payload_hash=payload_digest({'operation':action,'data':payload})))
    def preview(self,receipt_id):
        row=self._rpc('ap_mail_read',dict(p_operation='receipt',p_data={'receipt_id':receipt_id}))
        sha=digest(row.get('sha256'));key=self.config.workspace_id+'/pdf/'+sha+'.pdf'
        if row.get('workspace_id')!=self.config.workspace_id or row.get('id')!=receipt_id or row.get('original_object_key')!=key:raise MailError('denied')
        self.base._private_bucket()
        try:
            value=self.base.client.storage.from_(self.config.bucket).create_signed_url(key,300)
            url=value.get('signedURL') or value.get('signedUrl');parsed=urlparse(url)
            expected=self.config.supabase_url.rstrip('/')+'/storage/v1/object/sign/'+self.config.bucket+'/'+key
            if parsed.scheme!='https' or parsed.username or parsed.password or parsed.fragment or unquote(url.split('?',1)[0])!=expected:raise MailError('denied')
            return dict(url=url,expiresIn=300,expiresAt=(datetime.now(timezone.utc)+timedelta(seconds=300)).isoformat())
        except MailError:raise
        except Exception:raise MailError('unavailable') from None
