import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
import shutil
from unittest.mock import patch
from app.ap_mail.contracts import MailError

DOC=dict(id='00000000-0000-4000-8000-000000000003',vendor='Synthetic',filename='s.pdf',
         confirmed=False,pageCount=1,warnings=[],rows=[dict(id='00000000-0000-4000-8000-000000000004',
         invoiceNumber='00042',type='invoice',amount=13800,page=1,confidence=99)])


class ExtractionTests(unittest.TestCase):
    def test_private_pdf_uses_real_browser_ipc(self):
        from app.ap_mail.extraction import extract_private_pdf
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([shutil.which('node'),'--input-type=module','-e',
            "import {textPdf} from './tests/fixtures/ap_mail/pdfs.mjs';process.stdout.write(textPdf());"],
            cwd=root,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0)
        with tempfile.TemporaryDirectory() as folder:
            original=Path(folder)/'original.pdf';original.write_bytes(result.stdout)
            extra={'AP_MAIL_BROWSER_BINARY':'C:/Program Files/Google/Chrome/Application/chrome.exe'} if os.name=='nt' else {}
            with patch.dict(os.environ,**extra):
                doc=extract_private_pdf(original,'synthetic.pdf',heartbeat=lambda:True)
            self.assertFalse(doc['confirmed'])
            self.assertEqual([(r['invoiceNumber'],r['amount']) for r in doc['rows']],[('00042',10000),('00043',20000)])

    def test_extractor_parity_digital_scan_dotmatrix_credit(self):
        root=Path(__file__).resolve().parents[1]
        env=dict(os.environ)
        if os.name=='nt' and not env.get('AP_MAIL_BROWSER_BINARY'):
            env['AP_MAIL_BROWSER_BINARY']='C:/Program Files/Google/Chrome/Application/chrome.exe'
        result=subprocess.run([shutil.which('node'),str(root/'tests/fixtures/ap_mail/extraction_check.mjs')],
                              cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Synthetic browser extraction checks passed',result.stdout)

    def test_no_external_requests_or_secrets_in_child_environment(self):
        from app.ap_mail.extraction import run_child
        with tempfile.TemporaryDirectory() as folder:
            child=Path(folder)/'child.py'
            child.write_text("import os,json,sys\nr=json.load(sys.stdin)\nassert 'AP_TEST_SECRET' not in os.environ\n"
                +"print(json.dumps({'type':'result','doc':"+repr(DOC)+"}))\n",encoding='utf-8')
            with patch.dict(os.environ,AP_TEST_SECRET='TEST-SECRET'):
                doc=run_child([sys.executable,str(child)],{},timeout_seconds=5,heartbeat=lambda:True)
            self.assertEqual(doc['rows'][0]['amount'],13800)

    def test_timeout_and_heartbeat_loss_terminate_owned_child(self):
        from app.ap_mail.extraction import run_child
        with tempfile.TemporaryDirectory() as folder:
            child=Path(folder)/'waiting.py';child.write_text('import time\ntime.sleep(30)\n',encoding='utf-8')
            with self.assertRaises(MailError):run_child([sys.executable,str(child)],{},timeout_seconds=0.2,heartbeat=lambda:True)
            with self.assertRaises(MailError) as error:run_child([sys.executable,str(child)],{},timeout_seconds=5,heartbeat=lambda:False)
            self.assertEqual(error.exception.code,'stale_claim')

    def test_child_output_is_bounded_and_zero_rows_not_success(self):
        from app.ap_mail.extraction import run_child
        with tempfile.TemporaryDirectory() as folder:
            child=Path(folder)/'bad.py'
            for source in ["print('x'*2000000)","print("+repr(json.dumps({'type':'result','doc':{**DOC,'rows':[]}}))+")"]:
                child.write_text(source,encoding='utf-8')
                with self.assertRaises(MailError):run_child([sys.executable,str(child)],{},timeout_seconds=5,heartbeat=lambda:True)

    def test_twenty_mib_and_pdf_signature_checked_before_spawn(self):
        from app.ap_mail.extraction import extract_private_pdf
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.pdf';path.write_bytes(b'not a PDF')
            with self.assertRaises(MailError):extract_private_pdf(path,'input.pdf',heartbeat=lambda:True)
            with path.open('wb') as stream:stream.truncate(20*1024*1024+1)
            with self.assertRaises(MailError):extract_private_pdf(path,'input.pdf',heartbeat=lambda:True)

    def test_malformed_child_document_and_runtime_failure_are_distinct(self):
        from app.ap_mail.extraction import run_child
        with tempfile.TemporaryDirectory() as folder:
            child=Path(folder)/'response.py'
            child.write_text("print("+repr(json.dumps({'type':'result','doc':[]}))+")",encoding='utf-8')
            with self.assertRaises(MailError):run_child([sys.executable,str(child)],{},timeout_seconds=5,heartbeat=lambda:True)
            child.write_text("print("+repr(json.dumps({'type':'error','code':'not_configured'}))+")",encoding='utf-8')
            with self.assertRaises(MailError) as error:run_child([sys.executable,str(child)],{},timeout_seconds=5,heartbeat=lambda:True)
            self.assertEqual(error.exception.code,'not_configured')
