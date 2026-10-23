// Duplicate checking owns no source data, statement decisions, or bridge lifetime.
const defaultFilters=()=>({review:'unreviewed',classification:null,search:''});
export function createDuplicateBills(client,{onChange=()=>{},schedule=(fn,ms)=>setTimeout(fn,ms),cancelSchedule=clearTimeout}={}){
 const state={source:null,phase:'disabled',progress:null,page:null,selection:null,detail:null,error:null,
  filters:defaultFilters(),saveState:'idle',reviewRevision:null,loading:false};
 let disposed=false,busy=false,timer=null,token=0,listToken=0,selectionToken=0,pending=0,chain=Promise.resolve(),failed=null;
 const emit=()=>{if(!disposed)onChange(state);};
 const active=t=>!disposed&&t===token;
 function cancel(){if(timer!==null)cancelSchedule(timer);timer=null;}
 function clearEvidence(){state.progress=null;state.page=null;state.selection=null;state.detail=null;state.reviewRevision=null;state.error=null;state.saveState='idle';}
 function plan(){
  cancel();if(disposed||busy||pending||state.error||!state.source?.importId||state.source.capability!==1)return;
  const p=state.progress;
  if(p&&['failed','restart_required','superseded'].includes(p.state))return;
  if(p?.state==='ready'&&p.projectionReady&&state.page&&(!state.selection||state.detail))return;
  timer=schedule(()=>{timer=null;return tick();},p?.canStep===false?1000:10);
 }
 function enqueue(job){
  const t=token;pending++;cancel();
  const work=chain.catch(()=>{}).then(async()=>{
   if(!active(t))return null;
   state.loading=true;emit();
   try{const result=await job(t);return active(t)?result:null;}
   finally{if(active(t)){state.loading=false;emit();}}
  });
  chain=work;
  return work.finally(()=>{pending--;plan();});
 }
 function operation(action,payload,apply){
  const t=token,id=crypto.randomUUID();
  const execute=()=>enqueue(async current=>{
   if(current!==t)return null;
   try{
    const reply=await client.request(action,payload,{requestId:id});
    if(active(t)){state.error=null;failed=null;apply(reply);emit();}return reply;
   }catch(error){
    if(active(t)){
     if(error.code==='denied'){dispose();onChange(state);}
     else{state.error=error;failed=execute;emit();}
    }
    throw error;
   }
  });
  return execute();
 }
 function adoptProgress(p){
  if(p.importId&&p.importId!==state.source.importId||p.importVersion!==undefined&&p.importVersion!==state.source.importVersion)throw Error('Duplicate source changed. Refresh the workspace.');
  if(state.reviewRevision!==null&&p.reviewRevision!==null&&p.reviewRevision!==undefined&&state.reviewRevision!==p.reviewRevision){state.page=null;state.detail=null;}
  state.progress=p;state.reviewRevision=p.reviewRevision??state.reviewRevision;state.phase=p.state;
 }
 async function tick(){
  if(disposed||busy||pending)return;
  const p=state.progress;
  try{
   if(!p)await operation('duplicate_ensure',{import_id:state.source.importId,expected_import_version:state.source.importVersion},adoptProgress);
   else if(p.state==='ready'&&!p.projectionReady||p.canStep===false)await operation('duplicate_status',{scan_id:p.scanId},adoptProgress);
   else if(p.state==='ready'){if(state.selection&&!state.detail)await loadMembers();else await load();}
   else await operation('duplicate_step',{scan_id:p.scanId,generation:p.generation,expected_checkpoint:p.checkpoint,restart:false},adoptProgress);
  }catch{} // Detector-local failure; statements and acknowledged BILL saves stay usable.
 }
 function adoptSource(source){
  if(disposed)return;
  const next={importId:source.importId||null,importVersion:source.importVersion??0,capability:source.capability};
  if(JSON.stringify(next)===JSON.stringify(state.source))return;
  token++;listToken++;selectionToken++;cancel();failed=null;clearEvidence();state.source=next;
  state.phase=next.capability!==1?'disabled':next.importId?'pending':'no_source';emit();plan();
 }
 function setBusy(value){busy=!!value;if(busy)cancel();else plan();}
 function load({filters=state.filters,more=false}={}){
  if(disposed||!state.progress?.projectionReady)return Promise.resolve(null);
  const next={...defaultFilters(),...filters},changed=JSON.stringify(next)!==JSON.stringify(state.filters);
  if(changed){state.filters=next;state.page=null;more=false;}
  const lt=++listToken,cursor=more?state.page?.nextCursor:null,previous=more?state.page:null;
  return operation('duplicate_findings_page',{scan_id:state.progress.scanId,filters:next,cursor:cursor||null,limit:100},page=>{
   if(lt!==listToken)return;
   if(page.reviewRevision!==state.progress.reviewRevision)throw Error('Shared review changed. Refresh duplicate checks.');
   state.page={...page,findings:[...(previous?.findings||[]),...page.findings]};state.reviewRevision=page.reviewRevision;
  });
 }
 function open(key){
  state.selection=key;state.detail=null;state.saveState='idle';state.error=null;failed=null;selectionToken++;emit();return loadMembers();
 }
 function loadMembers({more=false}={}){
  if(!state.selection||!state.progress?.projectionReady)return Promise.resolve(null);
  const selected=state.selection,st=selectionToken,previous=more?state.detail:null;
  return operation('duplicate_members_page',{scan_id:state.progress.scanId,finding_key:selected,cursor:previous?.nextCursor||null,limit:100},page=>{
   if(st!==selectionToken||state.selection!==selected)return;
   if(page.reviewRevision!==state.progress.reviewRevision)throw Error('Shared review changed. Refresh duplicate checks.');
   state.detail={...page,members:[...(previous?.members||[]),...page.members]};emit();
  });
 }
 function save({decision,initials,note,expectedVersion}){
  if(!state.detail||!state.selection)return Promise.reject(Error('Open duplicate evidence before reviewing.'));
  const selected=state.selection;
  const payload={scan_id:state.progress.scanId,import_id:state.source.importId,expected_import_version:state.source.importVersion,
   finding_key:selected,expected_review_version:expectedVersion,decision,initials,note};
  state.saveState='saving';emit();
  return operation('duplicate_review_save',payload,ack=>{
   state.saveState=state.selection===selected?'saved':'idle';state.reviewRevision=ack.reviewRevision;state.page=null;
   if(state.selection===selected&&state.detail)state.detail.finding.review=ack.review;
   state.progress={...state.progress,projectionReady:false,reviewRevision:ack.reviewRevision,counts:null};
  }).catch(error=>{if(!disposed){state.saveState='not_saved';emit();}throw error;});
 }
 function retry(){
  if(disposed)return Promise.resolve(null);
  if(state.error?.code==='duplicate_conflict'){
   failed=null;state.error=null;state.page=null;state.detail=null;state.saveState='idle';
   return operation('duplicate_status',{scan_id:state.progress.scanId},adoptProgress);
  }
  if(failed){state.error=null;return failed();}
  const p=state.progress;
  if(p&&['failed','restart_required'].includes(p.state)){
   state.error=null;return operation('duplicate_step',{scan_id:p.scanId,generation:p.generation,expected_checkpoint:p.checkpoint,restart:true},adoptProgress);
  }
  state.error=null;state.page=null;
  return p?operation('duplicate_status',{scan_id:p.scanId},adoptProgress):tick();
 }
 function dispose(){
  token++;listToken++;selectionToken++;cancel();clearEvidence();state.source=null;state.phase='locked';failed=null;disposed=true;
 }
 return {state,adoptSource,setBusy,load,open,loadMembers,save,retry,dispose};
}
