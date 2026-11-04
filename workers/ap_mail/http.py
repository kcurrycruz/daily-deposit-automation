"""IAM-only WSGI surface. Headers claiming to be Cloud Tasks confer no authority."""
import json
import time
from app.ap_mail.contracts import identifier,natural

class Application:
    def __init__(self,role,audience,caller,verify,clock,handlers):
        if role not in ('checker','processor'):raise ValueError('Invalid runtime role.')
        self.role,self.audience,self.caller,self.verify,self.clock,self.handlers=role,audience,caller,verify,clock,handlers
    def handle(self,method,path,headers,body):
        endpoints={'checker':{'/poll','/dispatch-reconcile'},'processor':{'/process'}}
        if path not in endpoints[self.role] or method!='POST':return 404,{'code':'not_found'}
        if not isinstance(body,bytes) or len(body)>4096:return 400,{'code':'invalid'}
        try:
            header=next((value for key,value in headers.items() if key.lower()=='authorization'),'')
            if not isinstance(header,str) or not header.startswith('Bearer ') or not 1<=len(header[7:])<=8192:raise ValueError
            claims=self.verify(header[7:],self.audience)
            if (claims.get('iss') not in ('accounts.google.com','https://accounts.google.com') or claims.get('aud')!=self.audience or
                claims.get('email')!=self.caller or claims.get('email_verified') is not True or not claims.get('sub') or
                not isinstance(claims.get('exp'),(int,float)) or claims['exp']<=self.clock()):raise ValueError
        except Exception:return 403,{'code':'denied'}
        try:
            def unique(pairs):
                value={}
                for key,item in pairs:
                    if key in value:raise ValueError
                    value[key]=item
                return value
            value=json.loads(body,object_pairs_hook=unique)
            if not isinstance(value,dict):raise ValueError
            if path=='/process':
                if set(value)!=set(('job_id','dispatch_generation')):raise ValueError
                identifier(value['job_id']);natural(value['dispatch_generation'],1)
            elif value!={}:raise ValueError
        except Exception:return 400,{'code':'invalid'}
        try:
            result=self.handlers[path[1:]](value)
            safe={key:result[key] for key in ('status','retry','code','queued','discovered','attention','sent','failed','recovered') if key in result}
            return (503 if safe.get('retry') else 200),safe
        except Exception:return 503,{'code':'unavailable'}
    def __call__(self,environ,start_response):
        try:
            size=int(environ.get('CONTENT_LENGTH','-1'))
            if not 0<=size<=4096 or environ.get('QUERY_STRING'):code,result=400,{'code':'invalid'}
            else:
                body=environ['wsgi.input'].read(size)
                if len(body)!=size:code,result=400,{'code':'invalid'}
                else:code,result=self.handle(environ.get('REQUEST_METHOD'),environ.get('PATH_INFO'),{'Authorization':environ.get('HTTP_AUTHORIZATION','')},body)
        except Exception:code,result=400,{'code':'invalid'}
        raw=json.dumps(result,separators=(',',':')).encode()
        start_response(str(code)+' '+{200:'OK',400:'Bad Request',403:'Forbidden',404:'Not Found',503:'Service Unavailable'}[code],
            [('Content-Type','application/json'),('Content-Length',str(len(raw))),('Cache-Control','no-store')])
        return [raw]

def verify_google_token(token,audience):
    from google.oauth2.id_token import verify_oauth2_token
    from google.auth.transport.requests import Request
    request=Request()
    return verify_oauth2_token(token,lambda *args,**kwargs:request(*args,**{**kwargs,'timeout':10}),audience=audience)

def create_app():
    try:
        from .runtime import Runtime
        runtime=Runtime.from_environment()
        return Application(runtime.config.role,runtime.audience,runtime.caller,verify_google_token,time.time,
            {'poll':runtime.poll,'dispatch-reconcile':runtime.reconcile,'process':runtime.process})
    except Exception:raise SystemExit('AP mail runtime configuration is unavailable.') from None
