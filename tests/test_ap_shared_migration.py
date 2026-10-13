import unittest
from uuid import uuid4
from test_ap_shared_service import fixture
from test_ap_shared_models import valid_doc

class MigrationTests(unittest.TestCase):
    def test_migration_requires_explicit_confirmation_and_excludes_demo(self):
        service,repo,auth,_,_=fixture();doc=valid_doc()
        with self.assertRaises(ValueError):service.handle('migrate_legacy',{'confirmed':False,'statements':[{'doc':doc,'resolutions':{}}]},str(uuid4()),auth)
        with self.assertRaises(ValueError):service.handle('migrate_legacy',{'confirmed':True,'statements':[{'doc':{**doc,'demo':True},'resolutions':{}}]},str(uuid4()),auth)
        self.assertEqual(repo.completion_events,[])

    def test_migration_does_not_invent_completion_and_duplicate_ids_reject(self):
        service,repo,auth,_,_=fixture();doc=valid_doc();doc['notes']='Keep previous work'
        repo.transact=lambda operation,w,r,h,data:{'statement_id':data['statement_id'],'version':1,'original_object_id':None}
        payload={'confirmed':True,'statements':[{'doc':doc,'resolutions':{doc['rows'][0]['id']:{'decision':'Reviewed — no action needed','note':'Prior review'}}}]}
        result=service.handle('migrate_legacy',payload,str(uuid4()),auth)
        self.assertEqual(result['migrated_count'],1);self.assertEqual(repo.completion_events,[]);self.assertIsNone(result['statements'][0]['original_object_id'])
        self.assertNotEqual(result['statements'][0]['statement_id'],doc['id'])
        with self.assertRaises(ValueError):service.handle('migrate_legacy',{'confirmed':True,'statements':payload['statements']*2},str(uuid4()),auth)

