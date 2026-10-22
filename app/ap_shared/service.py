"""Validated AP operations. Originals and saved history are never overwritten."""
import base64
import binascii
import csv
from datetime import datetime
import hashlib
import io
import json
import re
from uuid import UUID, uuid5
from .access import require_access
from .models import (ApConfig,Authorization,JsonObject,ApValidationError,allowed,text,integer,date_value,
    require_uuid,normalize_initials,validate_record,validate_statement,validate_resolution,validate_provider_metadata,
    MAX_FILE_BYTES,MAX_CHUNK_BYTES,MAX_RECORDS,PAGE_SIZE,RULE_VERSION,BILL_ACTIONS,DUPLICATE_ACTIONS)

class ApService:
    def __init__(self,repository,config:ApConfig,clock,revalidate):
        self.repository=repository
        self.config=config
        self.clock=clock
        self.revalidate=revalidate
        self.bill_operations=None
        self.duplicate_operations=None

    def _check(self,authorization):
        current=self.revalidate()
        if current!=authorization: raise PermissionError('AP access is locked.')
        require_access({'_ap_authorization':current,'_ap_session_nonce':current.session_nonce},self.config,self.clock())

    def _tx(self,operation,data,request_id,authorization,*,step=None):
        self._check(authorization)
        actual=str(uuid5(UUID(request_id),step)) if step else request_id
        digest=hashlib.sha256(json.dumps({'operation':operation,'data':data},sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()
        return self.repository.transact(operation,self.config.workspace_id,actual,digest,data)

    def _upload(self,upload_id,authorization):
        require_uuid(upload_id)
        self._check(authorization)
        upload=self.repository.upload_info(self.config.workspace_id,upload_id)
        if upload['session_nonce']!=authorization.session_nonce: raise PermissionError('This staged upload is not available in this session.')
        return upload

    def _part_key(self,upload_id,index,part_hash):
        return f'{self.config.workspace_id}/staging/{upload_id}/{index}-{part_hash}.bin'

    def _results(self,value):
        if type(value) is not list: raise ApValidationError('Comparison evidence must be a list.')
        statuses=set('matched missing amount balance scheduled paid ambiguous extraction unverified credit history presence source possible vendor'.split())
        output=[]
        for row in value:
            out=allowed(row,'id invoiceNumber kind originalAmount outstanding activity date confidence duplicate page status reason candidates matchMethod referenceRule statementId vendor simulated','id status candidates')
            text(out['id'],maximum=512,blank=False)
            if type(out['status']) is not str or out['status'] not in statuses or out.get('simulated') is True: raise ApValidationError('Invalid comparison evidence.')
            if out.get('matchMethod') not in (None,'reference','amount'): raise ApValidationError('Invalid comparison method.')
            if 'referenceRule' in out and out['referenceRule']!='adventure-trailing-letter-v1': raise ApValidationError('Invalid reference rule.')
            if type(out['candidates']) is not list: raise ApValidationError('Invalid candidates.')
            out['candidates']=[validate_record(candidate) for candidate in out['candidates']]
            if out.get('matchMethod')=='amount' and out['status']=='matched': raise ApValidationError('Amount-only suggestions are not verified matches.')
            for key in ('originalAmount','outstanding'):
                if key in out: integer(out[key],nullable=True)
            for key in ('reason','vendor','invoiceNumber'):
                if key in out: text(out[key],maximum=16384)
            output.append(out)
        return output

    def handle(self,action:str,payload:JsonObject,request_id:str,authorization:Authorization) -> JsonObject:
        require_uuid(request_id); self._check(authorization)
        workspace=self.config.workspace_id
        if action in DUPLICATE_ACTIONS:
            if self.duplicate_operations is None:
                from .bills.operations import create_bill_operations
                from .bills.duplicates.operations import create_duplicate_operations
                if self.bill_operations is None:
                    self.bill_operations=create_bill_operations(self.repository,self.config,self.clock,self.revalidate)
                self.duplicate_operations=create_duplicate_operations(self.repository,self.bill_operations,self.config,self.clock,self.revalidate)
            return self.duplicate_operations.handle(action,payload,request_id,authorization)
        if action in BILL_ACTIONS:
            if self.bill_operations is None:
                from .bills.operations import create_bill_operations
                self.bill_operations=create_bill_operations(self.repository,self.config,self.clock,self.revalidate)
            return self.bill_operations.handle(action,payload,request_id,authorization)
        if action=='bootstrap':
            data=allowed(payload,'cursor limit')
            return self.repository.bootstrap(workspace,data.get('cursor'),data.get('limit',50))
        if action=='records_page':
            data=allowed(payload,'import_id after_ordinal limit','import_id')
            return self.repository.records_page(workspace,require_uuid(data['import_id']),data.get('after_ordinal',-1),data.get('limit',PAGE_SIZE))
        if action=='statement':
            data=allowed(payload,'statement_id revision_id','statement_id')
            return self.repository.statement(workspace,require_uuid(data['statement_id']),data.get('revision_id'))
        if action=='pdf_preview':
            data=allowed(payload,'statement_id','statement_id')
            return self.repository.signed_pdf(workspace,require_uuid(data['statement_id']))
        if action=='history_page':
            data=allowed(payload,'filters cursor limit')
            filters=allowed(data.get('filters',{}),'vendor statementDate initials status completedFrom completedTo')
            for key in ('vendor','status'):
                if key in filters: text(filters[key],maximum=1024)
            if filters.get('initials'): filters['initials']=normalize_initials(filters['initials'])
            if filters.get('statementDate'): date_value(filters['statementDate'])
            for key in ('completedFrom','completedTo'):
                if filters.get(key):
                    # Calendar filters are converted by the browser to UTC ISO boundaries for New York.
                    text(filters[key],maximum=40)
                    try: datetime.fromisoformat(filters[key])
                    except ValueError: raise ApValidationError('A valid completion-date filter is required.') from None
            return self.repository.history_page(workspace,filters,data.get('cursor'),data.get('limit',50))
        if action=='upload_begin':
            data=allowed(payload,'kind filename size file_hash','kind filename size file_hash')
            if data['kind'] not in ('pdf','csv') or not re.fullmatch('[a-f0-9]{64}',text(data['file_hash'],maximum=64)):
                raise ApValidationError('A valid file type and hash are required.')
            integer(data['size'],minimum=1,maximum=MAX_FILE_BYTES); text(data['filename'],maximum=1024,blank=False)
            upload_id=str(uuid5(UUID(authorization.session_nonce),request_id))
            return self._tx('begin_upload',{'upload_id':upload_id,'session_nonce':authorization.session_nonce,'metadata':data},request_id,authorization)
        if action=='upload_chunk':
            data=allowed(payload,'upload_id index data','upload_id index data')
            upload=self._upload(data['upload_id'],authorization)
            index=integer(data['index'],minimum=0,maximum=(MAX_FILE_BYTES//MAX_CHUNK_BYTES)-1)
            encoded=text(data['data'],maximum=4*((MAX_CHUNK_BYTES+2)//3))
            try: raw=base64.b64decode(encoded,validate=True)
            except (ValueError,binascii.Error): raise ApValidationError('The file chunk is not valid base64.') from None
            expected=min(MAX_CHUNK_BYTES,upload['metadata']['size']-index*MAX_CHUNK_BYTES)
            if len(raw)!=expected or expected<1: raise ApValidationError('File chunk size or position is invalid.')
            digest=hashlib.sha256(raw).hexdigest()
            previous=upload['chunks'].get(str(index))
            if previous and (previous['hash']!=digest or previous['size']!=len(raw)): raise ApValidationError('A different chunk cannot overwrite this upload.')
            if previous is None and index!=len(upload['chunks']): raise ApValidationError('Upload chunks in order.')
            self._check(authorization)
            self.repository.write_bytes(workspace,self._part_key(data['upload_id'],index,digest),raw,'application/octet-stream')
            return self._tx('put_chunk',{'upload_id':data['upload_id'],'session_nonce':authorization.session_nonce,'index':index,'chunk_hash':digest,'size':len(raw)},request_id,authorization)
        if action=='upload_finish':
            data=allowed(payload,'upload_id statement_id expected_version','upload_id'); upload=self._upload(data['upload_id'],authorization)
            if 'statement_id' in data:require_uuid(data['statement_id']);integer(data.get('expected_version'),minimum=1)
            meta=upload['metadata']; key=f'{workspace}/{meta["kind"]}/{meta["file_hash"]}.{meta["kind"]}'
            if upload['state']!='ready':
                parts=[]
                for i in range((meta['size']+MAX_CHUNK_BYTES-1)//MAX_CHUNK_BYTES):
                    part=upload['chunks'].get(str(i))
                    if not part: raise ApValidationError('The original upload is incomplete.')
                    self._check(authorization)
                    raw=self.repository.read_bytes(workspace,self._part_key(data['upload_id'],i,part['hash']))
                    if len(raw)!=part['size'] or hashlib.sha256(raw).hexdigest()!=part['hash']: raise ApValidationError('The uploaded chunk could not be verified.')
                    parts.append(raw)
                original=b''.join(parts)
                if len(original)!=meta['size'] or hashlib.sha256(original).hexdigest()!=meta['file_hash']: raise ApValidationError('The original file could not be verified.')
                if meta['kind']=='pdf':
                    if not original.startswith(b'%PDF-'): raise ApValidationError('The uploaded file is not a PDF.')
                else:
                    try:
                        reader=csv.reader(io.StringIO(original.decode('utf-8-sig')),strict=True)
                        header=next(reader)
                        if not header or any(len(row)!=len(header) for row in reader if row): raise ValueError
                    except (ValueError,UnicodeError,csv.Error,StopIteration): raise ApValidationError('The uploaded CSV is not readable or has inconsistent columns.') from None
                self._check(authorization)
                self.repository.write_bytes(workspace,key,original,'application/pdf' if meta['kind']=='pdf' else 'text/csv')
            self._tx('finish_upload',{'upload_id':data['upload_id'],'session_nonce':authorization.session_nonce,'object_key':key},request_id,authorization,step='finish-upload')
            reply={'upload_id':data['upload_id'],'kind':meta['kind'],'file_hash':meta['file_hash']}
            if meta['kind']=='pdf':
                if 'statement_id' in data:
                    reply.update(self._tx('attach_original',{'statement_id':data['statement_id'],'expected_version':data['expected_version'],'file_hash':meta['file_hash'],'original_object_key':key},request_id,authorization,step='attach-original'))
                    return reply
                statement_id=str(uuid5(UUID(data['upload_id']),'statement'))
                doc={'id':statement_id,'vendor':'Unidentified vendor','filename':meta['filename'],'layout':'generic',
                     'statementDate':'','declaredTotal':None,'confirmed':False,'pageCount':1,'rows':[],
                     'warnings':['Original saved. Extraction has not been confirmed.'],'notes':'','createdAt':upload.get('created_at','')}
                reply.update(self._tx('register_statement',{'statement_id':statement_id,'file_hash':meta['file_hash'],'original_object_key':key,'doc':doc},request_id,authorization,step='register-statement'))
            return reply
        if action=='import_begin':
            data=allowed(payload,'upload_id provider record_count','upload_id provider record_count')
            upload=self._upload(data['upload_id'],authorization)
            if upload['state']!='ready' or upload['metadata']['kind']!='csv': raise ApValidationError('Save the original Bills CSV before importing records.')
            metadata=validate_provider_metadata(data['provider']); metadata['label']=upload['metadata']['filename']
            integer(data['record_count'],minimum=1,maximum=MAX_RECORDS)
            return self._tx('begin_import',{'file_hash':upload['metadata']['file_hash'],'original_object_key':upload['object_key'],
                            'metadata':metadata,'record_count':data['record_count']},request_id,authorization)
        if action=='import_records':
            data=allowed(payload,'import_id start records','import_id start records'); require_uuid(data['import_id'])
            integer(data['start'],minimum=0,maximum=MAX_RECORDS-1)
            if type(data['records']) is not list or not 1<=len(data['records'])<=PAGE_SIZE: raise ApValidationError('Record batch size is invalid.')
            data['records']=[validate_record(record) for record in data['records']]
            return self._tx('append_records',data,request_id,authorization)
        if action=='import_finish':
            data=allowed(payload,'import_id','import_id'); require_uuid(data['import_id'])
            return self._tx('activate_import',data,request_id,authorization)
        if action=='save_revision':
            data=allowed(payload,'statement_id expected_version doc resolutions import_id mapping_snapshot results rule_version','statement_id expected_version doc resolutions import_id mapping_snapshot results rule_version')
            require_uuid(data['statement_id']); integer(data['expected_version'],minimum=1)
            data['doc']=validate_statement(data['doc'])
            if data['doc']['id']!=data['statement_id']: raise ApValidationError('The statement identifier does not agree.')
            if data['import_id'] is not None: require_uuid(data['import_id'])
            if type(data['mapping_snapshot']) is not dict or type(data['resolutions']) is not dict: raise ApValidationError('Invalid mappings or review decisions.')
            for vendor,mapped in data['mapping_snapshot'].items(): text(vendor,maximum=1024); text(mapped,maximum=1024)
            resolutions={}
            for row_id,decision in data['resolutions'].items():
                text(row_id,maximum=512,blank=False); resolutions[row_id]=validate_resolution(decision)
                resolutions[row_id].pop('at',None)
            data['resolutions']=resolutions; data['results']=self._results(data['results'])
            for row_id,resolution in resolutions.items():
                proof=resolution.get('confirmedMatch')
                if proof is None: continue
                row=next((item for item in data['results'] if item['id']==row_id),None)
                bill=proof['candidate']
                if (not data['doc']['confirmed'] or row is None or
                    not any(item['id']==row_id for item in data['doc']['rows']) or
                    row['status'] not in ('possible','ambiguous','amount') or
                    row.get('matchMethod') not in ('amount','reference') or
                    row.get('kind','invoice')!='invoice' or row.get('duplicate') or
                    proof['statementReference']!=row.get('invoiceNumber') or
                    proof['statementAmount']!=row.get('originalAmount') or
                    row['candidates'].count(bill)!=1 or bill.get('sourceIssues') or
                    bill.get('currency') not in (None,'','USD') or bill.get('kind','invoice')!='invoice'):
                    raise ApValidationError('Check the PDF and choose a valid candidate from this invoice comparison before confirming.')
            if data['rule_version']!=RULE_VERSION: raise ApValidationError('Reload the app before saving comparisons from a different rule version.')
            return self._tx('save_revision',data,request_id,authorization)
        if action=='save_mapping':
            data=allowed(payload,'vendor bill_vendor expected_version','vendor bill_vendor expected_version')
            text(data['vendor'],maximum=1024,blank=False); text(data['bill_vendor'],maximum=1024,blank=False)
            integer(data['expected_version'],minimum=0)
            return self._tx('save_mapping',data,request_id,authorization)
        if action in ('complete_revision','reopen_statement','archive_statement'):
            keys='statement_id expected_version initials notes' if action=='complete_revision' else 'statement_id expected_version'
            data=allowed(payload,keys,'statement_id expected_version'); require_uuid(data['statement_id']); integer(data['expected_version'],minimum=1)
            if action=='complete_revision':
                data['initials']=normalize_initials(data.get('initials','')); data['notes']=text(data.get('notes',''),maximum=16384)
            return self._tx(action,data,request_id,authorization)
        if action=='migrate_legacy':
            data=allowed(payload,'confirmed statements','confirmed statements')
            if data['confirmed'] is not True or type(data['statements']) is not list or not 1<=len(data['statements'])<=20:
                raise ApValidationError('Explicitly confirm a migration of up to twenty statements.')
            prepared=[];seen=set()
            for item in data['statements']:
                item=allowed(item,'doc resolutions','doc resolutions');original=dict(item['doc'])
                old_id=text(original.get('id'),maximum=256,blank=False)
                if old_id in seen:raise ApValidationError('Duplicate legacy statement identifiers.')
                seen.add(old_id)
                digest=hashlib.sha256(json.dumps(original,sort_keys=True,allow_nan=False).encode()).hexdigest()
                sid=str(uuid5(UUID(workspace),'legacy:'+old_id+':'+digest));original['id']=sid;original['confirmed']=False
                old_rows={};seen_rows=set()
                for row in original['rows']:
                    old_row=text(row.get('id'),maximum=256,blank=False)
                    if old_row in seen_rows:raise ApValidationError('Duplicate legacy row identifiers.')
                    seen_rows.add(old_row);old_rows[old_row]=str(uuid5(UUID(sid),old_row))
                original['rows']=[{**row,'id':old_rows[row['id']]} for row in original['rows']]
                original['warnings']=[*original['warnings'],'Migrated draft. Original PDF not attached; extraction and comparisons must be confirmed again.']
                doc=validate_statement(original)
                if type(item['resolutions']) is not dict:raise ApValidationError('Invalid legacy notes.')
                notes={}
                for row_id,resolution in item['resolutions'].items():
                    value=validate_resolution(resolution)
                    if row_id in old_rows:notes[old_rows[row_id]]={'note':value['note']}
                prepared.append({'statement_id':sid,'doc':doc,'resolutions':notes})
            replies=[self._tx('migrate_legacy',item,request_id,authorization,step='legacy-'+str(index)) for index,item in enumerate(prepared)]
            return {'migrated_count':len(replies),'statements':replies}
        raise ApValidationError('This shared operation is not available.')
