"""Checkpoint after discovery, before advancing history. Never parse email HTML."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone

from .contracts import MailError, ReceiptKey, bounded_text, natural, receipt_id
from .gmail import attachment_parts, opaque

TRANSIENT = frozenset(('auth','denied','wrong_account','quota','unavailable','conflict','paused'))


@dataclass(frozen=True)
class PollSummary:
    status: str
    discovered: int = 0
    queued: int = 0
    attention: int = 0
    next_work: bool = False


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.utcoffset() is None: raise ValueError
        return parsed
    except (TypeError, ValueError, AttributeError): raise MailError('invalid') from None


def _header(payload, name, maximum):
    headers=payload.get('headers', [])
    if type(headers) is not list or len(headers)>200: raise MailError('unreadable')
    for item in headers:
        if type(item) is not dict: raise MailError('unreadable')
        if str(item.get('name','')).casefold()==name.casefold():
            value=item.get('value','')
            if type(value) is not str: raise MailError('unreadable')
            return ''.join(c if ord(c)>=32 else ' ' for c in value).encode('utf-8')[:maximum].decode('utf-8',errors='ignore')
    return ''


def _history_pending(result,label_id):
    pending={}
    for event in result.get('history',[]):
        if type(event) is not dict: raise MailError('unreadable')
        for field in ('messagesAdded','labelsAdded','messagesDeleted','labelsRemoved','messages'):
            items=event.get(field, [])
            if type(items) is not list: raise MailError('unreadable')
            for item in items:
                msg=item if field=='messages' else item.get('message',{}) if type(item) is dict else {}
                if type(msg) is not dict: raise MailError('unreadable')
                ident=opaque(msg.get('id'))
                eligible=field=='messagesAdded'
                if field=='labelsAdded':
                    labels=item.get('labelIds',[])
                    if type(labels) is not list or len(labels)>1000:raise MailError('unreadable')
                    for label in labels:opaque(label)
                    eligible=label_id in labels
                pending[ident]=dict(id=ident,eligible=eligible or pending.get(ident,{}).get('eligible',False))
    if len(pending)>1000: raise MailError('limit')
    return list(pending.values())


class MailSync:
    def __init__(self, gmail, repository, clock, monotonic):
        self.gmail,self.repo,self.clock,self.monotonic=gmail,repository,clock,monotonic

    def _save(self, connection, cursor, messages=None, receipts=None, completed=False):
        self.repo.inventory_commit(connection,messages or [],receipts or [],cursor,completed=completed)
        return self.repo.connection()

    def begin_baseline(self, mode='new_only', history_bounds=None):
        if mode not in ('new_only','existing') or (mode=='existing' and history_bounds is None): raise MailError('invalid')
        home=self.repo.connection()
        if not home or not home['active']: raise MailError('not_configured')
        if home['paused']: raise MailError('paused')
        profile=self.gmail.profile(); self.gmail.labels()
        cursor=dict(phase='baseline',anchor=opaque(profile['historyId']))
        if home['cursor'].get('manual_pending'):cursor['manual_pending']=home['cursor']['manual_pending']
        if mode=='existing': cursor['historical']=self._historical(history_bounds)
        return self._save(home,cursor)

    def _historical(self, request):
        if type(request) is not dict: raise MailError('invalid')
        ident=bounded_text(request.get('id'),256)
        start,end=_time(request.get('after')),_time(request.get('before'))
        if start>=end: raise MailError('invalid')
        limit=natural(request.get('max_messages'),1,1000)
        return dict(id=ident,after=start.isoformat(),before=end.isoformat(),max_messages=limit,processed=0,done=False)

    def _message(self, ident, eligible, connection, phase, historical=None):
        known=self.repo.messages_known([ident]).get(ident)
        try:
            msg=self.gmail.message(ident)
        except MailError as error:
            if error.code!='not_found': raise
            return dict(message_id=ident,thread_id=ident,received_at=known.get('received_at') if known else None,
                        sender='',subject='',eligible=False,error_code='withdrawn'),[]
        received=datetime.fromtimestamp(int(msg['internalDate'])/1000,timezone.utc)
        payload=msg['payload']
        meta=dict(message_id=ident,thread_id=msg['threadId'],received_at=received.isoformat(),sender='',subject='',eligible=False,error_code=None)
        if self.gmail.label_id not in msg.get('labelIds',[]): return meta,[]
        if phase=='baseline': eligible=False
        elif historical:
            eligible=_time(historical['after'])<=received<_time(historical['before'])
        elif phase=='recovery':
            eligible=bool(known and known.get('eligible')) or received>=_time(connection['activated_at'])
            if not eligible and not known: meta['error_code']='historical'
        elif not eligible:
            eligible=bool(known and known.get('eligible')) or received>=_time(connection['activated_at'])
            if not eligible and not known: meta['error_code']='historical'
        meta['eligible']=eligible
        try:
            meta['sender']=_header(payload,'From',1024);meta['subject']=_header(payload,'Subject',2048)
            if not eligible: return meta,[]
            issues=[]
            parts=attachment_parts(msg,on_error=issues.append)
            if issues:meta['error_code']=issues[0]
            if not parts: raise MailError('unreadable')
            rows=[dict(id=receipt_id(ReceiptKey(connection['workspace_id'],connection['account_id'],ident,p.part_path)),
                message_id=ident,part_path=p.part_path,filename=p.filename,mime_type=p.mime_type,declared_size=p.size,
                attachment_id=p.attachment_id,status='queued',reason=None) for p in parts]
            return meta,rows
        except MailError as error:
            if error.code in TRANSIENT: raise
            meta['error_code']=error.code
            return meta,[]

    def _list_step(self, home, cursor, historical=False):
        state=cursor['historical'] if historical else cursor
        pending=state.get('pending',[])
        if pending:
            ident=pending[0]['id']
            meta,receipts=self._message(ident,historical,home,cursor['phase'],state if historical else None)
            state['pending']=pending[1:]
            if historical:
                state['processed']+=1
                if state['processed']>=state['max_messages']:state['done']=True;state.pop('pending',None)
            return self._save(home,cursor,[meta],receipts),(1,len(receipts),int(bool(meta.get('error_code'))))
        if state.get('page_loaded'):
            if state.get('page_next'):
                state['page_token']=state.pop('page_next');state.pop('page_loaded',None)
                return self._save(home,cursor),(0,0,0)
            if historical:state['done']=True
            else:
                cursor['phase']='live';cursor['history_id']=cursor.pop('anchor')
            for key in ('page_loaded','page_token','page_next','pending'):state.pop(key,None)
            return self._save(home,cursor),(0,0,0)
        query=None
        if historical:
            query=f"after:{int(_time(state['after']).timestamp())-1} before:{int(_time(state['before']).timestamp())}"
        page=self.gmail.messages(state.get('page_token'),query)
        state.update(page_loaded=True,page_next=page.get('nextPageToken'),
                     pending=[dict(id=opaque(item['id']),eligible=historical) for item in page.get('messages',[])])
        return self._save(home,cursor),(0,0,0)

    def _live_step(self, home, cursor):
        state=cursor.get('live_page')
        if state and state.get('pending'):
            pending=state['pending'];item=pending[0]
            meta,receipts=self._message(item['id'],item['eligible'],home,'live')
            state['pending']=pending[1:]
            return self._save(home,cursor,[meta],receipts),False,(1,len(receipts),int(bool(meta.get('error_code'))))
        if state and not state.get('page_next'):
            cursor['history_id']=state['history_id'];cursor.pop('live_page',None)
            return self._save(home,cursor),False,(0,0,0)
        try:
            page=self.gmail.history(cursor['history_id'],state.get('page_next') if state else None)
        except MailError as error:
            if error.code!='not_found': raise
            # Capture the replacement anchor before reconciliation, just as at baseline.
            cursor=dict(phase='recovery',anchor=self.gmail.profile()['historyId'],
                        **({'manual_pending':cursor['manual_pending']} if cursor.get('manual_pending') else {}),
                        **({'historical':cursor['historical']} if 'historical' in cursor else {}))
            return self._save(home,cursor),False,(0,0,0)
        pending=_history_pending(page,self.gmail.label_id)
        if not pending and not page.get('nextPageToken'):
            cursor['history_id']=page['historyId'];cursor.pop('live_page',None)
            return self._save(home,cursor,completed=True),True,(0,0,0)
        cursor['live_page']=dict(pending=pending,page_next=page.get('nextPageToken'),history_id=page['historyId'])
        return self._save(home,cursor),False,(0,0,0)

    def poll(self, connection_id, budget_seconds=60, *, queue_stale=True):
        if type(queue_stale) is not bool: raise MailError('invalid')
        deadline=self.monotonic()+natural(budget_seconds,1,60)
        counts=[0,0,0];home=None;live_idle=False
        try:
            home=self.repo.connection()
            if not home or home['id']!=connection_id or not home['active']: raise MailError('not_configured')
            if home['paused']: return PollSummary('paused')
            self.gmail.profile();self.gmail.labels()
            if queue_stale:self.repo.queue_stale(50)
            if home['cursor'].get('phase')=='baseline' and not home['cursor'].get('anchor'):
                home=self.begin_baseline()
            for _ in range(10000):
                if self.monotonic()>=deadline: return PollSummary('ok',*counts,next_work=True)
                cursor=deepcopy(home['cursor']);request=home.get('history_request')
                if cursor.get('manual_pending'):
                    ident=cursor['manual_pending'][0]
                    meta,receipts=self._message(ident,True,home,'live')
                    cursor['manual_pending']=cursor['manual_pending'][1:]
                    home=self._save(home,cursor,[meta],receipts)
                    counts=[counts[0]+1,counts[1]+len(receipts),counts[2]+int(bool(meta.get('error_code')))]
                    continue
                if request and request['id']!=cursor.get('historical',{}).get('id'):
                    cursor['historical']=self._historical(request);home=self._save(home,cursor);continue
                phase=cursor['phase']
                if phase in ('baseline','recovery'):home,delta=self._list_step(home,cursor)
                elif phase=='live':
                    if live_idle:
                        if cursor.get('historical') and not cursor['historical']['done']:
                            home,delta=self._list_step(home,cursor,historical=True)
                        else:return PollSummary('ok',*counts,next_work=False)
                    else:home,live_idle,delta=self._live_step(home,cursor)
                else:raise MailError('invalid')
                counts=[a+b for a,b in zip(counts,delta)]
            raise MailError('limit')
        except MailError as error:
            if home:
                try:self.repo.mutate('sync_error',dict(connection_id=home['id'],expected_generation=home['generation'],reason=error.code))
                except MailError:pass
            return PollSummary(error.code,*counts,next_work=True)
