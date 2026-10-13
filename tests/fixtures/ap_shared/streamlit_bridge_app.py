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
        if action=='bootstrap':return {'activeImport':None,'statements':[],'mappings':{},'mappingVersions':{},'nextCursor':None}
        if action=='history_page':return {'items':[],'nextCursor':None}
        raise ValueError('Synthetic bridge check supports no file or finance mutation.')
render_ap_statements(st,config=config,service=SyntheticService(),limiter=Limiter())
