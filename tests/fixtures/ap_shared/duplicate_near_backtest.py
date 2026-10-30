"""Read-only saved-export audit; output is aggregate counts, never raw bills."""
import argparse,hashlib,json,sqlite3,sys,tempfile,time
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from app.ap_shared.bills.duplicates.scan import DuplicateScan
from app.ap_shared.bills.duplicates.exclusions import ExactReferenceExclusions
from app.ap_shared.bills.duplicates.contracts import NEAR_RULE_VERSION
from bill_scale_check import peak_rss

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while block:=f.read(262144):h.update(block)
 return h.hexdigest()

def check(path):
 before=sha(path);baseline=peak_rss();started=time.monotonic();maximum=0
 with tempfile.TemporaryDirectory(prefix='hwfc-near-backtest-') as folder,closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(Path(folder)/'scan.sqlite')) as db,closing(sqlite3.connect(Path(folder)/'projection.sqlite')) as local:
  count=source.execute('select count(*) from bill_records').fetchone()[0]
  pin=dict(importId='00000000-0000-4000-8000-000000000001',importVersion=1,sourceDigest=before,storageFormat='snapshot-v2',recordCount=count,ruleVersion=NEAR_RULE_VERSION)
  engine=DuplicateScan(db,pin,time.monotonic);after=-1
  while True:
   rows=source.execute('select ordinal,record from bill_records where ordinal>? order by ordinal limit 5000',(after,)).fetchall()
   if not rows:break
   engine.ingest([dict(ordinal=n,bill=json.loads(raw)) for n,raw in rows]);after=rows[-1][0]
  engine.finish_input();input_seconds=time.monotonic()-started;scan_start=time.monotonic()
  while True:
   at=time.monotonic();r=engine.step(at+5);maximum=max(maximum,time.monotonic()-at)
   if r['done']:break
  summary=engine.finish();scan_seconds=time.monotonic()-scan_start
  local.execute('create table findings(id integer primary key,key text,member_count integer)')
  local.executemany('insert into findings values(?,?,?)',db.execute('select id,key,member_count from findings'))
  reads=[0]
  def members(pin,ordinals,auth):
   reads[0]+=1;values=dict(source.execute('select ordinal,record from bill_records where ordinal in ('+','.join('?' for _ in ordinals)+')',ordinals))
   return [dict(ordinal=n,bill={**json.loads(values[n]),'id':f'{pin["importId"]}:{n}'}) for n in ordinals]
  helper=ExactReferenceExclusions(SimpleNamespace(members=members,ops=SimpleNamespace(_check=lambda _:None)));helper.initialize(local);exclusion_started=time.monotonic()
  while not helper.advance(local,db,{},pin,None,time.monotonic()+5):pass
  exclusions=[key for key, in local.execute('select key from exact_reference_exclusions')];excluded=set(exclusions)
  raw=dict(db.execute('select classification,count(*) from findings group by classification'))
  visible={};typos=0
  for key,kind,reasons in db.execute('select key,classification,reasons from findings'):
   if key in excluded:continue
   visible[kind]=visible.get(kind,0)+1
   if 'single_digit_substitution' in json.loads(reasons):typos+=1
  target={n for n, in source.execute("select ordinal from bill_records where reference_key=? and vendor_key=?",('N2609-61636',"albert's organics inc"))}
  target_groups=[key for ident,key in db.execute('select id,key from findings') if {n for n, in db.execute('select ordinal from members where finding_id=?',(ident,))}==target]
  target_excluded=bool(target) and bool(target_groups) and all(key in excluded for key in target_groups)
  if not target_excluded:raise AssertionError('Known exact-reference export group was not excluded')
  unchanged=sha(path)==before
  if not unchanged:raise AssertionError('Read-only source changed')
  return dict(indexFileSha256=before,sourceUnchanged=unchanged,recordCount=count,ruleVersion=NEAR_RULE_VERSION,rawFindingCount=summary['findingCount'],rawPatterns=raw,excludedExactReferenceCount=len(excluded),visibleFindingCount=sum(visible.values()),visiblePatterns=visible,visibleDigitTypoCount=typos,knownExactGroupExcluded=target_excluded,memberPageReads=reads[0],inputSeconds=round(input_seconds,3),scanSeconds=round(scan_seconds,3),exclusionSeconds=round(time.monotonic()-exclusion_started,3),maxScanStepSeconds=round(maximum,3),peakRssIncreaseBytes=max(0,peak_rss()-baseline),totalSeconds=round(time.monotonic()-started,3))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source_index',type=Path);args=p.parse_args();print(json.dumps(check(args.source_index),sort_keys=True))
