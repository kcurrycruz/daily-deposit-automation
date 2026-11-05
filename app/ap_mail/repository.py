"""Fixed-workspace mail RPC adapter; never accepts client storage targets."""
from uuid import uuid4
from .contracts import MailError, bounded_text, canonical, digest, identifier, natural, payload_digest

OPERATIONS = frozenset('inventory claim heartbeat record_original save_extraction needs_attention release_retry finish '
                       'retry requeue pause reconcile outbox_sent outbox_delay sync_error dispatch_missing dispatch_checkpoint'.split())
FIELDS = {
    'inventory':'connection_id expected_generation expected_version expected_cursor messages receipts next_cursor completed',
    'claim':'job_id dispatch_generation', 'heartbeat':'claim',
    'record_original':'claim sha256 object_key size', 'save_extraction':'claim doc parser_version extraction_digest',
    'needs_attention':'claim reason', 'release_retry':'claim reason delay_seconds', 'finish':'claim status reason',
    'retry':'receipt_id expected_version', 'requeue':'receipt_id expected_version',
    'pause':'connection_id expected_version paused', 'reconcile':'limit',
    'outbox_sent':'job_id dispatch_generation task_name', 'outbox_delay':'job_id dispatch_generation delay_seconds',
    'sync_error':'connection_id expected_generation reason',
    'dispatch_missing':'job_id dispatch_generation',
    'dispatch_checkpoint':'connection_id expected_generation cursor',
}


class MailRepository:
    def __init__(self, config, client):
        self.config, self.client = config, client
        # Reuse the existing SDK diagnostic filters without creating a human session.
        from app.ap_shared.repository import ApRepository
        self.storage = ApRepository(client, config)

    def _rpc(self, name, args):
        try:
            value = self.client.rpc(name, args).execute().data
            if type(value) is not dict: raise MailError('unavailable')
            return value
        except MailError: raise
        except Exception as error:
            from .contracts import CODES
            code = getattr(error, 'message', '')
            raise MailError(code if code in CODES else 'unavailable') from None

    def mutate(self, operation, payload, request_id=None):
        if operation not in OPERATIONS or type(payload) is not dict: raise MailError('invalid')
        if set(payload)-set(FIELDS[operation].split()): raise MailError('invalid')
        forbidden = {'workspace_id', 'password', 'supabase_secret_key', 'sql', 'url'}
        if set(payload) & forbidden: raise MailError('invalid')
        request_id = identifier(request_id or str(uuid4()))
        if len(canonical(payload).encode('utf-8')) > 1024*1024: raise MailError('limit')
        return self._rpc('ap_mail_mutate', dict(p_operation=operation,p_workspace=self.config.workspace_id,
            p_request_id=request_id,p_payload_hash=payload_digest({'operation':operation,'data':payload}),p_data=payload))

    def _read(self, operation, data):
        return self._rpc('ap_mail_read', dict(p_operation=operation,p_workspace=self.config.workspace_id,p_data=data))

    def connection(self):
        return self._read('connection', {'connection_id':self.config.connection_id})['connection']

    def inventory_commit(self, expected_cursor, messages, receipts, next_cursor, *, completed=False):
        return self.mutate('inventory', dict(connection_id=self.config.connection_id,
            expected_generation=expected_cursor['generation'],expected_version=expected_cursor['version'],
            expected_cursor=expected_cursor['cursor'],messages=messages,receipts=receipts,
            next_cursor=next_cursor,completed=completed))

    def status(self): return self._read('status', {})

    def candidates_page(self,cursor=None,limit=50):
        natural(limit,1,50)
        if cursor is not None:identifier(cursor)
        return self._rpc('ap_mail_candidates',dict(p_workspace=self.config.workspace_id,p_cursor=cursor,p_limit=limit))

    def byte_match(self,receipt_id):
        return self._rpc('ap_mail_byte_match',dict(p_workspace=self.config.workspace_id,p_receipt_id=identifier(receipt_id)))['match']

    def publish(self,payload,request_id=None):
        if set(payload)!=set('doc assessment evidence claim pin'.split()) or len(canonical(payload).encode())>1024*1024:raise MailError('invalid')
        return self._rpc('ap_mail_publish',dict(p_workspace=self.config.workspace_id,p_request_id=identifier(request_id or str(uuid4())),
            p_payload_hash=payload_digest({'operation':'publish','data':payload}),p_data=payload))

    def reserve_original(self,claim,size):
        from dataclasses import asdict
        natural(size,1,self.config.max_file_bytes)
        return self._rpc('ap_mail_reserve',dict(p_workspace=self.config.workspace_id,p_claim=asdict(claim),p_bucket=self.config.bucket,
            p_requested=size,p_budget=self.config.storage_budget_bytes))

    def copy_original(self,claim,raw):
        from dataclasses import asdict
        from .storage import OriginalStore
        self.reserve_original(claim,len(raw));self.storage._private_bucket()
        sha=OriginalStore(self.config).put(raw)
        self.mutate('record_original',dict(claim=asdict(claim),sha256=sha,object_key=self.config.workspace_id+'/pdf/'+sha+'.pdf',size=len(raw)))
        return sha

    def queue_stale(self,limit=50):
        natural(limit,1,50)
        return self._rpc('ap_mail_queue_stale',dict(p_workspace=self.config.workspace_id,p_connection=self.config.connection_id,p_limit=limit))

    def original_bytes(self,receipt):
        from .storage import OriginalStore
        verified=self.private_original(receipt['id'])
        return OriginalStore(self.config).get(verified['sha256'],verified['actual_size'])

    def receipts_page(self, filters, cursor=None, limit=50):
        natural(limit, 1, 50)
        if filters: raise MailError('invalid')
        if cursor is not None: identifier(cursor)
        return self._read('receipts', {'cursor':cursor,'limit':limit})

    def outbox_page(self, cursor=None, limit=100, *, state='pending'):
        natural(limit, 1, 100)
        if state not in ('pending','sent'): raise MailError('invalid')
        if cursor is not None:
            identifier(cursor['job_id']); natural(cursor['dispatch_generation'], 1)
        return self._read('outbox', {'cursor':cursor,'limit':limit,'state':state})

    def receipt(self, receipt_id):
        return self._read('receipt', {'receipt_id':identifier(receipt_id)})

    def messages_known(self, ids):
        from .gmail import opaque
        if type(ids) is not list or len(ids)>100: raise MailError('invalid')
        for ident in ids: opaque(ident)
        items=self._read('messages',{'connection_id':self.config.connection_id,'ids':ids})['items']
        return {item['message_id']:item for item in items}

    def private_original(self, receipt_id):
        receipt_id = identifier(receipt_id)
        row = self.receipt(receipt_id)
        sha = digest(row.get('sha256'))
        if (row.get('id') != receipt_id or row.get('workspace_id') != self.config.workspace_id or
                row.get('original_object_key') != self.config.workspace_id+'/pdf/'+sha+'.pdf'):
            raise MailError('denied')
        self.storage._private_bucket()
        return row
