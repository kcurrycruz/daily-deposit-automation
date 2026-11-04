"""Read-only Gmail protocol. Network adapters must enforce response byte limits."""
import base64
import binascii
from dataclasses import dataclass, field
import re
from urllib.parse import quote

from .contracts import MAX_FILE_BYTES, MailError, bounded_text, natural

BASE = 'https://gmail.googleapis.com/gmail/v1/users/me'
USERINFO = 'https://openidconnect.googleapis.com/v1/userinfo'


def opaque(value, maximum=256):
    value = bounded_text(value, maximum)
    if not re.fullmatch('[A-Za-z0-9_-]+', value): raise MailError('invalid')
    return value


def decode_pdf(data, size):
    natural(size, 1, MAX_FILE_BYTES)
    if type(data) is not str or len(data) > ((MAX_FILE_BYTES+2)//3)*4:
        raise MailError('limit')
    if not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', data): raise MailError('unreadable')
    try: raw = base64.b64decode(data + '='*((-len(data)) % 4), altchars=b'-_', validate=True)
    except (ValueError, binascii.Error): raise MailError('unreadable') from None
    if len(raw) != size or not raw.startswith(b'%PDF-'): raise MailError('unreadable')
    return raw


@dataclass(frozen=True)
class AttachmentPart:
    part_path: str
    filename: str
    mime_type: str
    size: int
    attachment_id: str | None = field(default=None, repr=False)
    inline_bytes: bytes | None = field(default=None, repr=False)


def attachment_parts(message):
    """MIME indices, not thread IDs or filenames, identify each attachment."""
    if type(message) is not dict or type(message.get('payload')) is not dict: raise MailError('unreadable')
    output, count = [], 0

    def walk(part, path, depth):
        nonlocal count
        count += 1
        if depth > 20 or count > 200: raise MailError('limit')
        if type(part) is not dict: raise MailError('unreadable')
        mime = bounded_text(part.get('mimeType', ''), 256, blank=True).lower()
        name = bounded_text(part.get('filename', ''), 1024, blank=True)
        is_pdf = mime == 'application/pdf' or (name.lower().endswith('.pdf') and mime in ('', 'application/octet-stream'))
        if is_pdf:
            body = part.get('body')
            if type(body) is not dict: raise MailError('unreadable')
            size = natural(body.get('size'), 1, MAX_FILE_BYTES)
            attach, data = body.get('attachmentId'), body.get('data')
            if attach is not None and data: raise MailError('unreadable')
            if attach is not None:
                attach = opaque(attach, 4096)
                output.append(AttachmentPart(path, name or 'statement.pdf', 'application/pdf', size, attach))
            elif data:
                output.append(AttachmentPart(path, name or 'statement.pdf', 'application/pdf', size, inline_bytes=decode_pdf(data, size)))
            else: raise MailError('unreadable')
        children = part.get('parts', [])
        if type(children) is not list or len(children) > 200: raise MailError('limit')
        for index, child in enumerate(children): walk(child, path + '.' + str(index), depth+1)

    walk(message['payload'], '0', 0)
    return output


class GmailClient:
    def __init__(self, transport, token_provider, account_id, email, label_id):
        self.transport, self.token_provider = transport, token_provider
        self.account_id = bounded_text(account_id, 256)
        self.email = bounded_text(email, 320)
        self.label_id = opaque(label_id)

    def _get(self, path, params=None, *, max_bytes=2*1024*1024, identity=False):
        try:
            token = bounded_text(self.token_provider(), 16384)
            response = self.transport.request('GET', USERINFO if identity else BASE+path,
                headers={'Authorization':'Bearer '+token}, params=params or {}, timeout=20, max_bytes=max_bytes)
            status = response.status_code
            if status != 200:
                raise MailError({401:'auth',403:'denied',404:'not_found',429:'quota'}.get(status, 'unavailable'))
            result = response.json()
            if type(result) is not dict: raise MailError('unreadable')
            return result
        except MailError: raise
        except Exception: raise MailError('unavailable') from None

    def profile(self):
        identity = self._get('', identity=True)
        if (identity.get('sub') != self.account_id or identity.get('email_verified') is not True or
                str(identity.get('email', '')).casefold() != self.email.casefold()): raise MailError('wrong_account')
        result = self._get('/profile')
        if str(result.get('emailAddress', '')).casefold() != self.email.casefold(): raise MailError('wrong_account')
        opaque(result.get('historyId'))
        natural(result.get('messagesTotal', 0))
        return result

    def labels(self):
        items = self._get('/labels').get('labels')
        if type(items) is not list or len(items) > 10000: raise MailError('unreadable')
        for item in items:
            if type(item) is not dict: raise MailError('unreadable')
            opaque(item.get('id')); bounded_text(item.get('name'), 1024)
        if not any(item['id'] == self.label_id for item in items): raise MailError('label_missing')
        return items

    def message(self, message_id):
        message_id = opaque(message_id)
        result = self._get('/messages/'+quote(message_id, safe=''), {'format':'full'}, max_bytes=40*1024*1024)
        if result.get('id') != message_id: raise MailError('unreadable')
        opaque(result.get('threadId'))
        timestamp = result.get('internalDate')
        if type(timestamp) is not str or not timestamp.isascii() or not timestamp.isdigit(): raise MailError('unreadable')
        natural(int(timestamp), 0, 253402300799999)
        labels = result.get('labelIds', [])
        if type(labels) is not list or len(labels) > 1000: raise MailError('unreadable')
        for label in labels: opaque(label)
        if type(result.get('payload')) is not dict: raise MailError('unreadable')
        return result

    def history(self, history_id, page_token=None):
        params = {'startHistoryId':opaque(history_id), 'labelId':self.label_id, 'maxResults':100}
        if page_token is not None: params['pageToken'] = bounded_text(page_token, 4096)
        result = self._get('/history', params)
        opaque(result.get('historyId'))
        if type(result.get('history', [])) is not list: raise MailError('unreadable')
        if 'nextPageToken' in result: bounded_text(result['nextPageToken'], 4096)
        return result

    def messages(self, page_token=None, query=None):
        params = {'labelIds':self.label_id, 'maxResults':100, 'includeSpamTrash':'false'}
        if page_token is not None: params['pageToken'] = bounded_text(page_token, 4096)
        if query is not None: params['q'] = bounded_text(query, 1024)
        result = self._get('/messages', params)
        if type(result.get('messages', [])) is not list: raise MailError('unreadable')
        for message in result.get('messages', []):
            if type(message) is not dict: raise MailError('unreadable')
            opaque(message.get('id')); opaque(message.get('threadId'))
        if 'nextPageToken' in result: bounded_text(result['nextPageToken'], 4096)
        return result

    def attachment(self, message_id, attachment_id):
        result = self._get('/messages/'+quote(opaque(message_id), safe='')+'/attachments/'+
                           quote(opaque(attachment_id, 4096), safe=''), max_bytes=29*1024*1024)
        return decode_pdf(result.get('data'), result.get('size'))
