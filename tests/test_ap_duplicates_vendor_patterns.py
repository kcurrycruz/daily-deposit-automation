import json
import sqlite3
import unittest
from datetime import date, timedelta


class VendorPatternTests(unittest.TestCase):
    def store(self, rows):
        from app.ap_shared.bills.duplicates.vendor_patterns import VendorPatterns
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        db.execute('create table nodes(ordinal integer primary key,vendor text,ref text,shape text,day integer,amount integer,warning integer,n integer)')
        db.executemany('insert into nodes values(?,?,?,?,?,?,?,?)',[(i,*r) for i,r in enumerate(rows)])
        return VendorPatterns(db)

    def history(self,n=20,day='2026-09-15',vendor='a',prefix='INV',amount=100):
        return [(vendor,f'{prefix}{i:05d}',prefix+'#####',date.fromisoformat(day).toordinal(),amount,0,1) for i in range(n)]

    def profile(self, patterns,vendor='a',month='2026-10-01'):
        for _ in range(100):
            result=patterns.advance(vendor,date.fromisoformat(month).toordinal())
            if result is not None:return result
        self.fail('profile never completed')

    def test_profile_requires_twenty_distinct_historical_references(self):
        for count,established in [(19,False),(20,True)]:
            p=self.profile(self.store(self.history(count)))
            self.assertEqual(p['established'],established)
            self.assertEqual(p['distinctReferences'],count)
            self.assertEqual(p['periodEnd'],'2026-09-30')

    def test_secondary_formats_and_coverage_ties_are_deterministic(self):
        rows=self.history(90)+self.history(5,prefix='CR')+self.history(5,prefix='ALT')
        p=self.profile(self.store(rows))
        self.assertEqual(p['shapes'],[{'shape':'INV#####','references':90},{'shape':'ALT#####','references':5},{'shape':'CR#####','references':5}])
        self.assertTrue(p['established'])
        split=[]
        for prefix in 'ABCDE':split+=self.history(5,prefix=prefix)
        self.assertFalse(self.profile(self.store(split))['established'])

    def test_training_excludes_candidate_month_future_and_old_rows(self):
        rows=self.history()+self.history(50,day='2026-10-01',prefix='NEW')+self.history(50,day='2027-01-01',prefix='FUTURE')+self.history(50,day='2025-09-30',prefix='OLD')
        p=self.profile(self.store(rows));self.assertEqual(p['distinctReferences'],20)
        self.assertEqual(p['shapes'],[{'shape':'INV#####','references':20}])
        self.assertEqual(p['periodStart'],'2025-10-01')

    def test_duplicate_refs_and_ambiguous_identities_do_not_inflate_support(self):
        rows=self.history(19)+self.history(19,day='2026-09-16')
        rows+=[('a','BAD00001','BAD#####',date(2026,9,1).toordinal(),100,1,1),('a','BAD00002','BAD#####',date(2026,9,1).toordinal(),100,0,2)]
        p=self.profile(self.store(rows));self.assertEqual(p['distinctReferences'],19);self.assertFalse(p['established'])

    def test_preparation_is_batched_cached_and_year_boundary_is_correct(self):
        patterns=self.store(self.history(700,day='2026-12-15'))
        cutoff=date(2027,1,1).toordinal()
        self.assertIsNone(patterns.advance('a',cutoff))
        p=self.profile(patterns,month='2027-01-01')
        self.assertEqual(p['distinctReferences'],700)
        self.assertEqual(p['periodStart'],'2026-01-01')
        self.assertEqual(patterns.advance('a',cutoff),p)

    def test_earliest_valid_invoice_month_has_no_prior_profile(self):
        p=self.profile(self.store([]),month='0001-01-01')
        self.assertFalse(p['established'])
        self.assertEqual(p['distinctReferences'],0)

    def test_recurrence_requires_both_thresholds_and_excludes_candidate_day(self):
        day=date(2026,10,1).toordinal()
        rows=[('a',f'R{i:04d}','R####',day-1-i%6,100,0,1) for i in range(10)]
        patterns=self.store(rows+self.history(50,day='2026-10-01'))
        self.assertTrue(patterns.recurrence('a',100,day))
        self.assertFalse(self.store(rows[:9]).recurrence('a',100,day))
        same_days=[tuple([*r[:3],day-1,*r[4:]]) for r in rows]
        self.assertFalse(self.store(same_days).recurrence('a',100,day))

    def test_reference_edits_include_missing_character_without_routine_sequence_expansion(self):
        from app.ap_shared.bills.duplicates.vendor_patterns import reference_shape,compact_reference,edit_kind,reference_variants
        self.assertEqual(reference_shape(' inv 001-A '),'INV ###-A')
        self.assertEqual(compact_reference(' inv 001-A '),'INV001A')
        self.assertEqual(edit_kind('123456','12356'),'one_character_added_or_missing')
        self.assertEqual(edit_kind('123456','123465'),'adjacent_characters_swapped')
        self.assertIsNone(edit_kind('123456','129956'))
        variants=list(reference_variants('INV1234',['INV#####']))
        self.assertIn('INV12345',variants)
        self.assertIn('INV01234',variants)
        self.assertNotIn('OTHER1234',variants)

if __name__=='__main__':unittest.main()
