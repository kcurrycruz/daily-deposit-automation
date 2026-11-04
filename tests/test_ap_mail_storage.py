import hashlib
import httpx
import unittest
from app.ap_mail.contracts import MailConfig,MailError
from fixtures.ap_mail.store_double import W,C

PDF=b'%PDF-test'
CONFIG=MailConfig('https://synthetic.supabase.co','TEST-SECRET',W,'hwfc-ap-private',C,'processor')

class OriginalStoreTests(unittest.TestCase):
    def make(self,handler):
        from app.ap_mail.storage import OriginalStore
        return OriginalStore(CONFIG,transport=httpx.MockTransport(handler))

    def test_private_immutable_upload_lost_ack_and_hash_collision(self):
        requests=[]
        def respond(req):
            requests.append(req)
            self.assertEqual(req.url.host,'synthetic.supabase.co')
            self.assertEqual(req.headers['Authorization'],'Bearer TEST-SECRET')
            return httpx.Response(409) if req.method=='POST' else httpx.Response(200,content=PDF)
        sha=self.make(respond).put(PDF)
        self.assertEqual(sha,hashlib.sha256(PDF).hexdigest())
        self.assertTrue(requests[0].url.path.endswith('/'+W+'/pdf/'+sha+'.pdf'))
        self.assertEqual(requests[0].headers['x-upsert'],'false')
        def collision(req):return httpx.Response(409) if req.method=='POST' else httpx.Response(200,content=b'%PDF-other')
        with self.assertRaises(MailError):self.make(collision).put(PDF)

    def test_invalid_signature_and_oversize_never_upload(self):
        calls=[]
        store=self.make(lambda req:calls.append(req))
        for raw in [b'bad',b'%PDF-'+b'x'*(20*1024*1024)]:
            with self.assertRaises(MailError):store.put(raw)
        self.assertEqual(calls,[])

    def test_lost_upload_response_verifies_existing_private_bytes(self):
        def respond(req):
            if req.method=='POST':raise httpx.ReadTimeout('secret diagnostics must not escape')
            return httpx.Response(200,content=PDF)
        self.assertEqual(self.make(respond).put(PDF),hashlib.sha256(PDF).hexdigest())

    def test_existing_object_stream_is_bounded_and_redirects_rejected(self):
        class Chunks(httpx.SyncByteStream):
            def __iter__(self):
                for _ in range(25):yield b'x'*(1024*1024)
        for reply in [httpx.Response(200,stream=Chunks()),httpx.Response(302,headers={'location':'https://elsewhere.example'})]:
            with self.assertRaises(MailError):
                self.make(lambda req:httpx.Response(409) if req.method=='POST' else reply).put(PDF)
