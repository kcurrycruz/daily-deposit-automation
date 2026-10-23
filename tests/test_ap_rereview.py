import copy
import subprocess
import unittest
from uuid import uuid4
from test_ap_shared_models import valid_doc
from test_ap_shared_service import fixture
from test_ap_shared_access import CONFIG
from test_ap_shared_repository import BackendTransport, make_repository
from app.ap_shared.models import ApValidationError, RULE_VERSION, validate_statement, validate_resolution


class RereviewTests(unittest.TestCase):
    def test_private_atomic_schema(self):
        result=subprocess.run(['node','tests/fixtures/ap_shared/rereview_schema_checks.mjs'],capture_output=True,text=True,encoding='utf-8',timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Re-review SQL checks passed:',result.stdout)

    def test_review_mode_and_manual_marker_validation(self):
        doc={**valid_doc(),'reviewMode':'manual'}
        self.assertEqual(validate_statement(doc)['reviewMode'],'manual')
        self.assertEqual(validate_statement({**doc,'reviewMode':'latest'})['reviewMode'],'latest')
        for mode in ['bogus',None,True]:
            with self.subTest(mode=mode),self.assertRaises(ApValidationError):validate_statement({**doc,'reviewMode':mode})
        proof={'vendor':doc['vendor'],'reference':'00042','amount':18400,'kind':'invoice','initials':' kc '}
        resolution=validate_resolution({'decision':'Reviewed — no action needed','manualCheck':proof})
        self.assertEqual(resolution['manualCheck']['initials'],'KC')
        for field,value in [('initials',''),('initials','123'),('amount',True),('kind','unknown'),('extra',True)]:
            with self.subTest(field=field),self.assertRaises(ApValidationError):validate_resolution({'manualCheck':{**proof,field:value}})

    def payload(self):
        doc={**valid_doc(),'reviewMode':'manual'}; row=doc['rows'][0]
        result={'id':row['id'],'vendor':doc['vendor'],'invoiceNumber':row['invoiceNumber'],'kind':'invoice','originalAmount':row['amount'],'status':'missing','candidates':[]}
        return dict(statement_id=doc['id'],expected_version=2,doc=doc,resolutions={},import_id=None,mapping_snapshot={},results=[result],rule_version=RULE_VERSION)

    def service(self,payload):
        service,repo,auth,_,_=fixture()
        repo.rereview_enabled=lambda workspace:True
        prior={'doc':copy.deepcopy(payload['doc']),'resolutions':{},'results':copy.deepcopy(payload['results']),
               'importId':payload['import_id'],'mappingSnapshot':payload['mapping_snapshot'],'ruleVersion':payload['rule_version']}
        repo.revision_for_save=lambda workspace,sid,version:copy.deepcopy(prior)
        return service,repo,auth

    def test_manual_save_keeps_pinned_old_rule_and_allows_notes(self):
        payload=self.payload();payload['rule_version']='ap-match-v3'
        service,repo,auth=self.service(payload)
        payload['doc']['notes']='New note, same financial evidence'
        row=payload['results'][0]
        proof={'vendor':row['vendor'],'reference':row['invoiceNumber'],'amount':row['originalAmount'],'kind':row['kind'],'initials':' kc '}
        payload['resolutions']={row['id']:{'decision':'Reviewed — no action needed','note':'Checked in BILL','manualCheck':proof,'at':'forged'}}
        request=str(uuid4());first=service.handle('save_revision',payload,request,auth)
        self.assertEqual(service.handle('save_revision',payload,request,auth),first)
        self.assertEqual(first['version'],3)

    def test_manual_check_time_must_be_carried_from_exact_prior_server_proof(self):
        payload=self.payload();row=payload['results'][0]
        proof={'vendor':row['vendor'],'reference':row['invoiceNumber'],'amount':row['originalAmount'],'kind':row['kind'],'initials':'KC','checkedAt':'2026-10-01T12:00:00Z'}
        payload['resolutions']={row['id']:{'decision':'Reviewed — no action needed','manualCheck':proof}}
        service,repo,auth=self.service(payload)
        prior=repo.revision_for_save(CONFIG.workspace_id,payload['statement_id'],2);prior['resolutions']=copy.deepcopy(payload['resolutions'])
        repo.revision_for_save=lambda *args:copy.deepcopy(prior)
        service.handle('save_revision',payload,str(uuid4()),auth)
        payload['resolutions'][row['id']]['manualCheck']['checkedAt']='2026-01-01T00:00:00Z'
        with self.assertRaises(ApValidationError):service.handle('save_revision',payload,str(uuid4()),auth)

    def test_manual_mode_cannot_be_invented_without_an_authoritative_manual_revision(self):
        payload=self.payload();service,repo,auth=self.service(payload)
        prior=repo.revision_for_save(CONFIG.workspace_id,payload['statement_id'],2)
        prior['doc'].pop('reviewMode')
        repo.revision_for_save=lambda *args:copy.deepcopy(prior)
        with self.assertRaises(ApValidationError):service.handle('save_revision',payload,str(uuid4()),auth)
        self.assertEqual(repo.requests,{})

    def test_manual_save_fails_closed_without_schema_capability(self):
        payload=self.payload();service,repo,auth=self.service(payload)
        repo.rereview_enabled=lambda workspace:False
        with self.assertRaises(ApValidationError):service.handle('save_revision',payload,str(uuid4()),auth)
        self.assertEqual(repo.requests,{})

    def test_repository_reads_the_exact_expected_revision_for_retry_validation(self):
        from test_ap_shared_repository import STATEMENT
        transport=BackendTransport();repo=make_repository(transport)
        prior=repo.revision_for_save(CONFIG.workspace_id,STATEMENT,1)
        self.assertEqual(prior['doc']['id'],STATEMENT)
        query=transport.requests[-1].url.params
        self.assertEqual(query['statement_id'],'eq.'+STATEMENT)
        self.assertEqual(query['version'],'eq.1')
        self.assertEqual(query['workspace_id'],'eq.'+CONFIG.workspace_id)

    def test_manual_save_rejects_changed_financial_evidence_and_forged_identity(self):
        for change in ['amount','vendor','results','import','mapping','rule','not_manual','reference','kind','initials','no_decision']:
            payload=self.payload();service,repo,auth=self.service(payload);row=payload['results'][0]
            proof={'vendor':row['vendor'],'reference':row['invoiceNumber'],'amount':row['originalAmount'],'kind':'invoice','initials':'KC'}
            payload['resolutions']={row['id']:{'decision':'Reviewed — no action needed','manualCheck':proof}}
            if change=='amount':payload['doc']['rows'][0]['amount']+=1
            elif change=='vendor':payload['doc']['vendor']='Other'
            elif change=='results':row['status']='matched'
            elif change=='import':payload['import_id']=str(uuid4())
            elif change=='mapping':payload['mapping_snapshot']={'Synthetic':'Other'}
            elif change=='rule':payload['rule_version']='ap-match-v3'
            elif change=='not_manual':payload['doc']['reviewMode']='latest'
            elif change in ('reference','kind','initials'):proof[change]='123' if change=='initials' else 'bad'
            else:payload['resolutions'][row['id']].pop('decision')
            with self.subTest(change=change),self.assertRaises(ApValidationError):service.handle('save_revision',payload,str(uuid4()),auth)
            self.assertEqual(repo.requests,{})

    def test_mode_aware_reopen_requires_capability_and_legacy_payload_is_unchanged(self):
        service,repo,auth,_,_=fixture();sent=[]
        repo.rereview_enabled=lambda workspace:False
        repo.transact=lambda operation,workspace,request,digest,data:sent.append((operation,data)) or {'version':3}
        payload={'statement_id':str(uuid4()),'expected_version':2,'review_mode':'manual'}
        with self.assertRaises(ApValidationError):service.handle('reopen_statement',payload,str(uuid4()),auth)
        self.assertEqual(sent,[])
        repo.rereview_enabled=lambda workspace:True
        service.handle('reopen_statement',payload,str(uuid4()),auth)
        self.assertEqual(sent[-1],('reopen_statement',payload))
        service.handle('reopen_statement',{k:v for k,v in payload.items() if k!='review_mode'},str(uuid4()),auth)
        self.assertNotIn('review_mode',sent[-1][1])

    def test_bootstrap_advertises_rereview_only_when_migration_marker_exists(self):
        class Transport(BackendTransport):
            def respond(self,request):
                reply=super().respond(request)
                if request.url.path.endswith('/ap_workspaces'):
                    rows=reply.json();rows[0]['rereview_schema_version']=1
                    import httpx
                    return httpx.Response(200,json=rows)
                return reply
        self.assertNotIn('statementRereview',make_repository(BackendTransport()).bootstrap(CONFIG.workspace_id)['capabilities'])
        repo=make_repository(Transport())
        self.assertEqual(repo.bootstrap(CONFIG.workspace_id)['capabilities']['statementRereview'],1)
        self.assertTrue(repo.rereview_enabled(CONFIG.workspace_id))


if __name__=='__main__':unittest.main()
