"""Bounded historical vendor profiles. A format supports a warning, never a verdict."""
from datetime import date
import json
import re
from .contracts import encoded, DuplicateError


def reference_shape(reference):
    value=re.sub(r'\s+',' ',reference.strip().upper()).replace('\\','\\\\').replace('#','\\#')
    return re.sub('[0-9]','#',value)


def compact_reference(reference):
    return re.sub('[^A-Z0-9]','',reference.upper())


def month_start(day):
    value=date.fromordinal(day)
    return value.replace(day=1).toordinal()


def edit_kind(left,right):
    if left==right:return 'punctuation_or_spacing'
    if abs(len(left)-len(right))>1:return None
    if len(left)==len(right):
        differences=[i for i,(a,b) in enumerate(zip(left,right)) if a!=b]
        if len(differences)==1:return 'one_character_changed'
        if len(differences)==2:
            i,j=differences
            if j==i+1 and left[i]==right[j] and left[j]==right[i]:return 'adjacent_characters_swapped'
        return None
    short,long=(left,right) if len(left)<len(right) else (right,left)
    at=next((i for i,(a,b) in enumerate(zip(short,long)) if a!=b),len(short))
    return 'one_character_added_or_missing' if short[at:]==long[at+1:] else None


def _tokens(shape):
    tokens=[];escape=False
    for ch in shape:
        if escape:
            if ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':tokens.append(ch)
            escape=False
        elif ch=='\\':escape=True
        elif ch=='#':tokens.append('0123456789')
        elif ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':tokens.append(ch)
    return tokens


def reference_variants(reference,shapes):
    """Lazy, format-constrained edit search; never build a vendor-wide pair list."""
    base=compact_reference(reference);seen=set()
    for shape in sorted(shapes):
        target=_tokens(shape)
        if abs(len(target)-len(base))>1:continue
        def fits(value):return len(value)==len(target) and all(ch in choices for ch,choices in zip(value,target))
        def candidates():
            yield base
            if len(target)==len(base)-1:
                for at in range(len(base)):yield base[:at]+base[at+1:]
            elif len(target)==len(base)+1:
                for at in range(len(base)+1):
                    for ch in target[at]:yield base[:at]+ch+base[at:]
            else:
                for at,choices in enumerate(target):
                    for ch in choices:
                        if ch!=base[at]:yield base[:at]+ch+base[at+1:]
                for at in range(len(base)-1):yield base[:at]+base[at+1]+base[at]+base[at+2:]
        for value in candidates():
            if value not in seen and fits(value):
                seen.add(value);yield value


class VendorPatterns:
    def __init__(self,db):
        self.db=db;self.job=None;self.recurring=None
        db.executescript('''
          create index if not exists node_vendor_day on nodes(vendor,day,ordinal) where day is not null;
          create index if not exists node_vendor_amount_day on nodes(vendor,amount,day,ordinal) where day is not null;
          create table vendor_pattern_cache(vendor text,month integer,value text,primary key(vendor,month));
          create table vendor_pattern_refs(ref text primary key,shape text);
          create table vendor_pattern_shapes(shape text primary key,n integer);
          create index vendor_shape_support on vendor_pattern_shapes(n desc,shape);
          create table vendor_recurrence_cache(vendor text,amount integer,day integer,value integer,primary key(vendor,amount,day));
        ''')

    def advance(self,vendor,cutoff):
        cached=self.db.execute('select value from vendor_pattern_cache where vendor=? and month=?',(vendor,cutoff)).fetchone()
        if cached:return json.loads(cached[0])
        if month_start(cutoff)!=cutoff:raise DuplicateError('duplicate_invalid_source')
        if self.job is None:
            self.db.execute('delete from vendor_pattern_refs');self.db.execute('delete from vendor_pattern_shapes')
            self.job=dict(key=(vendor,cutoff),after=(cutoff-365,-1),n=0)
        job=self.job
        if job['key']!=(vendor,cutoff):raise DuplicateError('duplicate_restart')
        rows=self.db.execute('''select day,ordinal,ref,shape from nodes indexed by node_vendor_day
          where vendor=? and (day,ordinal)>(?,?) and day>=? and day<? and warning=0 and n=1
          order by day,ordinal limit 250''',(vendor,*job['after'],cutoff-365,cutoff)).fetchall()
        for day,ordinal,ref,shape in rows:
            previous=self.db.execute('select shape from vendor_pattern_refs where ref=?',(ref,)).fetchone()
            if not previous:
                job['n']+=1
                self.db.execute('insert into vendor_pattern_refs values(?,?)',(ref,shape))
            elif shape<previous[0]:
                self.db.execute('update vendor_pattern_shapes set n=n-1 where shape=?',(previous[0],))
                self.db.execute('update vendor_pattern_refs set shape=? where ref=?',(shape,ref))
            else:continue
            self.db.execute('insert into vendor_pattern_shapes values(?,1) on conflict(shape) do update set n=n+1',(shape,))
        if rows:job['after']=rows[-1][:2]
        if len(rows)==250:return None
        top=self.db.execute('select shape,n from vendor_pattern_shapes where n>=3 order by n desc,shape limit 3').fetchall()
        profile=dict(periodStart=date.fromordinal(max(1,cutoff-365)).isoformat(),periodEnd=date.fromordinal(max(1,cutoff-1)).isoformat(),
                     distinctReferences=job['n'],shapes=[dict(shape=s,references=n) for s,n in top],
                     established=job['n']>=20 and sum(n for _,n in top)*10>=job['n']*9)
        self.db.execute('insert into vendor_pattern_cache values(?,?,?)',(vendor,cutoff,encoded(profile)))
        self.job=None
        return profile

    def recurrence(self,vendor,amount,day):
        key=(vendor,amount,day)
        cached=self.db.execute('select value from vendor_recurrence_cache where vendor=? and amount=? and day=?',key).fetchone()
        if cached:return bool(cached[0])
        if self.recurring is None:self.recurring=dict(key=key,after=(day-90,-1),refs=set(),days=set())
        job=self.recurring
        if job['key']!=key:raise DuplicateError('duplicate_restart')
        rows=self.db.execute('''select day,ordinal,ref from nodes indexed by node_vendor_amount_day
          where vendor=? and amount=? and (day,ordinal)>(?,?) and day>=? and day<?
          order by day,ordinal limit 250''',(vendor,amount,*job['after'],day-90,day)).fetchall()
        for source_day,_,ref in rows:
            if len(job['refs'])<10:job['refs'].add(ref)
            if len(job['days'])<6:job['days'].add(source_day)
        positive=len(job['refs'])>=10 and len(job['days'])>=6
        if not positive and len(rows)==250:
            job['after']=rows[-1][:2];return None
        self.db.execute('insert into vendor_recurrence_cache values(?,?,?,?)',(*key,int(positive)))
        self.recurring=None
        return positive
