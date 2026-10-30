from contextlib import contextmanager
from types import SimpleNamespace
import gzip
import hashlib
import json
import sqlite3
import time
import unittest
from uuid import uuid4
import test_ap_duplicates_artifacts as artifact_fixtures
from fixtures.ap_shared.duplicate_cases import PIN,bill
from test_ap_shared_access import CONFIG

class FrozenEvidenceTests(unittest.TestCase):
    def test_saved_historical_members_do_not_require_current_source_or_current_rules(self):
        from app.ap_shared.bills.working.protection_evidence import FrozenDuplicateEvidence
        f=artifact_fixtures.DuplicateArtifactTests();folder,source,packed,report,repo,scan,_=f.fixture();self.addCleanup(f.doCleanups)
        values=[bill(),bill('271712X'),bill('WORKING-ONLY-SECRET',vendor='Unrelated')]
        full=sqlite3.connect(folder/'source.sqlite');self.addCleanup(full.close)
        full.execute('create table bill_records(ordinal integer primary key,record text)')
        full.executemany('insert into bill_records values(?,?)',[(n,json.dumps(v)) for n,v in enumerate(values)]);full.commit()
        @contextmanager
        def index(ident,auth):
            self.assertEqual(ident,PIN['importId']);yield SimpleNamespace(db=full),{}
        ops=SimpleNamespace(_index=index,_check=lambda _:None)
        for legacy in (False,True):
            raw=folder/('legacy.sqlite' if legacy else 'current.sqlite');raw.write_bytes(gzip.decompress(packed.read_bytes()))
            with sqlite3.connect(raw) as db:
                key=db.execute('select key from findings').fetchone()[0]
                if legacy:db.execute('alter table findings drop column evidence');db.execute('pragma user_version=1')
            db.close();data=raw.read_bytes();archive=gzip.compress(data,mtime=0)
            info={**report['artifact'],'hash':hashlib.sha256(archive).hexdigest(),'bytes':len(archive),'expandedHash':hashlib.sha256(data).hexdigest(),'expandedBytes':len(data)}
            if legacy:info.update(format='bill-duplicates-v1',ruleVersion='bill-duplicates-v1')
            version='v1' if legacy else 'v2'
            mf={**info,'key':f'{CONFIG.workspace_id}/bill-duplicates/{version}/{PIN["importId"]}/{info["ruleVersion"]}/{info["hash"]}.sqlite.gz'}
            path=folder/('legacy.gz' if legacy else 'current.gz');path.write_bytes(archive)
            fake=SimpleNamespace(config=CONFIG,scan=lambda ident:dict(id=ident,workspace_id=CONFIG.workspace_id,import_id=PIN['importId'],source_digest=PIN['sourceDigest'],rule_version=mf['ruleVersion'],state='ready',manifest=mf),read_result=lambda manifest,target,**kwargs:target.write_bytes(path.read_bytes()))
            reader=FrozenDuplicateEvidence(fake,ops);self.addCleanup(reader.close)
            evidence=reader(dict(scan_id=str(uuid4()),key=key,reviewed_import_id=PIN['importId']),None)
            self.assertEqual(evidence['memberCount'],2)
            self.assertEqual([m['bill']['id'] for m in evidence['members']],[f'{PIN["importId"]}:0',f'{PIN["importId"]}:1'])
            with sqlite3.connect(folder/'source.sqlite') as db:db.execute('update bill_records set record=? where ordinal=0',(json.dumps(bill('WRONG')),))
            db.close()
            with self.assertRaises(ValueError):reader(dict(scan_id=str(uuid4()),key=key,reviewed_import_id=PIN['importId']),None)
            full.execute('update bill_records set record=? where ordinal=0',(json.dumps(values[0]),));full.commit()
