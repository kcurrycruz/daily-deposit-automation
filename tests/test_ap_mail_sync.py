from datetime import datetime,timezone
import unittest
from fixtures.ap_mail.store_double import MailStore,C
from fixtures.ap_mail.history import Gmail,message,history_event
from fixtures.ap_mail.messages import pdf
from app.ap_mail.contracts import MailError


class SyncTests(unittest.TestCase):
    def test_unrelated_label_changes_never_import_old_baseline_mail(self):
        for field in ('labelsAdded','labelsRemoved'):
            store=MailStore();mail=Gmail({'old':message('old','1700000000000')})
            mail.lists={None:{'messages':[{'id':'old','threadId':'same-thread'}]}}
            self.sync(mail,store).poll(C)
            mail.events[('999',None)]={'historyId':'1001','history':[{'id':'1000',field:[{'message':{'id':'old','threadId':'same-thread'},'labelIds':['STARRED']}]}]}
            self.sync(mail,store).poll(C);self.assertEqual(store.receipts,{},field)
            mail.events[('1001',None)]={'historyId':'1002','history':[history_event('old',added_label=True)]}
            self.sync(mail,store).poll(C);self.assertEqual(len(store.receipts),1)
    def test_each_live_poll_schedules_only_a_bounded_stale_draft_page(self):
        gmail=Gmail({});store=MailStore();calls=[]
        store.queue_stale=lambda limit:calls.append(limit)
        sync=self.sync(gmail,store)
        self.active(store)
        sync.poll(C)
        self.assertEqual(calls,[50])
        store.home['paused']=True;sync.poll(C);self.assertEqual(calls,[50])

    def test_explicit_message_retry_is_durable_and_processes_old_email(self):
        store=MailStore();self.active(store)
        store.home['cursor']['manual_pending']=['old']
        mail=Gmail({'old':message('old','1700000000000')})
        self.sync(mail,store).poll(C)
        self.assertEqual(len(store.receipts),1)
        self.assertEqual(store.home['cursor'].get('manual_pending',[]),[])
    def sync(self,mail,store,monotonic=lambda:0):
        from app.ap_mail.sync import MailSync
        return MailSync(mail,store,lambda:datetime(2026,11,4,12,10,tzinfo=timezone.utc),monotonic)

    def active(self,store):store.home['cursor']={'phase':'live','history_id':'999'}

    def test_baseline_history_bridge(self):
        store=MailStore();mail=Gmail({'old':message('old','1700000000000')})
        mail.lists={None:{'messages':[{'id':'old','threadId':'same-thread'}]}}
        self.sync(mail,store).poll(C)
        self.assertEqual(mail.calls[0],'profile')
        self.assertEqual(store.home['cursor']['phase'],'live')
        self.assertFalse(store.messages['old']['eligible']);self.assertEqual(store.receipts,{})
        mail.events[('999',None)]={'historyId':'1001','history':[history_event('old',added_label=True)]}
        self.sync(mail,store).poll(C)
        self.assertEqual(len(store.receipts),1)
        self.assertTrue(store.messages['old']['eligible'])

    def test_checkpoint_after_each_discovered_page(self):
        store=MailStore();self.active(store)
        mail=Gmail({key:message(key) for key in ['a','b']})
        mail.events[('999',None)]={'historyId':'1001','history':[history_event('a'),history_event('b')]}
        store.fail_message='b'
        result=self.sync(mail,store).poll(C)
        self.assertEqual(result.status,'unavailable')
        self.assertEqual(len(store.receipts),1)
        self.assertNotEqual(store.home['cursor'].get('history_id'),'1001')
        store.fail_message=None
        self.sync(mail,store).poll(C)
        self.assertEqual(len(store.receipts),2)
        self.assertEqual(store.home['cursor']['history_id'],'1001')

    def test_history_expiry_reconcile_and_old_unknown(self):
        store=MailStore();self.active(store)
        mail=Gmail({'old':message('old','1700000000000'),'new':message('new','1793793900000')})
        mail.events[('999',None)]=MailError('not_found')
        mail.anchor='1100';mail.lists={None:{'messages':[{'id':key,'threadId':'same-thread'} for key in ['old','new']]}}
        result=self.sync(mail,store).poll(C)
        self.assertEqual(result.status,'ok')
        self.assertEqual(len(store.receipts),1)
        self.assertEqual(store.messages['old']['error_code'],'historical')
        self.assertFalse(store.messages['old']['eligible'])
        self.assertEqual(store.home['cursor']['history_id'],'1100')

    def test_historical_import_separate_cursor(self):
        store=MailStore();self.active(store)
        store.home['history_request']=dict(id='request-1',after='2026-11-01T00:00:00+00:00',
            before='2026-11-05T00:00:00+00:00',max_messages=1)
        mail=Gmail({'old':message('old')});mail.lists={None:{'messages':[{'id':'old','threadId':'same-thread'}]}}
        self.sync(mail,store).poll(C)
        self.assertEqual(len(store.receipts),1)
        self.assertEqual(store.home['cursor']['history_id'],'999')
        self.assertTrue(store.home['cursor']['historical']['done'])
        self.sync(mail,store).poll(C)
        self.assertEqual(len(store.receipts),1)
        query=next(call[2] for call in mail.calls if isinstance(call,tuple) and call[0]=='list')
        self.assertIn('after:',query);self.assertIn('before:',query)

    def test_label_removed_or_message_deleted(self):
        store=MailStore();self.active(store)
        removed=message('removed');removed['labelIds']=[]
        mail=Gmail({'removed':removed})
        mail.events[('999',None)]={'historyId':'1001','history':[history_event('removed'),history_event('gone')]}
        self.sync(mail,store).poll(C)
        self.assertEqual(store.receipts,{})
        self.assertEqual(store.messages['gone']['error_code'],'withdrawn')
        self.assertFalse(store.messages['removed']['eligible'])

    def test_thousand_message_budget_resume(self):
        store=MailStore();self.active(store)
        mail=Gmail({f'm{i}':message(f'm{i}') for i in range(1000)})
        for page in range(10):
            mail.events[('999',None if page==0 else str(page))]=dict(historyId='1001',
                history=[history_event(f'm{i}') for i in range(page*100,(page+1)*100)],
                **({'nextPageToken':str(page+1)} if page<9 else {}))
        ticks=[0]
        def monotonic():ticks[0]+=1;return ticks[0]
        runner=self.sync(mail,store,monotonic)
        for _ in range(100):
            result=runner.poll(C,budget_seconds=40)
            if not result.next_work:break
        self.assertEqual(len(store.receipts),1000)
        self.assertEqual(store.home['cursor']['history_id'],'1001')
        self.assertLess(ticks[0],4000)

    def test_multiple_inline_parts_and_same_thread_new_message(self):
        store=MailStore();self.active(store)
        parts=[pdf(attachmentId='a'),pdf(data='JVBERi0xLjc')]
        mail=Gmail({'a':message('a',parts=parts),'b':message('b')})
        mail.events[('999',None)]={'historyId':'1001','history':[history_event('a'),history_event('a'),history_event('b')]}
        self.sync(mail,store).poll(C)
        self.assertEqual(len(store.receipts),3)
        self.assertTrue(all('inline_bytes' not in value for value in store.receipts.values()))

    def test_unreadable_message_is_attention_without_fabricating_pdf(self):
        store=MailStore();self.active(store);bad=message('bad',parts=[pdf(data='bad$')])
        mail=Gmail({'bad':bad});mail.events[('999',None)]={'historyId':'1001','history':[history_event('bad')]}
        self.sync(mail,store).poll(C)
        self.assertEqual(store.receipts,{})
        self.assertEqual(store.messages['bad']['error_code'],'unreadable')
        self.assertEqual(store.home['cursor']['history_id'],'1001')

    def test_bad_part_does_not_drop_other_pdfs(self):
        store=MailStore();self.active(store)
        mail=Gmail({'mixed':message('mixed',parts=[pdf(attachmentId='valid'),pdf(data='bad$')])})
        mail.events[('999',None)]={'historyId':'1001','history':[history_event('mixed')]}
        self.sync(mail,store).poll(C)
        self.assertEqual(len(store.receipts),1)
        self.assertEqual(store.messages['mixed']['error_code'],'unreadable')

