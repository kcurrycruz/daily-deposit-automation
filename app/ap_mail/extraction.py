"""Supervise the credential-free extractor and bound every IPC message/lifetime."""
import os
from pathlib import Path
import shutil
import tempfile

from app.ap_shared.models import validate_statement
from .contracts import MailError, MAX_FILE_BYTES, bounded_text
from .process import run_json


def run_child(command, request, *, timeout_seconds=600, heartbeat):
    result=run_json(command,request,timeout_seconds=timeout_seconds,heartbeat=heartbeat)
    if type(result) is not dict or result.get('confirmed') is not False or not result.get('rows'):raise MailError('unreadable')
    try:return validate_statement(result)
    except (ValueError,TypeError,KeyError):raise MailError('unreadable') from None


def extract_private_pdf(path, filename, *, timeout_seconds=600, heartbeat):
    path=Path(path)
    bounded_text(filename,1024)
    if path.is_symlink() or not path.is_file() or not 1<=path.stat().st_size<=MAX_FILE_BYTES:raise MailError('limit')
    with path.open('rb') as stream:
        if stream.read(5)!=b'%PDF-':raise MailError('unreadable')
    node=shutil.which('node')
    if not node:raise MailError('not_configured')
    browser=Path(__file__).resolve().parents[2]/'workers/ap_mail/browser.mjs'
    with tempfile.TemporaryDirectory(prefix='ap-mail-scan-') as folder:
        os.chmod(folder,0o700)
        original=Path(folder)/'input.pdf';shutil.copyfile(path,original)
        os.chmod(original,0o600)
        return run_child([node,str(browser)],dict(path=str(original),filename=filename),
                         timeout_seconds=timeout_seconds,heartbeat=heartbeat)
