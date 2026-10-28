import json
import unittest
from copy import deepcopy
from uuid import uuid4
from fixtures.ap_shared.duplicate_cases import PIN


class VendorEvidenceContractTests(unittest.TestCase):
    def test_finding_evidence_is_bound_to_complete_pair_and_prior_month(self):
        from app.ap_shared.bills.duplicates.contracts import validate_finding_evidence
        previews=[dict(ordinal=n,vendor='Synthetic',invoiceNumber=ref,amount=10000,invoiceDate=day,currency='USD')
                  for n,ref,day in [(24,'INV451234','2026-10-01'),(25,'INV45124','2026-10-02')]]
        evidence=self.evidence();evidence['dateGapDays']=1
        self.assertEqual(validate_finding_evidence(evidence,'reference_entry_issue',previews,2,[24,25]),evidence)
        alterations=[lambda e,p:e['profiles'][0].update(vendor='Unrelated'),
                     lambda e,p:[v.update(periodStart='2026-10-01',periodEnd='2027-09-30') for v in e['profiles']],
                     lambda e,p:e.update(dateGapDays=0),lambda e,p:p[0].update(invoiceNumber='INV999999'),
                     lambda e,p:p[0].update(amount=20000),lambda e,p:p[0].update(currency='EUR')]
        for alter in alterations:
            e,p=deepcopy(evidence),deepcopy(previews);alter(e,p)
            with self.subTest(e=e,p=p),self.assertRaises(ValueError):validate_finding_evidence(e,'reference_entry_issue',p,2,[24,25])
        for count,members in [(3,[24,25,26]),(2,[24,26])]:
            with self.assertRaises(ValueError):validate_finding_evidence(evidence,'reference_entry_issue',previews,count,members)

    def evidence(self):
        profile=dict(periodStart='2025-10-01',periodEnd='2026-09-30',distinctReferences=24,
                     shapes=[dict(shape='INV######',references=24)],established=True,vendor='Synthetic',invoiceNumber='INV451234',matches=True)
        other={**deepcopy(profile),'invoiceNumber':'INV45124','matches':False}
        return dict(version=1,dateGapDays=0,referenceReuse=False,profiles=[profile,other],edit='one_character_added_or_missing')

    def test_evidence_round_trip_rejects_forged_support_and_fit(self):
        from app.ap_shared.bills.duplicates.contracts import validate_evidence
        evidence=self.evidence();self.assertEqual(validate_evidence(evidence,'reference_entry_issue'),evidence)
        for alter in [lambda e:e.update(version=2),lambda e:e.update(dateGapDays=4),
                      lambda e:e['profiles'][0].update(matches=False),
                      lambda e:e['profiles'][0].update(distinctReferences=19),
                      lambda e:e['profiles'][0].update(periodEnd='2026-09-29'),
                      lambda e:e['profiles'][0]['shapes'][0].update(references=2)]:
            candidate=deepcopy(evidence);alter(candidate)
            with self.subTest(candidate=candidate),self.assertRaises(ValueError):validate_evidence(candidate,'reference_entry_issue')

    def test_v3_manifest_uses_v2_format_and_owned_versioned_namespace(self):
        from app.ap_shared.bills.duplicates.contracts import RULE_VERSION,ARTIFACT_FORMAT,STORAGE_VERSION,validate_manifest
        self.assertEqual((RULE_VERSION,ARTIFACT_FORMAT,STORAGE_VERSION),('bill-duplicates-v3','bill-duplicates-v2','v2'))
        manifest=dict(format=ARTIFACT_FORMAT,ruleVersion=RULE_VERSION,sourceDigest='a'*64,importId=PIN['importId'],
                      key=f'{PIN["importId"]}/bill-duplicates/{STORAGE_VERSION}/{PIN["importId"]}/{RULE_VERSION}/'+ 'b'*64+'.sqlite.gz',
                      hash='b'*64,bytes=50,expandedHash='c'*64,expandedBytes=4096,findingCount=1,recordCount=2)
        self.assertEqual(validate_manifest(manifest),manifest)
        for change in [dict(format='bill-duplicates-v1'),dict(ruleVersion='bill-duplicates-v2'),
                       dict(key=manifest['key'].replace('/v2/','/v1/'))]:
            with self.assertRaises(ValueError):validate_manifest({**manifest,**change})

    def test_empty_evidence_is_only_valid_for_existing_classes(self):
        from app.ap_shared.bills.duplicates.contracts import validate_evidence
        empty=dict(version=1,dateGapDays=365,referenceReuse=True,profiles=[])
        self.assertEqual(validate_evidence(empty,'amount_difference'),empty)
        for kind in ('reference_entry_issue','possible_wrong_vendor','invented'):
            with self.assertRaises(ValueError):validate_evidence(empty,kind)
