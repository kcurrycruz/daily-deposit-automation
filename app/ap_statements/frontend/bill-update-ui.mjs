import {importBillSnapshot} from './bill-upload.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function billUpdateHTML(progress){
 const labels={preparing:'Preparing file',uploading:'Uploading',checking:'Checking records',saving:'Saving',done:'BILL data updated. Previous invoices were refreshed, not added again.',unchanged:'This BILL export is already current. No invoices were added.',cancelled:'Update cancelled. Your saved BILL data was not replaced.'};
 const count=Number.isSafeInteger(progress.sourceRowCount)?` · ${progress.sourceRowCount.toLocaleString()} source rows checked`:'';
 return `<section class="bill-update-progress" role="status" aria-live="polite"><strong>${esc(labels[progress.stage]||'Updating BILL data')}${count}</strong>${Number.isFinite(progress.fraction)?`<progress max="1" value="${Math.max(0,Math.min(1,progress.fraction))}" aria-label="${esc(labels[progress.stage])}"></progress>`:''}<p>${['done','unchanged','cancelled'].includes(progress.stage)?'Your statements and previous reviews are retained.':'Keep this tab open. Saved BILL data remains in use until the update is acknowledged.'}</p></section>`;
}
export function draftSourceHTML(detail,activeId){
 if(!detail?.importId||detail.importId===activeId||detail.completed||detail.readOnly)return '';
 return `<div class="notice blue"><div>This draft still uses ${esc(detail.importInfo?.metadata?.label||detail.importLabel||'its saved BILL export')}. <button class="button small" data-action="refresh-comparisons">Compare with current BILL data</button><small>Notes and corrections stay. Invoice decisions must be reviewed again.</small></div></div>`;
}
export function createBillUpdateUI({shared,client,hasUnsaved=()=>false,onProgress=()=>{},confirmRestore,confirmRestart,importer=importBillSnapshot}){
 let disposed=false,active=null;
 const check=()=>{if(disposed)throw Error('BILL update cancelled after leaving this page.');};
 async function update(file,{asOf=''}={}){
  check();if(active)throw Error('A BILL update is already in progress.');
  if(hasUnsaved())throw Error('Save your statement edits before updating BILL data.');
  if(shared.state.capabilities?.billSnapshots!==2)throw Error('This deployment needs the BILL snapshot migration before uploading a new export. Your saved data is still available.');
  const controller=new AbortController();active=controller;
  const progress=p=>{if(!disposed&&!controller.signal.aborted)onProgress(p);};
  async function execute(operation){
   if(active&&active!==controller)throw Error('A BILL update is already in progress.');
   check();if(hasUnsaved())throw Error('Save your statement edits before retrying the BILL update.');
   active=controller;
   try{const result=await operation();check();
    if(result.cancelled){progress({stage:'cancelled'});return result;}
    if(result.alreadyCurrent){progress({stage:'unchanged'});return result;}
    // Activation is authoritative; directory readback must also succeed before publication.
    try{await shared.adoptImport(result);}catch(error){error.retry=async()=>result;throw error;}
    check();progress({stage:'done'});return result;
   }catch(error){if(error.retry){const retry=error.retry;error.retry=()=>execute(retry);}throw error;}
   finally{active=null;}
  }
  return execute(()=>importer(client,file,{asOf,signal:controller.signal,onProgress:progress,confirmRestore,confirmRestart}));
 }
 return {update,dispose(){disposed=true;active?.abort();active=null;}};
}
