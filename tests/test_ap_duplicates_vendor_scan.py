import json
import unittest
from datetime import date,timedelta
from fixtures.ap_shared.duplicate_cases import bill,changed
import test_ap_duplicates_scan as scan_tests


def history(vendor='Synthetic Foods',prefix='INV',width=6,day='2026-08-15',count=24):
    return [bill(f'{prefix}{1000+i:0{width}d}',amount=1000+i,vendor=vendor,invoice_date=day) for i in range(count)]


class VendorScanTests(unittest.TestCase):
    scan=scan_tests.DuplicateScanTests.scan
    def test_oversized_generated_evidence_fails_before_result_is_publishable(self):
        from app.ap_shared.bills.duplicates.contracts import DuplicateError
        rows=[]
        for prefix in ['#'*900,'#'*899+'A','#'*899+'B']:
            rows+=history(prefix=prefix,count=8)
        rows+=[bill('#'*900+'451234',amount=88888),bill('#'*900+'45124',amount=88888)]
        with self.assertRaises(DuplicateError) as error:self.scan(rows)
        self.assertEqual(error.exception.code,'duplicate_limit')

    def findings(self,rows,probes=10000):
        db,_,_,_=self.scan(rows,probes)
        return db,[(kind,json.loads(value)) for kind,value in db.execute('select classification,evidence from findings order by id')]

    def test_missing_digit_adds_profile_supported_entry_issue(self):
        rows=history()+[bill('INV451234',amount=88888),bill('INV45124',amount=88888)]
        db,findings=self.findings(rows)
        self.assertEqual([k for k,_ in findings],['reference_entry_issue'])
        evidence=findings[0][1]
        self.assertEqual(evidence['edit'],'one_character_added_or_missing')
        self.assertEqual({p['invoiceNumber']:p['matches'] for p in evidence['profiles']},{'INV451234':True,'INV45124':False})
        self.assertTrue(all(p['distinctReferences']==24 for p in evidence['profiles']))
        self.assertEqual(db.execute('select count(*) from members').fetchone()[0],2)

    def test_cross_vendor_counterpart_includes_both_search_names(self):
        rows=history(vendor='Synthetic Paper',prefix='PAP')+history(vendor='Synthetic Produce',prefix='FOOD',width=7)
        rows+=[bill('PAP451234',vendor='Synthetic Paper',amount=88888),bill('PAP451234',vendor='Synthetic Produce',amount=88888)]
        db,findings=self.findings(rows,probes=1)
        self.assertEqual([k for k,_ in findings],['possible_wrong_vendor'])
        self.assertEqual({p['vendor'] for p in findings[0][1]['profiles']},{'Synthetic Paper','Synthetic Produce'})
        search=db.execute('select search from findings').fetchone()[0]
        self.assertIn('synthetic paper',search);self.assertIn('synthetic produce',search)

    def test_generic_shared_formats_and_same_day_sequences_add_no_warning(self):
        rows=history(vendor='A',prefix='')+history(vendor='B',prefix='')
        rows+=[bill('451234',vendor='A',amount=88888),bill('451235',vendor='A',amount=88888),bill('451234',vendor='B',amount=88888)]
        _,findings=self.findings(rows)
        self.assertEqual(findings,[])

    def test_candidate_month_history_is_not_training_even_across_month_boundary(self):
        rows=history(day='2026-09-10')+[bill('INV451234',amount=88888,invoice_date='2026-09-30'),bill('INV45124',amount=88888,invoice_date='2026-10-01')]
        _,findings=self.findings(rows);self.assertEqual(findings,[])
        rows=history(day='2026-08-15')+rows[-2:]
        _,findings=self.findings(rows);self.assertEqual(len(findings),1)
        self.assertTrue(all(p['periodEnd']=='2026-08-31' for p in findings[0][1]['profiles']))

    def test_new_rules_obey_date_currency_and_source_ambiguity(self):
        base=history()+[bill('INV451234',amount=88888),bill('INV45124',amount=88888)]
        for changes in [dict(invoiceDate='2026-10-05'),dict(invoiceDate=''),dict(currency='EUR'),dict(sourceIssues='Incomplete source rows.')]:
            with self.subTest(changes=changes):
                rows=base[:-1]+[changed(base[-1],**changes)]
                _,findings=self.findings(rows);self.assertEqual(findings,[])
        _,findings=self.findings(base+[changed(base[-1],id='second-source')])
        self.assertNotIn('reference_entry_issue',[k for k,_ in findings])

    def test_different_day_routine_amounts_are_excluded(self):
        rows=history()+[bill(f'INV{990000+i}',amount=88888,invoice_date=(date(2026,9,15)+timedelta(days=i%6)).isoformat()) for i in range(10)]
        rows+=[bill('INV451234',amount=88888),bill('INV45124',amount=88888,invoice_date='2026-10-02')]
        _,findings=self.findings(rows)
        self.assertNotIn('reference_entry_issue',[k for k,_ in findings])

    def test_new_keys_and_profile_evidence_are_order_independent(self):
        rows=history()+[bill('INV451234',amount=88888),bill('INV45124',amount=88888)]
        first,_,_,_=self.scan(rows)
        second,_,_,_=self.scan(list(reversed([changed(r,reportedPaidAmount=0,sourceRows='999') for r in rows])))
        self.assertEqual(first.execute('select key from findings').fetchall(),second.execute('select key from findings').fetchall())
        a=json.loads(first.execute('select evidence from findings').fetchone()[0])
        b=json.loads(second.execute('select evidence from findings').fetchone()[0])
        self.assertEqual(sorted(a['profiles'],key=lambda p:p['matches']),sorted(b['profiles'],key=lambda p:p['matches']))

    def test_reused_reference_retains_amount_difference_and_date_context(self):
        rows=[bill('REUSED',amount=10000),bill('REUSED',amount=20000,invoice_date='2025-10-01')]
        _,findings=self.findings(rows)
        self.assertEqual(findings[0][0],'amount_difference')
        self.assertEqual(findings[0][1]['dateGapDays'],365)
        self.assertTrue(findings[0][1]['referenceReuse'])

    def test_large_historical_profile_resumes_under_small_probe_budget(self):
        rows=history(count=2000)+[bill('INV451234',amount=88888),bill('INV45124',amount=88888)]
        db,engine,summary,calls=self.scan(rows,probes=25)
        self.assertGreater(calls,100)
        self.assertEqual(summary['findingCount'],1)
        evidence=json.loads(db.execute('select evidence from findings').fetchone()[0])
        self.assertEqual(evidence['profiles'][0]['distinctReferences'],2000)
        self.assertTrue(engine.done)

if __name__=='__main__':unittest.main()
