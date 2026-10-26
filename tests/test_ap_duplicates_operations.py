import importlib
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dataclasses import replace
from uuid import uuid4, uuid5, UUID
from unittest.mock import patch
from fixtures.ap_shared.bill_exports import export
from fixtures.ap_shared.duplicate_store_double import DuplicateStoreDouble
import test_ap_bill_operations as bill_harness
from test_ap_shared_access import CONFIG,NOW


def setup_detector(test):
    from app.ap_shared.bills.duplicates.artifacts import DuplicateArtifactCache
    from app.ap_shared.bills.duplicates.projection import ReviewProjection
    from app.ap_shared.bills.duplicates.source import DuplicateSource,SourcePreparationCache
    api=importlib.import_module('app.ap_shared.bills.duplicates.operations')
    harness=bill_harness.BillOperationsTests(); harness.setUp(); test.addCleanup(harness.doCleanups)
    job,p=harness.upload(export([{'Invoice #':'271712','Invoice Date':'10/01/2026'},
                                {'Invoice #':'271712X','Invoice Date':'10/01/2026'}])); harness.finish(job,p)
    base=harness.service.repository; base.config=CONFIG
    repo=DuplicateStoreDouble(base,harness.repo)
    source_cache=SourcePreparationCache(harness.repo);test.addCleanup(source_cache.close)
    source=DuplicateSource(base,harness.ops,source_cache)
    registry=api.DuplicateScanRegistry(); test.addCleanup(registry.close)
    cache=DuplicateArtifactCache(repo); test.addCleanup(cache.close)
    projection=ReviewProjection(repo,cache,source,time.monotonic); test.addCleanup(projection.close)
    ops=api.DuplicateOperations(repo,source,registry,cache,projection,CONFIG,lambda:NOW,harness.service.revalidate)
    harness.service.duplicate_operations=ops
    return harness,ops,repo


class DuplicateOperationsTests(unittest.TestCase):
    def setUp(self): self.h,self.ops,self.repo=setup_detector(self)
    def call(self,action,payload,request_id=None):
        return self.ops.handle(action,payload,request_id or str(uuid4()),self.h.auth)
    def ensure(self):
        pin=self.repo.current()
        return self.call('duplicate_ensure',dict(import_id=pin['importId'],expected_import_version=pin['importVersion']))
    def complete(self,p):
        for _ in range(60):
            if p['state']=='ready' and p['projectionReady']: return p
            if p['state']=='ready': p=self.call('duplicate_status',dict(scan_id=p['scanId']))
            else: p=self.call('duplicate_step',dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=p['checkpoint'],restart=False))
        self.fail('scan not completed')
    def test_existing_import_scans_without_statements_and_returns_evidence(self):
        p=self.complete(self.ensure()); self.assertEqual(p['counts']['unreviewed'],1)
        self.assertEqual(p['findingCount'],1);self.assertIsNone(p['errorCode'])
        page=self.call('duplicate_findings_page',dict(scan_id=p['scanId'],filters={},cursor=None,limit=100))
        self.assertEqual(page['total'],1)
        detail=self.call('duplicate_members_page',dict(scan_id=p['scanId'],finding_key=page['findings'][0]['key'],cursor=None,limit=100))
        self.assertEqual([m['bill']['invoiceNumber'] for m in detail['members']],['271712','271712X'])
        self.assertFalse(self.h.service.repository.completion_events)
        self.assertEqual(self.h.repo.active_id,p['importId'])

    def test_revised_rules_select_new_scan_without_reusing_old_review(self):
        from copy import deepcopy
        p=self.complete(self.ensure())
        legacy_id=str(uuid5(UUID(CONFIG.workspace_id),p['importId']+':bill-duplicates-v1'))
        self.assertNotEqual(p['scanId'],legacy_id)
        self.assertEqual(p['scanId'],str(uuid5(UUID(CONFIG.workspace_id),p['importId']+':bill-duplicates-v2')))
        historical=deepcopy(self.repo.scans[p['scanId']])
        historical.update(id=legacy_id,rule_version='bill-duplicates-v1')
        historical['manifest']['ruleVersion']='bill-duplicates-v1'
        historical['manifest']['key']=historical['manifest']['key'].replace('/bill-duplicates-v2/','/bill-duplicates-v1/')
        self.repo.scans[legacy_id]=historical
        old_review=dict(key='e'*64,decision='not_duplicate',initials='KC',note='Old rule review',version=1,
                        at='2026-10-22T12:00:00Z',reviewedImportId=p['importId'])
        self.repo.saved[old_review['key']]=deepcopy(old_review)
        self.ops.projection.invalidate(CONFIG.workspace_id)
        current=self.complete(self.ensure())
        self.assertEqual(current['scanId'],p['scanId'])
        self.assertEqual(current['counts'],dict(all=1,reviewed=0,unreviewed=1))
        self.assertEqual(self.repo.scans[legacy_id],historical)
        self.assertEqual(self.repo.saved[old_review['key']],old_review)

    def test_progress_exposes_only_safe_optional_timing_metadata(self):
        p=self.ensure(); stored=self.repo.scans[p['scanId']]
        stored['updated_at']='2026-10-22T11:59:00+00:00'
        stored['lease_until']='2099-01-01T00:00:00+00:00'
        p=self.call('duplicate_status',dict(scan_id=p['scanId']))
        self.assertEqual(p.get('updatedAt'),'2026-10-22T11:59:00+00:00')
        self.assertEqual(p.get('leaseExpiresAt'),'2099-01-01T00:00:00+00:00')
        self.assertEqual(p.get('serverNow'),NOW.isoformat())
        for secret in ('session_nonce','source_digest','source_pin','source_reader','storage_path','exception'):
            self.assertNotIn(secret,p)
        stored.pop('updated_at'); stored.pop('lease_until')
        p=self.call('duplicate_status',dict(scan_id=p['scanId']))
        self.assertIsNone(p['updatedAt']);self.assertIsNone(p['leaseExpiresAt'])
    def test_packaging_publishes_when_later_requests_use_different_threads(self):
        p=self.ensure()
        for _ in range(30):
            if p['phase']=='packaging': break
            p=self.call('duplicate_step',dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=p['checkpoint'],restart=False))
        self.assertEqual(p['phase'],'packaging')
        with ThreadPoolExecutor(max_workers=1) as request:
            p=request.submit(self.complete,p).result()
        self.assertTrue(p['projectionReady'])
        self.assertEqual(p['counts']['unreviewed'],1)
        self.assertEqual(self.h.repo.active_id,p['importId'])

    def test_lost_step_reply_process_loss_and_second_session(self):
        p=self.ensure(); data=dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=0,restart=False)
        request=str(uuid4()); first=self.call('duplicate_step',data,request)
        repeated=self.call('duplicate_step',data,request)
        self.assertEqual(first['checkpoint'],repeated['checkpoint'])
        with self.assertRaises(PermissionError):
            self.ops.handle('duplicate_step',{**data,'expected_checkpoint':first['checkpoint']},str(uuid4()),replace(self.h.auth,session_nonce=str(uuid4())))
        self.ops.registry.release(p['scanId'])
        next_data={**data,'expected_checkpoint':first['checkpoint']}
        missing=self.call('duplicate_step',next_data)
        self.assertEqual(missing['state'],'restart_required')
        restarted=self.call('duplicate_step',{**next_data,'restart':True})
        self.assertNotEqual(restarted['generation'],p['generation'])
        self.assertEqual(self.complete(restarted)['counts']['unreviewed'],1)
    def test_review_is_server_verified_acknowledged_and_idempotent(self):
        p=self.complete(self.ensure())
        page=self.call('duplicate_findings_page',dict(scan_id=p['scanId'],filters={},cursor=None,limit=100))
        data=dict(scan_id=p['scanId'],import_id=p['importId'],expected_import_version=p['importVersion'],
                  finding_key=page['findings'][0]['key'],expected_review_version=0,decision='not_duplicate',initials=' kc ',note='Legitimate suffix')
        with self.assertRaises(ValueError): self.call('duplicate_review_save',{**data,'finding_key':'f'*64})
        with self.assertRaises(ValueError): self.call('duplicate_review_save',{**data,'verified_key':data['finding_key']})
        request=str(uuid4()); ack=self.call('duplicate_review_save',data,request)
        self.assertEqual(ack['review']['initials'],'KC')
        self.assertEqual(self.call('duplicate_review_save',data,request),ack)
        self.assertEqual(len(self.repo.events),1)
        with self.assertRaises(ValueError): self.call('duplicate_review_save',data)
        p=self.complete(self.call('duplicate_status',dict(scan_id=p['scanId'])))
        self.assertEqual(p['counts']['reviewed'],1)
    def test_immutable_upload_retry_keeps_bill_saved(self):
        p=self.ensure(); self.repo.fail_publish=True
        for _ in range(30):
            try:
                next_p=self.call('duplicate_step',dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=p['checkpoint'],restart=False))
                p=next_p
            except ValueError: break
        self.assertTrue(self.repo.base.objects)
        paths=set(self.repo.base.objects); self.repo.fail_publish=False
        p=self.call('duplicate_status',dict(scan_id=p['scanId']))
        p=self.complete(p)
        self.assertEqual(set(self.repo.base.objects),paths)
        self.assertEqual(self.h.repo.active_id,p['importId'])
    def test_unknown_fields_booleans_stale_source_and_foreign_ids(self):
        p=self.ensure()
        for changes in [dict(expected_checkpoint=True),dict(restart=1),dict(extra='bad')]:
            with self.assertRaises(ValueError):
                self.call('duplicate_step',{**dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=p['checkpoint'],restart=False),**changes})
        with self.assertRaises(ValueError): self.call('duplicate_status',dict(scan_id=str(uuid4())))
        self.h.repo.version+=1
        with self.assertRaises(ValueError): self.ensure_old(p)
    def ensure_old(self,p): return self.call('duplicate_ensure',dict(import_id=p['importId'],expected_import_version=p['importVersion']))

    def test_registry_bounds_server_handles_and_expiry(self):
        from app.ap_shared.bills.duplicates.operations import DuplicateScanRegistry
        now=[0]; registry=DuplicateScanRegistry(monotonic=lambda:now[0]); self.addCleanup(registry.close)
        p=self.ensure(); row=self.repo.scan(p['scanId']); row.update(source_pin=self.repo.current(),fresh=True)
        registry.claim(row,self.h.auth)
        other_auth=replace(self.h.auth,workspace_id=str(uuid4()))
        second={**row,'id':str(uuid4()),'workspace_id':other_auth.workspace_id}
        registry.claim(second,other_auth)
        third_auth=replace(self.h.auth,workspace_id=str(uuid4()))
        with self.assertRaises(ValueError): registry.claim({**row,'id':str(uuid4()),'workspace_id':third_auth.workspace_id},third_auth)
        now[0]=3601
        registry.claim({**row,'id':str(uuid4()),'workspace_id':third_auth.workspace_id},third_auth)

    def test_new_access_session_can_restart_only_after_old_lease_expires(self):
        from app.ap_shared.bills.duplicates.operations import DuplicateOperations
        from app.ap_shared.bills.duplicates.source import DuplicateSource
        from app.ap_shared.bills.operations import BillOperations
        p=self.ensure(); other=replace(self.h.auth,session_nonce=str(uuid4()))
        bills=BillOperations(self.h.repo,CONFIG,lambda:NOW,lambda:other,self.h.builds,self.h.cache)
        ops=DuplicateOperations(self.repo,DuplicateSource(self.h.service.repository,bills),self.ops.registry,
            self.ops.cache,self.ops.projection,CONFIG,lambda:NOW,lambda:other)
        self.repo.scans[p['scanId']]['lease_until']='2026-10-23T12:00:00Z'
        payload=dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=0,restart=True)
        with self.assertRaises(PermissionError): ops.handle('duplicate_step',payload,str(uuid4()),other)
        self.repo.scans[p['scanId']]['lease_until']='2026-10-01T12:00:00Z'
        restarted=ops.handle('duplicate_step',payload,str(uuid4()),other)
        self.assertNotEqual(restarted['generation'],p['generation'])

    def test_legitimate_adventure_suffix_review_survives_weekly_payment_changes(self):
        rows=[{'Vendor Name':'Adventure in Food Trading Company','Invoice #':ref} for ref in ('271712','271712X')]
        job,step=self.h.upload(export(rows));self.h.finish(job,step)
        first=self.complete(self.ensure())
        page=self.call('duplicate_findings_page',dict(scan_id=first['scanId'],filters={},cursor=None,limit=100))
        key=page['findings'][0]['key']
        self.assertEqual(page['findings'][0]['classification'],'possible_duplicate')
        self.call('duplicate_review_save',dict(scan_id=first['scanId'],import_id=first['importId'],expected_import_version=first['importVersion'],
            finding_key=key,expected_review_version=0,decision='not_duplicate',initials='KC',note='Legitimate Adventure suffix bills.'))
        updated=[{**row,'Paid Amount':'138.00','Status':'PaidInFull','Full Payment Date':'10/20/2026'} for row in rows]
        job,step=self.h.upload(export(updated));self.h.finish(job,step)
        second=self.complete(self.ensure());self.assertNotEqual(first['importId'],second['importId'])
        self.assertEqual(second['counts'],dict(all=1,reviewed=1,unreviewed=0))
        page=self.call('duplicate_findings_page',dict(scan_id=second['scanId'],filters={'review':'reviewed'},cursor=None,limit=100))
        self.assertEqual(page['findings'][0]['key'],key);self.assertEqual(page['findings'][0]['review']['decision'],'not_duplicate')
        self.assertEqual(len(self.repo.events),1)

    def test_replacement_releases_only_obsolete_workspace_scan(self):
        first=self.ensure()
        job,step=self.h.upload(export([{'Invoice #':'NEW1234'}]));self.h.finish(job,step)
        second=self.ensure()
        self.assertEqual(second['state'],'running')
        self.assertNotIn(first['scanId'],self.ops.registry.handles)
        self.assertEqual(self.complete(second)['state'],'ready')

    def test_publication_does_not_start_a_second_budget_of_preparation(self):
        now=[0];self.ops.registry.clock=lambda:now[0]
        original=self.repo.put_result
        def slow_publication(*args):
            result=original(*args);now[0]+=6;return result
        with patch('time.monotonic',side_effect=lambda:now[0]),patch.object(self.repo,'put_result',side_effect=slow_publication):
            p=self.ensure()
            for _ in range(60):
                if p['state']=='ready':break
                p=self.call('duplicate_step',dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=p['checkpoint'],restart=False))
            self.assertEqual(p['state'],'ready')
            self.assertFalse(self.ops.cache.pending)
            self.assertFalse(self.ops.cache.entries)

    def test_original_session_can_restart_expired_lease_with_or_without_local_state(self):
        for release in (False,True):
            with self.subTest(release=release):
                p=self.ensure()
                self.repo.scans[p['scanId']]['lease_until']='2026-10-01T12:00:00Z'
                if release:self.ops.registry.release(p['scanId'])
                progress=self.call('duplicate_status',dict(scan_id=p['scanId']))
                self.assertEqual(progress['state'],'restart_required')
                restarted=self.call('duplicate_step',dict(scan_id=p['scanId'],generation=p['generation'],expected_checkpoint=p['checkpoint'],restart=True))
                self.assertNotEqual(restarted['generation'],p['generation'])

    def test_restored_unfinished_source_is_restartable_with_new_generation(self):
        first=self.ensure()
        job,step=self.h.upload(export([{'Invoice #':'NEW1234'}]));self.h.finish(job,step)
        self.ensure()
        self.h.repo.active_id=first['importId'];self.h.repo.version+=1
        restored=self.ensure()
        self.assertEqual(restored['state'],'restart_required')
        restarted=self.call('duplicate_step',dict(scan_id=restored['scanId'],generation=restored['generation'],expected_checkpoint=restored['checkpoint'],restart=True))
        self.assertNotEqual(restarted['generation'],first['generation'])
        self.assertEqual(self.complete(restarted)['state'],'ready')
