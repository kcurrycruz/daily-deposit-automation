"""Bounded JSON IPC for trusted, credential-free parser/matching programs."""
import json
import os
from queue import Queue, Empty, Full
import signal
import subprocess
import threading
import time
from .contracts import MailError,CODES

OUTPUT_BYTES=1024*1024
ENV_KEYS=frozenset(('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL',
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


def run_json(command,request,*,timeout_seconds=600,heartbeat,on_request=None):
    if not 0<timeout_seconds<=600:raise MailError('invalid')
    if not heartbeat():raise MailError('stale_claim')
    environment={key:value for key,value in os.environ.items() if key.upper() in ENV_KEYS}
    events=Queue(maxsize=8);stop=threading.Event();finished=threading.Event()
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        env=environment,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0,start_new_session=os.name!='nt')

    def receive():
        total=0
        try:
            for _ in range(10000):
                line=process.stdout.readline(OUTPUT_BYTES+1)
                if not line:break
                total+=len(line)
                if len(line)>OUTPUT_BYTES or total>4*OUTPUT_BYTES:value=MailError('limit')
                else:
                    try:value=json.loads(line,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
                    except (ValueError,TypeError):value=MailError('unreadable')
                while not stop.is_set():
                    try:events.put(value,timeout=.1);break
                    except Full:continue
                if isinstance(value,MailError):break
            else:
                while not stop.is_set():
                    try:events.put(MailError('limit'),timeout=.1);break
                    except Full:continue
        except Exception:
            if not stop.is_set():
                try:events.put(MailError('unreadable'),timeout=.1)
                except Full:pass
        finally:finished.set()

    reader=threading.Thread(target=receive,daemon=True);reader.start()
    deadline=time.monotonic()+timeout_seconds;result=None;has_result=False;seen=set()
    try:
        initial=json.dumps(request,allow_nan=False).encode('utf-8')
        if len(initial)>OUTPUT_BYTES:raise MailError('limit')
        process.stdin.write(initial+(b'\n' if on_request else b''));process.stdin.flush()
        if not on_request:process.stdin.close()
        next_heartbeat=0
        while True:
            now=time.monotonic()
            if now>=deadline:raise MailError('limit')
            if now>=next_heartbeat:
                if not heartbeat():raise MailError('stale_claim')
                next_heartbeat=now+15
            try:value=events.get(timeout=min(.1,max(.001,deadline-now)))
            except Empty:
                if finished.is_set():break
                continue
            if isinstance(value,MailError):raise value
            if type(value) is not dict:raise MailError('unreadable')
            kind=value.get('type')
            if kind=='error':raise MailError(value.get('code') if value.get('code') in CODES else 'unreadable')
            if kind=='result':
                if has_result or ('doc' in value)==('value' in value):raise MailError('unreadable')
                has_result=True;result=value.get('doc') if 'doc' in value else value['value']
            elif kind=='read':
                ident=value.get('request_id')
                if not on_request or has_result or type(ident) is not int or ident<1 or ident in seen or type(value.get('payload')) is not dict:
                    raise MailError('denied')
                seen.add(ident)
                try:
                    data=on_request(value.get('action'),value['payload'])
                    if type(data) is not dict:raise MailError('unavailable')
                    reply=dict(type='reply',request_id=ident,ok=True,value=data)
                except Exception as error:
                    code=getattr(error,'code','denied' if isinstance(error,PermissionError) else 'unavailable')
                    if code not in CODES and code!='bill_range_loading':code='unavailable'
                    reply=dict(type='reply',request_id=ident,ok=False,error={'code':code})
                raw=json.dumps(reply,ensure_ascii=False,allow_nan=False).encode('utf-8')
                if len(raw)>OUTPUT_BYTES:raise MailError('limit')
                process.stdin.write(raw+b'\n');process.stdin.flush()
            elif kind!='progress':raise MailError('unreadable')
        try:code=process.wait(timeout=max(.01,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:raise MailError('limit') from None
        if code or not has_result:raise MailError('unreadable')
        return result
    finally:
        stop.set();_terminate(process)
        if not process.stdin.closed:
            try:process.stdin.close()
            except BrokenPipeError:pass
        process.stdout.close();reader.join(timeout=1)
