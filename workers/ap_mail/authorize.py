"""Owner-run desktop OAuth: loopback + PKCE/state, no token files or token output."""
import argparse
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import logging
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs,urlencode,urlsplit
import webbrowser
import httpx
from app.ap_mail.contracts import MailError,canonical

SCOPES=('openid','email','https://www.googleapis.com/auth/gmail.readonly')
AUTH_URI='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URI='https://oauth2.googleapis.com/token'

def validate_callback(path,expected_state):
    try:
        parsed=urlsplit(path);query=parse_qs(parsed.query,strict_parsing=True)
        if parsed.path!='/oauth2/callback' or 'error' in query or len(query.get('state',[]))!=1 or len(query.get('code',[]))!=1:raise ValueError
        if not hmac.compare_digest(query['state'][0],expected_state):raise ValueError
        if not 1<=len(query['code'][0])<=4096:raise ValueError
        return query['code'][0]
    except Exception:raise MailError('auth') from None

def accept_grant(token,identity,expected_email,nonce):
    if (not token.get('refresh_token') or not token.get('access_token') or identity.get('email_verified') is not True or
        identity.get('email','').casefold()!=expected_email.casefold() or not identity.get('sub') or
        not hmac.compare_digest(str(identity.get('nonce','')),nonce)):raise MailError('wrong_account')
    scopes=set(str(token.get('scope','')).split())
    if 'https://www.googleapis.com/auth/userinfo.email' in scopes:scopes.discard('https://www.googleapis.com/auth/userinfo.email');scopes.add('email')
    if scopes!=set(SCOPES):raise MailError('auth')
    return identity

def persist_grant(store,secret_name,token,client,identity,label):
    payload=canonical(dict(refresh_token=token['refresh_token'],client_id=client['client_id'],client_secret=client['client_secret'],
        token_uri=TOKEN_URI,account_id=identity['sub'],email=identity['email'],label_id=label['id'],scopes=SCOPES)).encode()
    try:version=store.add(secret_name,payload)
    except Exception:raise MailError('storage') from None
    return dict(account_id=identity['sub'],email=identity['email'],label_id=label['id'],label_name=label['name'],secret_version=version)

def authorize(client_path,expected_email,label_name,secret_name):
    from .http import verify_google_token
    from .runtime import BoundedTransport,SecretStore
    from app.ap_mail.gmail import GmailClient
    logging.disable(logging.CRITICAL)
    try:
        path=Path(client_path)
        if path.stat().st_size>16384:raise MailError('invalid')
        client=json.loads(path.read_text(encoding='utf-8'))['installed']
        if client.get('auth_uri')!='https://accounts.google.com/o/oauth2/auth' or client.get('token_uri')!=TOKEN_URI:raise MailError('invalid')
        state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode();received={}
        class Callback(BaseHTTPRequestHandler):
            def log_message(self,*args):pass # A callback URL includes an authorization code.
            def do_GET(self):
                try:
                    if self.headers.get('Host')!='127.0.0.1:'+str(self.server.server_port):raise MailError('auth')
                    code=validate_callback(self.path,state);received['code']=code;status=200
                except Exception:received['error']=True;status=400
                body=b'Authorization received. Return to the setup terminal.' if status==200 else b'Authorization was rejected. Return to the setup terminal.'
                self.send_response(status);self.send_header('Content-Type','text/plain');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        with HTTPServer(('127.0.0.1',0),Callback) as server:
            server.timeout=1;redirect='http://127.0.0.1:'+str(server.server_port)+'/oauth2/callback'
            url=AUTH_URI+'?'+urlencode(dict(client_id=client['client_id'],redirect_uri=redirect,response_type='code',scope=' '.join(SCOPES),
                access_type='offline',prompt='consent',state=state,nonce=nonce,code_challenge=challenge,code_challenge_method='S256',login_hint=expected_email))
            if not webbrowser.open(url):raise MailError('unavailable')
            deadline=time.monotonic()+180
            while not received and time.monotonic()<deadline:server.handle_request()
        if received.get('error') or not received.get('code'):raise MailError('auth')
        # No redirects or diagnostics from the token endpoint are followed/printed.
        with httpx.Client(timeout=20,follow_redirects=False,trust_env=False) as http:
            with http.stream('POST',TOKEN_URI,data=dict(code=received['code'],client_id=client['client_id'],client_secret=client['client_secret'],
                    redirect_uri=redirect,grant_type='authorization_code',code_verifier=verifier)) as response:
                if response.status_code!=200:raise MailError('auth')
                raw=bytearray()
                for chunk in response.iter_bytes(4096):
                    if len(raw)+len(chunk)>16384:raise MailError('auth')
                    raw.extend(chunk)
                token=json.loads(raw)
        identity=verify_google_token(token.get('id_token',''),client['client_id']);accept_grant(token,identity,expected_email,nonce)
        transport=BoundedTransport();reply=transport.request('GET','https://gmail.googleapis.com/gmail/v1/users/me/labels',
            headers={'Authorization':'Bearer '+token['access_token']},params={},timeout=20,max_bytes=2*1024*1024)
        if reply.status_code!=200:raise MailError('auth')
        labels=[item for item in reply.json().get('labels',[]) if item.get('name')==label_name]
        if len(labels)!=1:raise MailError('label_missing')
        label=labels[0];gmail=GmailClient(transport,lambda:token['access_token'],identity['sub'],identity['email'],label['id'])
        gmail.profile();gmail.labels()
        return persist_grant(SecretStore(),secret_name,token,client,identity,label)
    except MailError:raise
    except Exception:raise MailError('auth') from None

def main():
    parser=argparse.ArgumentParser(description='Authorize the selected Gmail account without saving tokens to disk.')
    parser.add_argument('--client-json',required=True);parser.add_argument('--expected-email',required=True)
    parser.add_argument('--label',default='AP Statements');parser.add_argument('--secret',required=True)
    args=parser.parse_args()
    try:print(json.dumps(authorize(args.client_json,args.expected_email,args.label,args.secret)))
    except MailError as error:raise SystemExit('Gmail setup did not finish: '+error.code+'. No token was printed.') from None
if __name__=='__main__':main()
