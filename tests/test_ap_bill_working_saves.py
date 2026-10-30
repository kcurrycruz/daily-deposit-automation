import copy
import unittest
from uuid import uuid4
from test_ap_shared_models import valid_doc
from test_ap_shared_service import fixture
from app.ap_shared.models import RULE_VERSION
from test_ap_bill_working_policy import I,S


class WorkingSaveTests(unittest.TestCase):
    def payload(self):
        doc=valid_doc()
        return dict(statement_id=doc['id'],expected_version=2,doc=doc,resolutions={},import_id=I,
                    mapping_snapshot={},results=[dict(id=doc['rows'][0]['id'],status='range',candidates=[])],
                    rule_version=RULE_VERSION,working_set_id=S,working_version=3)

    def test_scoped_provenance_and_outside_range_result_survive_validation(self):
        service,repo,auth,_,_=fixture();payload=self.payload()
        saved=service.handle('save_revision',payload,str(uuid4()),auth)
        self.assertEqual(saved['version'],3)
        self.assertEqual(service._results(payload['results'])[0]['status'],'range')

    def test_invalid_scope_and_version_are_rejected(self):
        for key,value in [('working_set_id','not-a-uuid'),('working_version',True),('working_version',-1)]:
            service,repo,auth,_,_=fixture();payload=self.payload();payload[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):service.handle('save_revision',payload,str(uuid4()),auth)
            self.assertEqual(repo.requests,{})

    def test_manual_review_cannot_reassign_its_frozen_working_set(self):
        from test_ap_rereview import RereviewTests
        helpers=RereviewTests();payload=helpers.payload();payload['working_set_id']=S;payload['working_version']=None
        service,repo,auth=helpers.service(payload)
        prior=repo.revision_for_save(None,None,None);prior['workingSetId']=I
        repo.revision_for_save=lambda *args:copy.deepcopy(prior)
        with self.assertRaises(ValueError):service.handle('save_revision',payload,str(uuid4()),auth)


if __name__=='__main__':unittest.main()
