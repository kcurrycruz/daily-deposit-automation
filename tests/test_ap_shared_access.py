import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.ap_shared.models import ApConfig

NOW=datetime(2026,10,13,12,tzinfo=timezone.utc)
CONFIG=ApConfig('SYNTHETIC-PASSWORD','https://synthetic.supabase.co','SYNTHETIC-SERVER-KEY',
                '00000000-0000-4000-8000-000000000001','hwfc-ap-private')

class TestLimiter:
    def __init__(self): self.tickets={}; self.blocked=False; self.outage=False
    def begin_attempt(self,session_nonce,now):
        if self.outage: raise OSError('Synthetic backend failure')
        if self.blocked: return None
        ticket=str(uuid4()); self.tickets[ticket]=(session_nonce,now)
        return ticket
    def finish_attempt(self,ticket,succeeded,now):
        if self.outage: raise OSError('Synthetic backend failure')
        self.tickets.pop(ticket)

class AccessTests(unittest.TestCase):
    def unlocked(self):
        from app.ap_shared.access import attempt_unlock
        session={'run_result':'preserve Daily'}
        self.assertTrue(attempt_unlock(session,CONFIG.password,CONFIG,TestLimiter(),NOW))
        return session

    def test_password_checked_and_not_retained_in_session(self):
        from app.ap_shared.access import attempt_unlock,require_access
        session={'_ap_password':CONFIG.password}
        self.assertFalse(attempt_unlock(session,'WRONG',CONFIG,TestLimiter(),NOW))
        with self.assertRaises(PermissionError): require_access(session,CONFIG,NOW)
        self.assertNotIn('_ap_password',session)
        self.assertTrue(attempt_unlock(session,CONFIG.password,CONFIG,TestLimiter(),NOW))
        self.assertNotIn(CONFIG.password,repr(session)); self.assertNotIn(CONFIG.supabase_secret_key,repr(session))

    def test_access_expires_at_eight_hours(self):
        from app.ap_shared.access import require_access
        session=self.unlocked()
        self.assertEqual(require_access(session,CONFIG,NOW+timedelta(seconds=28799)).workspace_id,CONFIG.workspace_id)
        with self.assertRaises(PermissionError): require_access(session,CONFIG,NOW+timedelta(seconds=28800))

    def test_rotating_password_key_workspace_or_bucket_rejects_old_access(self):
        from app.ap_shared.access import require_access
        session=self.unlocked()
        for cfg in [replace(CONFIG,password='DIFFERENT'),replace(CONFIG,supabase_secret_key='ROTATED'),
                    replace(CONFIG,workspace_id=str(uuid4())),replace(CONFIG,bucket='other-private')]:
            with self.subTest(config=repr(cfg)), self.assertRaises(PermissionError): require_access(session,cfg,NOW)

    def test_lock_clears_AP_data_but_not_Daily_results(self):
        from app.ap_shared.access import lock_access,require_access
        session=self.unlocked(); nonce=session['_ap_session_nonce']; session['_ap_shared_response']={'private':'synthetic'}
        lock_access(session)
        self.assertEqual(session['run_result'],'preserve Daily'); self.assertNotIn('_ap_shared_response',session)
        self.assertNotIn('_ap_session_nonce',session)
        with self.assertRaises(PermissionError): require_access(session,CONFIG,NOW)
        from app.ap_shared.access import attempt_unlock
        self.assertTrue(attempt_unlock(session,CONFIG.password,CONFIG,TestLimiter(),NOW))
        self.assertNotEqual(session['_ap_session_nonce'],nonce)

    def test_limiter_denial_or_outage_cannot_authorize_correct_password(self):
        from app.ap_shared.access import attempt_unlock,require_access
        for field in ('blocked','outage'):
            limiter=TestLimiter(); setattr(limiter,field,True); session={}
            self.assertFalse(attempt_unlock(session,CONFIG.password,CONFIG,limiter,NOW))
            with self.assertRaises(PermissionError): require_access(session,CONFIG,NOW)

    def test_failed_limiter_acknowledgement_does_not_grant_access(self):
        from app.ap_shared.access import attempt_unlock,require_access
        limiter=TestLimiter(); limiter.finish_attempt=lambda *args: (_ for _ in ()).throw(OSError('unavailable'))
        session={}; self.assertFalse(attempt_unlock(session,CONFIG.password,CONFIG,limiter,NOW))
        with self.assertRaises(PermissionError): require_access(session,CONFIG,NOW)

    def test_nonce_or_plain_dict_cannot_impersonate_server_authorization(self):
        from app.ap_shared.access import require_access
        session=self.unlocked(); session['_ap_session_nonce']=str(uuid4())
        with self.assertRaises(PermissionError): require_access(session,CONFIG,NOW)
        with self.assertRaises(PermissionError): require_access({'_ap_authorization':{'workspace_id':CONFIG.workspace_id}},CONFIG,NOW)

    def test_nonstring_password_is_rejected_without_echo(self):
        from app.ap_shared.access import attempt_unlock
        self.assertFalse(attempt_unlock({},[],CONFIG,TestLimiter(),NOW))

if __name__=='__main__': unittest.main()
