"""Indexed, cooperative candidate corroboration for vendor-aware warnings."""
from datetime import date
import json
from .vendor_patterns import VendorPatterns, month_start, reference_variants, edit_kind
from .rules import classify


class VendorCandidates:
    def __init__(self,scan):
        self.scan=scan;self.db=scan.db;self.patterns=VendorPatterns(self.db)
        self.db.executescript('''
          create index node_vendor_compact on nodes(vendor,amount,compact,day,ordinal) where day is not null;
          create index node_cross_compact on nodes(compact,amount,day,ordinal) where day is not null;
          create table vendor_candidate_pairs(a text,b text,kind text,primary key(a,b,kind));
        ''')

    def _pair(self,cur,other,kind):
        node=cur['node']
        if node['n']!=1 or other['n']!=1 or node['warning'] or other['warning']:return
        if node['currency'] and other['currency'] and node['currency']!=other['currency']:return
        if classify(json.loads(node['preview']),json.loads(other['preview'])) is not None:return
        if kind=='reference_entry_issue' and (len(node['compact'])<4 or len(other['compact'])<4 or edit_kind(node['compact'],other['compact']) is None):return
        ids=sorted([node['ident'],other['ident']])
        found=self.db.execute('insert or ignore into vendor_candidate_pairs values(?,?,?)',(*ids,kind))
        if not found.rowcount:return
        cur['vendor']['pair']=dict(nodes=[node,other],kind=kind,profiles=[],at=0,cutoff=month_start(min(node['day'],other['day'])))

    def _corroborate(self,job):
        nodes=job['nodes'];at=job['at']
        if at<len(nodes):
            node=nodes[at];profile=self.patterns.advance(node['vendor'],job['cutoff'])
            if profile is None:return
            if not profile['established']:return True
            profile={**profile,'vendor':json.loads(node['preview'])['vendor'],
                     'invoiceNumber':json.loads(node['preview'])['invoiceNumber'],
                     'matches':node['shape'] in [v['shape'] for v in profile['shapes']]}
            job['profiles'].append(profile);job['at']+=1
            return
        profiles=job['profiles'];gap=abs(nodes[0]['day']-nodes[1]['day'])
        if profiles[0]['matches']==profiles[1]['matches']:return True
        if job['kind']=='reference_entry_issue' and gap:
            recurrent=self.patterns.recurrence(nodes[0]['vendor'],nodes[0]['amount'],min(n['day'] for n in nodes))
            if recurrent is None:return
            if recurrent:return True
        reasons=['vendor_format_mismatch']
        if not nodes[0]['currency'] or not nodes[1]['currency']:reasons.append('currency_unknown')
        if gap:reasons.append('different_invoice_dates')
        evidence=dict(version=1,dateGapDays=gap,referenceReuse=False,profiles=profiles)
        if job['kind']=='reference_entry_issue':
            evidence['edit']=edit_kind(nodes[0]['compact'],nodes[1]['compact'])
            reasons.append('reference_edit')
        else:reasons.append('cross_vendor_reference')
        self.scan._begin(nodes,dict(classification=job['kind'],strength='possible',reasons=sorted(reasons),evidence=evidence))
        return True

    def step(self,cur):
        """One probe/bounded profile batch. Return True only when this node is done."""
        self.scan.probes+=1;node=cur['node']
        if node['day'] is None or node['n']!=1 or node['warning']:return True
        if 'vendor' not in cur:
            start=month_start(node['day']);months=[start]
            if 0<=node['day']-start<=2 and start>1:months.append(month_start(start-1))
            cur['vendor']=dict(phase='local',months=months,month=0,variants=None,key=None,after=None,pair=None)
        state=cur['vendor']
        if state['pair']:
            if self._corroborate(state['pair']):state['pair']=None
            return False
        if state['phase']=='local':
            if state['variants'] is None:
                if state['month']==len(state['months']):
                    state.update(phase='cross',after=(node['day']-3,-1));return False
                profile=self.patterns.advance(node['vendor'],state['months'][state['month']])
                if profile is None:return False
                state['month']+=1
                if not profile['established'] or node['shape'] in [v['shape'] for v in profile['shapes']]:return False
                state['variants']=iter(reference_variants(json.loads(node['preview'])['invoiceNumber'],[v['shape'] for v in profile['shapes']]))
            if state['key'] is None:
                state['key']=next(state['variants'],None);state['after']=(node['day']-3,-1)
                if state['key'] is None:state['variants']=None;return False
            row=self.db.execute('''select * from nodes indexed by node_vendor_compact
                where vendor=? and amount=? and compact=? and (day,ordinal)>(?,?) and day>=? and day<=? and ordinal<>?
                order by day,ordinal limit 1''',(node['vendor'],node['amount'],state['key'],*state['after'],node['day']-3,node['day']+3,node['ordinal'])).fetchone()
            if row:
                other=self.scan._node(row);state['after']=(other['day'],other['ordinal']);self._pair(cur,other,'reference_entry_issue')
            else:state['key']=None
            return False
        if len(node['compact'])<6:return True
        row=self.db.execute('''select * from nodes indexed by node_cross_compact
            where compact=? and amount=? and (day,ordinal)>(?,?) and day>=? and day<=? and ordinal>? and vendor<>?
            order by day,ordinal limit 1''',(node['compact'],node['amount'],*state['after'],node['day']-3,node['day']+3,node['ordinal'],node['vendor'])).fetchone()
        if not row:return True
        other=self.scan._node(row);state['after']=(other['day'],other['ordinal']);self._pair(cur,other,'possible_wrong_vendor')
        return False
