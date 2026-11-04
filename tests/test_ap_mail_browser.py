import os
from pathlib import Path
import shutil
import subprocess
import unittest

class MailBrowserTests(unittest.TestCase):
    def test_polling_preserves_real_dom_pdf_focus_scroll_and_history_form(self):
        root=Path(__file__).resolve().parents[1];env=dict(os.environ)
        if os.name=='nt':env.setdefault('AP_MAIL_BROWSER_BINARY','C:/Program Files/Google/Chrome/Application/chrome.exe')
        result=subprocess.run([shutil.which('node'),str(root/'tests/fixtures/ap_mail/ui.browser.mjs')],cwd=root,env=env,
            capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Mail browser DOM checks passed',result.stdout)
