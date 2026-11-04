import unittest

class BurstTests(unittest.TestCase):
    def test_hundred_pdf_burst_no_loss_and_crash_boundaries(self):
        from fixtures.ap_mail.burst_check import run_burst
        report=run_burst()
        self.assertEqual(report['receipts'],100)
        self.assertEqual(report['statements'],101) # one pre-existing completed human statement
        self.assertEqual(report['awaiting_review'],100)
        self.assertEqual(report['completion_events'],1)
        self.assertTrue(report['human_unchanged'])
        self.assertEqual(report['running'],0)
        self.assertLessEqual(report['max_attempts'],3)
        self.assertEqual(report['ocr_calls'],100)
        self.assertEqual(report['objects'],100)
        self.assertEqual(report['lost_publish_ack'],1)
        self.assertEqual(report['preliminary_found'],200)
        self.assertEqual(report['bill_source_table_reads'],1)
        self.assertGreaterEqual(report['recovered'],2)
