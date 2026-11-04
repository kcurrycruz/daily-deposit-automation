import base64
import copy
import unittest
from fixtures.ap_mail.messages import pdf


class MimeTests(unittest.TestCase):
    def test_root_inline_and_nested_pdf_parts(self):
        from app.ap_mail.gmail import attachment_parts
        encoded = base64.urlsafe_b64encode(b'%PDF-1.7').decode().rstrip('=')
        root = attachment_parts({'payload':pdf(data=encoded)})
        self.assertEqual((root[0].part_path, root[0].inline_bytes), ('0', b'%PDF-1.7'))
        nested = attachment_parts({'payload':dict(mimeType='multipart/mixed', parts=[
            dict(mimeType='text/html', body={'data':'ignored'}), pdf(attachmentId='att-1'),
            dict(mimeType='multipart/mixed', parts=[pdf('other.pdf', attachmentId='att-2')])])})
        self.assertEqual([(p.part_path,p.attachment_id) for p in nested], [('0.1','att-1'),('0.2.0','att-2')])
        self.assertTrue(all(p.inline_bytes is None for p in nested))

    def test_non_pdf_and_mime_bombs(self):
        from app.ap_mail.gmail import attachment_parts
        from app.ap_mail.contracts import MailError
        self.assertEqual(attachment_parts({'payload':dict(mimeType='text/plain', body={'data':'not parsed'})}), [])
        deep = pdf(attachmentId='a')
        for _ in range(21): deep=dict(mimeType='multipart/mixed', parts=[deep])
        invalid=[{'payload':deep}, {'payload':dict(parts=[pdf(attachmentId='a') for _ in range(200)])},
                 {'payload':pdf(size=20*1024*1024+1, attachmentId='a')},
                 {'payload':pdf(data='invalid$')}, {'payload':pdf()},
                 {'payload':pdf(attachmentId='a', data='JVBERi0xLjc')},
                 {'payload':pdf(size=True, attachmentId='a')}]
        for value in invalid:
            with self.subTest(value=str(value)[:100]), self.assertRaises(MailError): attachment_parts(value)


class Response:
    def __init__(self, status, data): self.status_code,self.data=status,data
    def json(self): return copy.deepcopy(self.data)


class Transport:
    def __init__(self, replies): self.replies=list(replies);self.calls=[]
    def request(self, method, url, **kwargs):
        self.calls.append((method,url,kwargs))
        return Response(*self.replies.pop(0))


class GmailTests(unittest.TestCase):
    def client(self, replies):
        from app.ap_mail.gmail import GmailClient
        t=Transport(replies)
        return GmailClient(t, lambda:'TEST-TOKEN', 'account-1', 'owner@example.test', 'Label_1'),t

    def test_opaque_history_id(self):
        cursor='123456789012345678901234567890'
        client,t=self.client([(200,{'historyId':cursor,'history':[], 'nextPageToken':'next'})])
        self.assertEqual(client.history(cursor)['historyId'],cursor)
        self.assertEqual(t.calls[0][2]['params']['startHistoryId'],cursor)
        self.assertEqual(t.calls[0][2]['params']['labelId'],'Label_1')

    def test_profile_pins_account_and_email(self):
        from app.ap_mail.contracts import MailError
        client,_=self.client([(200,{'sub':'account-1','email':'owner@example.test','email_verified':True}),
                               (200,{'emailAddress':'owner@example.test','historyId':'999','messagesTotal':1})])
        self.assertEqual(client.profile()['historyId'],'999')
        for identity in [dict(sub='other',email='owner@example.test',email_verified=True),
                         dict(sub='account-1',email='other@example.test',email_verified=True),
                         dict(sub='account-1',email='owner@example.test',email_verified=False)]:
            client,_=self.client([(200,identity)])
            with self.subTest(identity=identity), self.assertRaises(MailError) as e: client.profile()
            self.assertEqual(e.exception.code,'wrong_account')

    def test_label_id_root_message_and_read_only_calls(self):
        client,t=self.client([(200,{'labels':[dict(id='Label_1',name='Renamed')]}),
            (200,{'id':'msg-1','threadId':'thread-1','internalDate':'1793793600000',
                  'labelIds':['Label_1'], 'payload':pdf(attachmentId='att-1')}),
            (200,{'messages':[{'id':'msg-1','threadId':'thread-1'}], 'resultSizeEstimate':1}),
            (200,{'size':8,'data':'JVBERi0xLjc'})])
        self.assertEqual(client.labels()[0]['name'],'Renamed')
        self.assertEqual(client.message('msg-1')['id'],'msg-1')
        self.assertEqual(client.messages()['messages'][0]['id'],'msg-1')
        self.assertEqual(client.attachment('msg-1','att-1'),b'%PDF-1.7')
        self.assertTrue(all(call[0]=='GET' for call in t.calls))
        self.assertTrue(all('TEST-TOKEN' not in call[1] for call in t.calls))

    def test_errors_are_sanitized_and_malformed_success_rejected(self):
        from app.ap_mail.contracts import MailError
        for status,code in [(401,'auth'),(403,'denied'),(404,'not_found'),(429,'quota'),(503,'unavailable')]:
            client,_=self.client([(status,{'error':'SECRET PDF TEXT'})])
            with self.subTest(status=status), self.assertRaises(MailError) as e: client.history('999')
            self.assertEqual(e.exception.code,code)
            self.assertNotIn('SECRET',str(e.exception))
        client,_=self.client([(200,{'historyId':123,'history':[]})])
        with self.assertRaises(MailError): client.history('999')
        client,_=self.client([(200,{'labels':[]})])
        with self.assertRaises(MailError) as e: client.labels()
        self.assertEqual(e.exception.code,'label_missing')

