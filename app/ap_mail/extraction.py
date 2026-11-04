"""Supervise the credential-free extractor and bound every IPC message/lifetime."""
import json
import os
from pathlib import Path
from queue import Queue, Empty
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from app.ap_shared.models import validate_statement
from .contracts import MailError, MAX_FILE_BYTES, bounded_text

OUTPUT_BYTES = 1024*1024
ENV_KEYS = frozenset(('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL',
                      'NODE_PATH','PLAYWRIGHT_BROWSERS_PATH','AP_MAIL_BROWSER_BINARY'))


def _terminate(process):
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
    else:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run_child(command, request, *, timeout_seconds=600, heartbeat):
    if not 0<timeout_seconds<=600:raise MailError('invalid')
    environment={key:value for key,value in os.environ.items() if key.upper() in ENV_KEYS}
    events=Queue(maxsize=8)
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        env=environment,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0,
        start_new_session=os.name!='nt')
    stop=threading.Event()

    def receive():
        try:
            for _ in range(10001):
                line=process.stdout.readline(OUTPUT_BYTES+1)
                if not line:break
                if len(line)>OUTPUT_BYTES:
                    value=MailError('limit')
                else:
                    try:value=json.loads(line)
                    except (ValueError,TypeError):value=MailError('unreadable')
                while not stop.is_set():
                    try:events.put(value,timeout=.1);break
                    except Exception:continue
                if isinstance(value,MailError):break
            else:events.put(MailError('limit'),timeout=.1)
        except Exception:
            if not stop.is_set():
                try:events.put(MailError('unreadable'),timeout=.1)
                except Exception:pass
        finally:
            if not stop.is_set():
                try:events.put(None,timeout=.1)
                except Exception:pass

    reader=threading.Thread(target=receive,daemon=True)
    reader.start();deadline=time.monotonic()+timeout_seconds;result=None
    try:
        process.stdin.write(json.dumps(request,allow_nan=False).encode('utf-8'));process.stdin.close()
        next_heartbeat=0
        while True:
            now=time.monotonic()
            if now>=deadline:raise MailError('limit')
            if now>=next_heartbeat:
                if not heartbeat():raise MailError('stale_claim')
                next_heartbeat=now+15
            try:value=events.get(timeout=min(.1,max(.001,deadline-now)))
            except Empty:continue
            if isinstance(value,MailError):raise value
            if value is None:break
            if type(value) is not dict:raise MailError('unreadable')
            if value.get('type')=='error':raise MailError(value.get('code') if value.get('code') in ('limit','unreadable','not_configured') else 'unreadable')
            if value.get('type')=='result':
                if result is not None:raise MailError('unreadable')
                result=value.get('doc')
            elif value.get('type')!='progress':raise MailError('unreadable')
        try:code=process.wait(timeout=max(.01,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:raise MailError('limit') from None
        if code or type(result) is not dict or result.get('confirmed') is not False or not result.get('rows'):raise MailError('unreadable')
        try:return validate_statement(result)
        except (ValueError,TypeError,KeyError):raise MailError('unreadable') from None
    finally:
        stop.set();_terminate(process)
        process.stdout.close();reader.join(timeout=1)


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
