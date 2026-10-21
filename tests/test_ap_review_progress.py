import unittest


class ReviewProgressTests(unittest.TestCase):
    def test_saved_revision_progress_uses_saved_results_and_explicit_decisions(self):
        from app.ap_shared.review_progress import review_progress
        revision={'doc':{'confirmed':True},'results':[
            {'id':'a','status':'matched'}, {'id':'b','status':'presence'},
            {'id':'c','status':'ambiguous'}, {'id':'d','status':'missing'}],
            'resolutions':{'a':{'decision':'Follow up with vendor'},
                           'c':{'decision':'Reviewed — no action needed'}}}
        self.assertEqual(review_progress(revision),{'resolved':2,'total':4})

    def test_missing_or_incomplete_saved_evidence_does_not_invent_progress(self):
        from app.ap_shared.review_progress import review_progress
        for revision in ({}, {'doc':{'confirmed':True},'results':[]},
                         {'doc':{'confirmed':False},'results':[{'id':'a','status':'matched'}]},
                         {'doc':{'confirmed':True},'results':[{'oops':1}]}):
            with self.subTest(revision=revision):
                self.assertIsNone(review_progress(revision))

    def test_history_metadata_contains_progress_from_frozen_revision(self):
        from test_ap_shared_repository import BackendTransport, make_repository, STATEMENT, REVISION
        from test_ap_shared_access import CONFIG
        import httpx
        class HistoryTransport(BackendTransport):
            def respond(self,request):
                if request.url.path.endswith('/ap_completion_events'):
                    self.requests.append(request)
                    return httpx.Response(200,json=[{'id':REVISION,'statement_id':STATEMENT,
                        'revision_id':REVISION,'initials':'KC','status':'follow_up',
                        'created_at':'2026-10-21T14:00:00Z','note':''}])
                response=super().respond(request)
                if request.url.path.endswith('/ap_statement_revisions'):
                    rows=response.json();rows[0]['doc']['confirmed']=True
                    rows[0]['results']=[{'id':'a','status':'missing'},{'id':'b','status':'matched'}]
                    return httpx.Response(200,json=rows)
                return response
        transport=HistoryTransport();items=make_repository(transport).history_page(CONFIG.workspace_id,{})['items']
        self.assertEqual(items[0]['progress'],{'resolved':1,'total':2})
        self.assertFalse(any('/ap_bill_records' in str(r.url) for r in transport.requests))
