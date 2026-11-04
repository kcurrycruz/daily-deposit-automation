from copy import deepcopy
from app.ap_mail.contracts import MailError
from fixtures.ap_mail.messages import pdf


def message(ident, received='1793793600000', parts=None):
    return dict(id=ident,threadId='same-thread',internalDate=received,labelIds=['Label_1'],
                payload=dict(mimeType='multipart/mixed',headers=[{'name':'Subject','value':'Synthetic statement'},
                {'name':'From','value':'vendor@example.test'}],parts=parts or [pdf(attachmentId='att-'+ident)]))


class Gmail:
    label_id='Label_1'
    def __init__(self, messages=None):
        self.data=messages or {};self.calls=[];self.anchor='999';self.lists={None:dict(messages=[])};self.events={}
    def profile(self):self.calls.append('profile');return {'historyId':self.anchor}
    def labels(self):return [{'id':'Label_1','name':'AP Statements'}]
    def messages(self,page_token=None,query=None):
        self.calls.append(('list',page_token,query));return deepcopy(self.lists[page_token])
    def history(self,history_id,page_token=None):
        self.calls.append(('history',history_id,page_token))
        result=self.events.get((history_id,page_token),dict(historyId=history_id,history=[]))
        if isinstance(result,Exception):raise result
        return deepcopy(result)
    def message(self,message_id):
        self.calls.append(('message',message_id))
        result=self.data.get(message_id,MailError('not_found'))
        if isinstance(result,Exception):raise result
        return deepcopy(result)


def history_event(ident, *, added_label=False):
    event=dict(id='1000')
    event['labelsAdded' if added_label else 'messagesAdded']=[dict(message={'id':ident,'threadId':'same-thread'},labelIds=['Label_1'])]
    return event
