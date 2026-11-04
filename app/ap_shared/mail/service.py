from datetime import datetime,timezone
from urllib.parse import urlparse
from ...ap_mail.contracts import MailError
from ..models import allowed,require_uuid,integer,text

FIELDS={
 'mail_status':('', ''),'mail_list':('cursor limit',''),'mail_messages':('cursor limit',''),
 'mail_pause':('connection_id expected_version paused','connection_id expected_version paused'),
 'mail_retry':('receipt_id expected_version','receipt_id expected_version'),
 'mail_history':('connection_id expected_version after before max_messages','connection_id expected_version after before max_messages'),
 'mail_choice':('receipt_id expected_version choice','receipt_id expected_version choice'),
 'mail_message_retry':('connection_id message_id expected_version','connection_id message_id expected_version'),
 'mail_message_skip':('connection_id message_id expected_version','connection_id message_id expected_version'),
 'mail_preview':('receipt_id','receipt_id'),
}

class MailService:
    def __init__(self,repository,config,clock,check):self.repo,self.config,self.clock,self.check=repository,config,clock,check
    def handle(self,action,payload,request_id,authorization):
        self.check(authorization);require_uuid(request_id)
        if not self.repo.enabled():raise MailError('not_configured')
        self.check(authorization)
        if action not in FIELDS:raise MailError('invalid')
        data=allowed(payload,*FIELDS[action])
        for key in ('receipt_id','connection_id'):
            if key in data:require_uuid(data[key])
        if 'expected_version' in data:integer(data['expected_version'],minimum=1)
        if 'message_id' in data:
            from ...ap_mail.gmail import opaque
            opaque(data['message_id'])
        if action in ('mail_list','mail_messages'):
            integer(data.setdefault('limit',50),minimum=1,maximum=50)
            if data.get('cursor') is not None:
                if action=='mail_list':
                    cursor=allowed(data['cursor'],'id discovered_at','id discovered_at');require_uuid(cursor['id'])
                    try:
                        if datetime.fromisoformat(cursor['discovered_at'].replace('Z','+00:00')).utcoffset() is None:raise ValueError
                    except (ValueError,AttributeError,TypeError):raise MailError('invalid') from None
                else:
                    cursor=allowed(data['cursor'],'connection_id message_id','connection_id message_id');require_uuid(cursor['connection_id'])
                    from ...ap_mail.gmail import opaque
                    opaque(cursor['message_id'])
        if action=='mail_pause' and type(data['paused']) is not bool:raise MailError('invalid')
        if action=='mail_choice' and data['choice'] not in ('existing','continue','skip'):raise MailError('invalid')
        if action=='mail_history':
            integer(data['max_messages'],minimum=1,maximum=1000)
            try:
                start=datetime.fromisoformat(data['after'].replace('Z','+00:00'));end=datetime.fromisoformat(data['before'].replace('Z','+00:00'))
                if start.utcoffset() is None or end.utcoffset() is None or start>=end:raise ValueError
            except (ValueError,AttributeError,TypeError):raise MailError('invalid') from None
        self.check(authorization)
        if action=='mail_preview':
            result=self.repo.preview(data['receipt_id']);url=result.get('url');parsed=urlparse(url if isinstance(url,str) else '')
            prefix=self.config.supabase_url.rstrip('/')+'/storage/v1/object/sign/'+self.config.bucket+'/'
            if not isinstance(url,str) or not url.startswith(prefix) or parsed.username or parsed.password or parsed.fragment or not 1<=result.get('expiresIn',0)<=300:raise MailError('denied')
        elif action in ('mail_status','mail_list','mail_messages'):
            name={'mail_status':'status','mail_list':'receipts','mail_messages':'messages'}[action]
            raw=self.repo.read(name,data)
            keys=('connection','counts') if action=='mail_status' else ('items','nextCursor')
            result={key:raw[key] for key in keys}
        else:result=self.repo.control(action.removeprefix('mail_'),data,request_id)
        self.check(authorization);return result
