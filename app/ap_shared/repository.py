"""Supabase I/O only. Callers must authorize before financial operations."""
from datetime import datetime, timedelta, timezone
from functools import wraps
import base64
import hashlib
import json
import logging
import re
from urllib.parse import urlparse
from .models import (ApConfig, JsonObject, SharedSnapshot, require_uuid, integer,
                     validate_record, PAGE_SIZE, PREVIEW_SECONDS)
from .review_progress import review_progress

class ApStoreError(RuntimeError):
    def __init__(self, code='unavailable'):
        self.code=code
        super().__init__({'conflict':'Another save changed this record. Reload before saving again.',
                         'denied':'AP access or backend permissions are unavailable.',
                         'validation':'The shared operation could not be validated.',
                         'not_saved':'This work was not saved. Keep your edit and retry.'}.get(code,
                         'Shared AP storage is unavailable or incomplete. Retry without discarding your work.'))

def safe_backend(method):
    @wraps(method)
    def guarded(*args,**kwargs):
        try: return method(*args,**kwargs)
        except (ApStoreError,PermissionError): raise
        except Exception as error:
            message=getattr(error,'message','')
            code=getattr(error,'code','')
            mapped='conflict' if message in ('conflict','request_conflict','completed_revision','import_immutable') else (
                'denied' if code=='42501' or message=='upload_denied' else 'validation' if message in ('validation','review_required','initials_required','extraction_unconfirmed','original_required') else 'unavailable')
            raise ApStoreError(mapped) from None
    return guarded

def create_repository(config: ApConfig):
    from supabase import create_client
    from supabase.client import ClientOptions
    try:
        client=create_client(config.supabase_url,config.supabase_secret_key,ClientOptions(
            auto_refresh_token=False,persist_session=False,postgrest_client_timeout=10,storage_client_timeout=10))
        return ApRepository(client,config)
    except Exception:
        raise ApStoreError() from None

class _PrivateNetworkLogs(logging.Filter):
    def filter(self,record):return False

class ApRepository:
    def __init__(self,client,config: ApConfig):
        # SDK request diagnostics can contain financial filters or signed paths.
        for name in ('httpx','httpcore','supabase','postgrest','storage3'):
            logger=logging.getLogger(name)
            if not any(isinstance(f,_PrivateNetworkLogs) for f in logger.filters):logger.addFilter(_PrivateNetworkLogs())
        self.client=client
        self.config=config

    def _workspace(self,workspace_id):
        if workspace_id!=self.config.workspace_id: raise PermissionError('AP workspace access denied.')

    def _private_bucket(self):
        bucket=self.client.storage.get_bucket(self.config.bucket)
        public=bucket.get('public') if isinstance(bucket,dict) else getattr(bucket,'public',None)
        if public is not False: raise ApStoreError('denied')

    def _object_key(self,workspace_id,key):
        self._workspace(workspace_id)
        pattern=re.escape(workspace_id)+r'/(?:pdf/[0-9a-f]{64}\.pdf|csv/[0-9a-f]{64}\.csv|staging/[0-9a-f-]{36}/\d{1,3}-[0-9a-f]{64}\.bin|bills/v2/[0-9a-f]{64}/[0-9a-f]{64}\.(?:csv|sqlite)\.gz|bill-duplicates/(?:v1/[0-9a-f-]{36}/bill-duplicates-v[12]|v2/[0-9a-f-]{36}/bill-duplicates-v3)/[0-9a-f]{64}\.sqlite\.gz)'
        if type(key) is not str or not re.fullmatch(pattern,key): raise ApStoreError('validation')

    def _table(self,name,columns='*'):
        return self.client.table(name).select(columns).eq('workspace_id',self.config.workspace_id)

    def _one(self,query):
        rows=query.limit(1).execute().data
        if not isinstance(rows,list) or len(rows)!=1: raise ApStoreError()
        return rows[0]

    @safe_backend
    def import_info(self,workspace_id,import_id):
        self._workspace(workspace_id); self._private_bucket(); require_uuid(import_id)
        row=self._one(self._table('ap_bill_imports').eq('id',import_id))
        if row['id']!=import_id: raise ApStoreError()
        return row

    @safe_backend
    def bootstrap(self,workspace_id,cursor=None,limit=50) -> SharedSnapshot:
        self._workspace(workspace_id); self._private_bucket(); integer(limit,minimum=1,maximum=50)
        home=self._one(self.client.table('ap_workspaces').select('*').eq('id',workspace_id))
        source=self.import_info(workspace_id,home['active_import_id']) if home['active_import_id'] else None
        active={key:source[key] for key in ('id','metadata','record_count','created_at')} if source else None
        if active is not None:
            active['storage_format']=source.get('storage_format','rows-v1')
            if source.get('storage_format')=='snapshot-v2':
                active['vendorDigest']=source['snapshot_manifest']['vendorDigest']
        query=self._table('ap_statements').eq('archived',False).eq('completed',False).order('id').limit(limit)
        if cursor: query=query.gt('id',require_uuid(cursor))
        items=query.execute().data
        statements=[]
        for item in items:
            revision=self._one(self._table('ap_statement_revisions').eq('id',item['current_revision_id']))
            doc=revision['doc']
            statements.append({'id':item['id'],'filename':item['filename'],'vendor':doc.get('vendor','Unidentified vendor'),
                'statementDate':doc.get('statementDate',''),'declaredTotal':doc.get('declaredTotal'),
                'version':item['version'],'completed':item['completed'],'archived':item['archived'],
                'originalAvailable':bool(item.get('original_object_key'))})
        mapping_rows=[]; offset=0
        while True:
            page=self._table('ap_vendor_mappings').order('vendor').range(offset,offset+PAGE_SIZE-1).execute().data
            mapping_rows.extend(page)
            if len(page)<PAGE_SIZE: break
            offset+=PAGE_SIZE
        capabilities={'billSnapshots':2} if 'import_version' in home else {}
        if home.get('duplicate_schema_version')==1: capabilities['duplicateBills']=1
        if home.get('rereview_schema_version')==1: capabilities['statementRereview']=1
        return {'activeImport':active,'capabilities':capabilities,
                'importVersion':home.get('import_version'),
                'mappings':{r['vendor']:r['bill_vendor'] for r in mapping_rows},
                'mappingVersions':{r['vendor']:r['version'] for r in mapping_rows},'statements':statements,
                'nextCursor':items[-1]['id'] if len(items)==limit else None}

    @safe_backend
    def rereview_enabled(self,workspace_id):
        self._workspace(workspace_id);self._private_bucket()
        home=self._one(self.client.table('ap_workspaces').select('*').eq('id',workspace_id))
        return home.get('rereview_schema_version')==1

    @safe_backend
    def revision_for_save(self,workspace_id,statement_id,version):
        self._workspace(workspace_id);self._private_bucket();require_uuid(statement_id);integer(version,minimum=1)
        row=self._one(self._table('ap_statement_revisions').eq('statement_id',statement_id).eq('version',version))
        return {'doc':row['doc'],'results':row['results'],'resolutions':row['resolutions'],
                'importId':row['import_id'],'mappingSnapshot':row['mapping_snapshot'],'ruleVersion':row['rule_version']}

    @safe_backend
    def records_page(self,workspace_id,import_id,after_ordinal=-1,limit=PAGE_SIZE):
        self._workspace(workspace_id); integer(after_ordinal,minimum=-1,maximum=99999); integer(limit,minimum=1,maximum=PAGE_SIZE)
        info=self.import_info(workspace_id,import_id)
        total=integer(info['record_count'],minimum=1,maximum=100000)
        if info['state']!='ready' or after_ordinal>=total: raise ApStoreError()
        rows=self._table('ap_bill_records').eq('import_id',import_id).gt('ordinal',after_ordinal).order('ordinal').limit(limit).execute().data
        expected=min(limit,total-after_ordinal-1)
        if len(rows)!=expected or any(r['ordinal']!=after_ordinal+1+i for i,r in enumerate(rows)): raise ApStoreError()
        records=[{**validate_record(row['record']),'id':f'{import_id}:{row["ordinal"]}'} for row in rows]
        last=rows[-1]['ordinal'] if rows else after_ordinal
        return {'records':records,'nextCursor':last if last+1<total else None,'recordCount':total,'importId':import_id}

    @safe_backend
    def statement(self,workspace_id,statement_id,revision=None):
        self._workspace(workspace_id); self._private_bucket(); require_uuid(statement_id)
        item=self._one(self._table('ap_statements').eq('id',statement_id))
        if item['id']!=statement_id: raise ApStoreError()
        query=self._table('ap_statement_revisions').eq('statement_id',statement_id)
        query=query.eq('id',require_uuid(revision)) if revision else query.eq('id',item['current_revision_id'])
        data=self._one(query)
        source=self.import_info(workspace_id,data['import_id']) if data['import_id'] else None
        return {'doc':data['doc'],'version':item['version'],'revisionVersion':data['version'],'revisionId':data['id'],
                'importLabel':source['metadata'].get('label','') if source else '',
                'importInfo':({key:source[key] for key in ('id','metadata','record_count','created_at')}|{'storage_format':source.get('storage_format','rows-v1')}) if source else None,
                'resolutions':data['resolutions'],'results':data['results'],'importId':data['import_id'],
                'mappingSnapshot':data['mapping_snapshot'],'ruleVersion':data['rule_version'],
                'completed':item['completed'],'archived':item['archived'],'originalAvailable':bool(item.get('original_object_key'))}

    @safe_backend
    def signed_pdf(self,workspace_id,statement_id,expires_in=PREVIEW_SECONDS):
        self._workspace(workspace_id); self._private_bucket(); require_uuid(statement_id)
        integer(expires_in,minimum=1,maximum=PREVIEW_SECONDS)
        item=self._one(self._table('ap_statements').eq('id',statement_id))
        if item['id']!=statement_id: raise ApStoreError()
        key=item.get('original_object_key')
        if not key or not re.fullmatch(re.escape(workspace_id)+r'/pdf/[a-f0-9]{64}\.pdf',key): raise ApStoreError()
        result=self.client.storage.from_(self.config.bucket).create_signed_url(key,expires_in)
        url=result.get('signedURL') or result.get('signedUrl')
        if not url or not url.startswith(self.config.supabase_url+'/storage/v1/object/sign/'+self.config.bucket+'/'): raise ApStoreError()
        return {'url':url,'expiresIn':expires_in,'expiresAt':(datetime.now(timezone.utc)+timedelta(seconds=expires_in)).isoformat()}

    @safe_backend
    def history_page(self,workspace_id,filters,cursor=None,limit=50):
        self._workspace(workspace_id); self._private_bucket(); integer(limit,minimum=1,maximum=50)
        query=self._table('ap_completion_events').eq('event','completed').order('created_at',desc=True).order('id',desc=True).limit(limit)
        for key,column in [('vendor','vendor'),('statementDate','statement_date'),('initials','initials'),('status','status')]:
            if filters.get(key): query=query.eq(column,filters[key])
        for key,method in [('completedFrom','gte'),('completedTo','lte')]:
            if filters.get(key): query=getattr(query,method)('created_at',filters[key])
        if cursor:
            at,row_id=json.loads(base64.urlsafe_b64decode(cursor.encode('ascii')))
            at=datetime.fromisoformat(at).isoformat(); require_uuid(row_id)
            query=query.or_(f'created_at.lt.{at},and(created_at.eq.{at},id.lt.{row_id})')
        events=query.execute().data
        items=[]
        for event in events:
            revision=self._one(self._table('ap_statement_revisions').eq('id',event['revision_id']))
            doc=revision['doc']
            items.append({'id':event['id'],'statementId':event['statement_id'],'revisionId':event['revision_id'],
                          'vendor':doc['vendor'],'filename':doc['filename'],'statementDate':doc.get('statementDate',''),
                          'initials':event['initials'],'status':event['status'],'completedAt':event['created_at'],'notes':event['note'],
                          'progress':review_progress(revision)})
        following=base64.urlsafe_b64encode(json.dumps([events[-1]['created_at'],events[-1]['id']]).encode('utf-8')).decode('ascii') if len(events)==limit else None
        return {'items':items,'nextCursor':following}

    @safe_backend
    def transact(self,operation,workspace_id,request_id,payload_hash,data):
        self._workspace(workspace_id); self._private_bucket(); require_uuid(request_id)
        operations={'register_statement','save_revision','complete_revision','reopen_statement','archive_statement','begin_import','append_records','activate_import','save_mapping','begin_upload','put_chunk','finish_upload','migrate_legacy','attach_original'}
        if operation not in operations: raise ApStoreError('validation')
        response=self.client.rpc('ap_'+operation,{'p_workspace':workspace_id,'p_request_id':request_id,
                    'p_payload_hash':payload_hash,'p_data':data}).execute().data
        if not isinstance(response,dict): raise ApStoreError()
        return response

    @safe_backend
    def upload_info(self,workspace_id,upload_id):
        self._workspace(workspace_id); self._private_bucket(); require_uuid(upload_id)
        item=self._one(self._table('ap_uploads').eq('id',upload_id))
        if item['id']!=upload_id: raise ApStoreError()
        return item

    @safe_backend
    def write_bytes(self,workspace_id,key,data,content_type):
        self._object_key(workspace_id,key); self._private_bucket()
        bucket=self.client.storage.from_(self.config.bucket)
        try:
            bucket.upload(key,data,file_options={'content-type':content_type,'upsert':'false'})
        except Exception:
            # An acknowledgement may be lost after a successful immutable upload.
            # Reuse only exactly identical bytes; never enable overwrite/upsert.
            try: existing=bucket.download(key)
            except Exception: raise ApStoreError('not_saved') from None
            if existing!=data: raise ApStoreError('not_saved') from None
        return {'saved':True}

    @safe_backend
    def read_bytes(self,workspace_id,key):
        self._object_key(workspace_id,key); self._private_bucket()
        return self.client.storage.from_(self.config.bucket).download(key)

    @safe_backend
    def begin_attempt(self,session_nonce,now):
        require_uuid(session_nonce)
        ticket=self.client.rpc('ap_begin_access_attempt',{'p_workspace':self.config.workspace_id,'p_nonce':session_nonce}).execute().data
        return require_uuid(ticket) if ticket else None

    @safe_backend
    def finish_attempt(self,ticket,succeeded,now):
        require_uuid(ticket)
        self.client.rpc('ap_finish_access_attempt',{'p_workspace':self.config.workspace_id,'p_ticket':ticket,'p_success':bool(succeeded)}).execute()
