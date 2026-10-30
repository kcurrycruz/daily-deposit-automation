import {createBillRangeUI,rangeSummaryHTML} from './bill-range.mjs';
import {importBillSnapshot} from './bill-upload.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function billUpdateHTML(progress){
 const labels={range_preparing:'Preparing active BILL range',range_refreshing:'Refreshing saved follow-ups',range_prepared:'Review the active BILL range',preparing:'Preparing file',uploading:'Uploading',checking:'Checking records',saving:'Saving',done:'BILL data updated. Previous invoices were refreshed, not added again.',unchanged:'This BILL export is already current. No invoices were added.',current_changed:'BILL data changed in another session. The current saved export has been loaded.',cancelled:'Update cancelled. Your saved BILL data was not replaced.'};
 const count=Number.isSafeInteger(progress.sourceRowCount)?` · ${progress.sourceRowCount.toLocaleString()} source rows checked`:'';
 return `<section class="bill-update-progress" role="status" aria-live="polite"><strong>${esc(labels[progress.stage]||'Updating BILL data')}${count}</strong>${progress.manifest?rangeSummaryHTML(progress.manifest):''}${Number.isFinite(progress.fraction)?`<progress max="1" value="${Math.max(0,Math.min(1,progress.fraction))}" aria-label="${esc(labels[progress.stage])}"></progress>`:''}<p>${['done','unchanged','current_changed','cancelled'].includes(progress.stage)?'Your statements and previous reviews are retained.':'Keep this tab open. Saved BILL data remains in use until the update is acknowledged.'}</p></section>`;
}
export function draftSourceHTML(detail,activeId,scope){
 if(!activeId||detail?.completed||detail?.readOnly)return '';
 if(scope?.error)return '<div class="notice amber"><div>Current BILL comparison is unavailable. <button class="button small" data-action="refresh-comparisons">Retry comparison</button></div></div>';
 if(detail?.importId!==activeId||!scope?.complete||scope.importId!==activeId)return '<div class="notice blue" role="status"><div>Automatically updating comparisons with the latest BILL data… Your notes and corrections are retained.</div></div>';
 return `<div class="notice blue"><div>Compared with latest BILL data: ${esc(detail.importInfo?.metadata?.label||detail.importLabel||'saved export')}. Invoice presence does not verify payment settlement.</div></div>`;
}
export function createBillUpdateUI({shared,client,hasUnsaved=()=>false,onProgress=()=>{},confirmRestore,confirmRestart,confirmApply,importer=importBillSnapshot}){
 let disposed=false,active=null,ownRange=null;
 const check=()=>{if(disposed)throw Error('BILL update cancelled after leaving this page.');};
 async function update(file,{asOf='',mode='last_12_months'}={}){
  check();if(active)throw Error('A BILL update is already in progress.');
  if(hasUnsaved())throw Error('Save your statement edits before updating BILL data.');
  if(shared.state.capabilities?.billSnapshots!==2)throw Error('This deployment needs the BILL snapshot migration before uploading a new export. Your saved data is still available.');
  const controller=new AbortController();active=controller;
  const progress=p=>{if(!disposed&&!controller.signal.aborted)onProgress(p);};
  async function execute(operation,needsRange=true){
   let rangePending=needsRange;
   if(active&&active!==controller)throw Error('A BILL update is already in progress.');
   check();if(hasUnsaved())throw Error('Save your statement edits before retrying the BILL update.');
   active=controller;
   try{const result=await operation();check();
    if(result.cancelled){progress({stage:'cancelled'});return result;}
    if(shared.state.capabilities?.billWorkingSets===1){
     if(result.superseded)return result;
     if(!rangePending)return result;
     rangePending=false;
     const ranges=shared.ranges||(ownRange??=createBillRangeUI({client,shared,hasUnsaved,onProgress:progress,confirmApply,confirmRestart}));
     return await ranges.prepareUploaded(result,mode);
    }
    // Activation is authoritative; directory readback must also succeed before publication.
    let adopted;
    if(!result.alreadyCurrent||result.importId){try{adopted=await shared.adoptImport(result);}catch(error){error.retry=async()=>result;throw error;}}
    if(result.superseded||(adopted?.importId&&adopted.importId!==result.importId)){check();progress({stage:'current_changed'});return {...result,superseded:true};}
    check();progress({stage:result.alreadyCurrent?'unchanged':'done'});return result;
   }catch(error){if(error.retry){const retry=error.retry;error.retry=()=>execute(retry,rangePending);}if(error.cancel){const cancel=error.cancel;error.cancel=async()=>{const result=await cancel();progress({stage:'cancelled'});return result;};}throw error;}
   finally{active=null;}
  }
  return execute(()=>importer(client,file,{asOf,signal:controller.signal,onProgress:progress,confirmRestore,confirmRestart,prepareOnly:shared.state.capabilities?.billWorkingSets===1}));
 }
 return {update,dispose(){disposed=true;active?.abort();ownRange?.dispose();active=null;}};
}
