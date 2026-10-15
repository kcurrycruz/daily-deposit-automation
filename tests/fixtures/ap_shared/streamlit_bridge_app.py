"""Real Streamlit component bridge with a synthetic service, never Supabase."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from datetime import datetime,timezone
import streamlit as st
from app.ap_shared.models import ApConfig
from app.ap_shared.access import attempt_unlock
from app.ap_statements_ui import render_ap_statements

st.set_page_config(page_title='Synthetic AP bridge QA',layout='wide')
config=ApConfig('SYNTHETIC-ONLY-PASSWORD','https://synthetic.supabase.co','SYNTHETIC-ONLY-SERVER-KEY','00000000-0000-4000-8000-000000000001','hwfc-ap-private')
class Limiter:
    def begin_attempt(self,*args):return 'synthetic'
    def finish_attempt(self,*args):return True
if not st.session_state.get('_ap_qa_initialized'):
    attempt_unlock(st.session_state,config.password,config,Limiter(),datetime.now(timezone.utc))
    st.session_state['_ap_qa_initialized']=True
class SyntheticService:
    clock=staticmethod(lambda:datetime.now(timezone.utc))
    def handle(self,action,payload,request_id,authorization):
        if st.query_params.get('fail_once')=='1' and not st.session_state.get('_ap_qa_failed_once'):
            st.session_state['_ap_qa_failed_once']=True
            from app.ap_shared.repository import ApStoreError
            raise ApStoreError('unavailable')
        if st.query_params.get('layout')=='1':
            import_id='00000000-0000-4000-8000-000000000010'
            documents=[{
                'id':f'00000000-0000-4000-8000-{index+20:012d}',
                'vendor':'Synthetic Layout Supplier','filename':f'Layout statement {index+1}.pdf',
                'layout':'generic','statementDate':'2026-10-01','declaredTotal':10000,
                'confirmed':True,'pageCount':1,'warnings':[],'notes':'Synthetic layout QA only',
                'rows':[{'id':f'00000000-0000-4000-8000-{index+30:012d}',
                         'invoiceNumber':f'QA-{index+1:03d}','type':'invoice',
                         'amount':10000,'balance':10000,'page':1,'confidence':99}]
            } for index in range(3)]
            records=[{'id':f'{import_id}:{index}','vendor':doc['vendor'],
                      'invoiceNumber':doc['rows'][0]['invoiceNumber'],'amount':10000,
                      'kind':'invoice','comparisonScope':'invoice-only','status':'Open','currency':'USD'}
                     for index,doc in enumerate(documents)]
            if action=='bootstrap':
                return {'activeImport':{'id':import_id,'metadata':{
                    'label':'synthetic-layout-bills.csv','sourceFormat':'bill-native',
                    'refreshedAt':datetime.now(timezone.utc).isoformat()}},
                    'statements':[{'id':doc['id']} for doc in documents],
                    'mappings':{},'mappingVersions':{},'nextCursor':None}
            if action=='records_page':
                return {'records':records,'importId':import_id,'recordCount':3,'nextCursor':None}
            if action=='statement':
                doc=next(doc for doc in documents if doc['id']==payload['statement_id'])
                return {'doc':doc,'version':1,'resolutions':{},'results':[],
                        'importId':import_id,'mappingSnapshot':{},'ruleVersion':'ap-match-v3',
                        'originalAvailable':False,'completed':False,'archived':False}
        if action=='bootstrap':return {'activeImport':None,'statements':[],'mappings':{},'mappingVersions':{},'nextCursor':None}
        if action=='history_page':return {'items':[],'nextCursor':None}
        raise ValueError('Synthetic bridge check supports no file or finance mutation.')
render_ap_statements(st,config=config,service=SyntheticService(),limiter=Limiter())
