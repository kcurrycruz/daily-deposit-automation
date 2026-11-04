"""Transactional boundary double; actual constraints/fencing run in the SQL harness."""
from copy import deepcopy
from app.ap_mail.contracts import MailError

W='00000000-0000-4000-8000-000000000001'
C='00000000-0000-4000-8000-000000000002'


class MailStore:
    def __init__(self):
        self.home=dict(id=C,workspace_id=W,account_id='account-1',email='owner@example.test',label_id='Label_1',
                       active=True,paused=False,generation=1,version=1,cursor={'phase':'baseline'},
                       activated_at='2026-11-04T12:00:00+00:00',history_request=None)
        self.messages={};self.receipts={};self.fail_message=None;self.commits=[]

    def connection(self): return deepcopy(self.home)
    def queue_stale(self,limit=50):return {'queued':0}

    def messages_known(self, ids): return {key:deepcopy(self.messages[key]) for key in ids if key in self.messages}

    def inventory_commit(self, expected_cursor, messages, receipts, next_cursor, *, completed=False):
        if any(self.home[k]!=expected_cursor[k] for k in ['version','generation','cursor']): raise MailError('conflict')
        if any(m['message_id']==self.fail_message for m in messages): raise MailError('unavailable')
        for msg in messages: self.messages[msg['message_id']]=deepcopy(msg)
        for receipt in receipts:
            if receipt['id'] not in self.receipts: self.receipts[receipt['id']]=deepcopy(receipt)
        self.home['cursor']=deepcopy(next_cursor);self.home['version']+=1
        self.home['error_code']=None
        if completed:self.home['last_success_at']='2026-11-04T12:10:00+00:00'
        self.commits.append((deepcopy(messages),deepcopy(receipts),deepcopy(next_cursor)))
        return dict(version=self.home['version'])

    def mutate(self, operation, payload, request_id=None):
        if operation!='sync_error': raise AssertionError(operation)
        self.home['error_code']=payload['reason']
        return {'saved':True}
