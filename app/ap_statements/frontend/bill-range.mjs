// Shared active coverage is prepared privately and published only after acknowledgement.
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const count=n=>Number.isSafeInteger(n)?n.toLocaleString('en-US'):'Unknown';
const reasons={recent:'Within date range',date_unknown:'Date unavailable',unsettled:'Unpaid or uncertain',follow_up:'Saved follow-up',non_invoice:'Credit or other activity',all:'All imported dates'};
export function rangeSelectorHTML(mode='last_12_months',{supported=true}={}){
 return `<div class="bill-range-controls"><label for="bill-range-mode">Active BILL data</label><select id="bill-range-mode" ${supported?'':'disabled'}><option value="last_12_months" ${mode==='last_12_months'?'selected':''}>Last 12 months</option><option value="all" ${mode==='all'?'selected':''}>All imported dates</option></select><small>${supported?'Older unpaid or uncertain bills and saved follow-ups stay active. The complete export remains saved.':'A database migration is needed to change the active date range.'}</small></div>`;
}
export function rangeSummaryHTML(mf){
 if(!mf)return '';
 return `<section class="bill-range-summary" aria-label="Prepared BILL range"><strong>${count(mf.activeCount)} active · ${count(mf.archivedCount)} archived · ${count(mf.fullRecordCount)} imported</strong>${mf.activeCount===0?"<p>No bills in this range. The full export is retained.</p>":""}<p>${mf.policy.mode==='all'?'All imported dates':`Invoice dates from ${esc(mf.policy.cutoffDate)} · prepared ${esc(mf.policy.asOfDate)}`}</p><ul>${Object.entries(mf.retainedReasonCounts||{}).map(([reason,n])=>`<li>${esc(reasons[reason]||reason)}: ${count(n)}</li>`).join('')}</ul><small>Reason counts can overlap. Archived bills are retained for exact-reference checks. Saved PDFs and previous reviews remain available.</small></section>`;
}
export function rangeCoverageText(mf){return mf?`${count(mf.activeCount)} of ${count(mf.fullRecordCount)} bills active · ${mf.policy.mode==='all'?'All imported dates':`From ${mf.policy.cutoffDate}, plus protected older bills`}`:'';}
const wait=(ms,signal)=>new Promise((resolve,reject)=>{const abort=()=>{clearTimeout(timer);reject(Error('BILL range update cancelled.'));};const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},ms);signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();});
export function createBillRangeUI({client,shared,hasUnsaved=()=>false,onProgress=()=>{},confirmApply=async()=>false,confirmRestart=async()=>false,delay=wait}){
 let disposed=false,active=null;
 const check=()=>{if(disposed||active?.signal.aborted)throw Error('BILL range update cancelled after leaving this page.');};
 const guard=()=>{check();if(hasUnsaved())throw Error('Save your statement edits before changing or refreshing BILL data.');if(shared.state.capabilities?.billWorkingSets!==1)throw Error('The active BILL range migration is required before changing this setting.');};
 async function run({mode,uploaded,refresh=false,current:given,adopt=true}){
  guard();if(active)throw Error('A BILL range update is already in progress.');
  const controller=new AbortController(),steps=new Map();let current=given,job=null,prepared=null,accepted=refresh;
  active=controller;
  const progress=p=>{if(!disposed&&!controller.signal.aborted)onProgress(p);};
  async function request(key,action,payload){
   check();let step=steps.get(key);
   if(!step){step={id:crypto.randomUUID(),action,payload};steps.set(key,step);}
   if(step.action!==action||JSON.stringify(step.payload)!==JSON.stringify(payload))throw Error('BILL range retry changed. Reload the current data.');
   if('reply' in step)return structuredClone(step.reply);
   for(let attempt=0;;attempt++){
    try{const reply=await client.request(action,payload,{requestId:step.id,signal:controller.signal});step.reply=structuredClone(reply);if(action==='bill_range_begin')job=reply;check();return reply;}
    catch(error){if(error.code!=='bill_range_loading'||attempt>=60)throw error;progress({stage:'range_preparing'});await delay(1000,controller.signal);}
   }
  }
  async function cancel(){
   if(job?.job_id)await client.request('bill_range_cancel',{job_id:job.job_id},{requestId:crypto.randomUUID()});
   if(uploaded?.job_id)await client.request('bill_cancel',{job_id:uploaded.job_id},{requestId:crypto.randomUUID()}).catch(()=>{});
   return {cancelled:true};
  }
  async function execute(){
   guard();if(active&&active!==controller)throw Error('A BILL range update is already in progress.');active=controller;
   try{
    current??=await request('current','bill_current',{include_working:true});
    if(refresh&&(!current.workingSet||current.protectionsCurrent!==false))return current;
    mode=refresh?current.workingSet.policy.mode:mode||'last_12_months';
    if(!['last_12_months','all'].includes(mode))throw Error('Choose an active BILL date range.');
    const source=uploaded?.importId||current.importId;if(!source)throw Error('Upload BILL data before applying a date range.');
    progress({stage:refresh?'range_refreshing':'range_preparing'});
    let p=await request('begin','bill_range_begin',{source_import_id:source,mode,expected_import_version:current.importVersion,expected_working_version:current.workingVersion??0,...(uploaded?.job_id?{upload_job_id:uploaded.job_id}:{}),...(refresh?{refresh:true}:{})});
    for(let turn=0;p.state!=='prepared';turn++){
     check();if(turn>=10000)throw Error('BILL range preparation did not finish. Retry the saved checkpoint.');
     if(!p.job_id||!p.generation||!Number.isSafeInteger(p.checkpoint))throw Error('BILL range checkpoint is incomplete.');
     let restart=false;if(p.state==='restart_required'){if(!await confirmRestart(p))return cancel();restart=true;}
     progress({stage:refresh?'range_refreshing':'range_preparing',...('recordsRead' in p?{recordsRead:p.recordsRead,activeCount:p.activeCount}:{})});
     const next=await request(`${restart?'restart':'step'}:${p.generation}:${p.checkpoint}`,'bill_range_step',{job_id:p.job_id,generation:p.generation,expected_checkpoint:p.checkpoint,...(restart?{restart:true}:{})});
     if(next.state!=='restart_required'&&!restart&&next.checkpoint<=p.checkpoint)throw Error('BILL range checkpoint did not advance.');
     p=next;await delay(10,controller.signal);
    }
    prepared=p;progress({stage:'range_prepared',manifest:p.manifest});
    if(!accepted){accepted=await confirmApply(p.manifest);check();if(!accepted)return cancel();}
    // A user may have edited another statement while the preview was open.
    guard();progress({stage:'saving'});
    const result=await request('activate','bill_range_activate',{job_id:p.job_id,expected_import_version:current.importVersion,expected_working_version:current.workingVersion??0});
    if(adopt){const adopted=await shared.adoptImport(result);check();if(adopted?.importId&&adopted.importId!==result.importId||adopted?.workingSet&&adopted.workingSet.workingSetId!==result.workingSet?.workingSetId)result.superseded=true;}
    progress({stage:result.superseded?'current_changed':'done'});return result;
   }catch(error){
    if(error.code==='bill_conflict'&&!disposed&&!controller.signal.aborted&&!hasUnsaved()&&current){
      const latest=await client.request('bill_current',{include_working:true},{signal:controller.signal});check();
      if(latest.protectionsCurrent!==false&&(latest.importId!==current.importId||latest.importVersion!==current.importVersion||(latest.workingVersion??0)!==(current.workingVersion??0))){
        await cancel().catch(()=>{});if(adopt)await shared.adoptImport(latest);check();progress({stage:'current_changed'});return {...latest,superseded:true};
      }
    }
    if(!disposed&&!controller.signal.aborted){error.retry=execute;if(prepared||job)error.cancel=cancel;}
    else if(job&&!steps.has('activate'))await cancel().catch(()=>{});
    throw error;
   }finally{if(active===controller)active=null;}
  }
  return execute();
 }
 return {applySaved:mode=>run({mode}),prepareUploaded:(uploaded,mode)=>run({uploaded,mode}),refreshProtections:options=>run({refresh:true,...options}),dispose(){disposed=true;active?.abort();}};
}
