import test from 'node:test';
import assert from 'node:assert/strict';
import {createBillUpdateUI, billUpdateHTML, draftSourceHTML} from '../app/ap_statements/frontend/bill-update-ui.mjs';

function setup(extra={}){
 const events=[],history={results:[{id:'frozen',status:'match'}]},frozen=structuredClone(history.results);
 const shared={state:{capabilities:{billSnapshots:2},provider:{label:'Old export',recordCount:5610}},async adoptImport(r){this.state.provider={label:r.metadata.label,recordCount:r.recordCount};}};
 const ui=createBillUpdateUI({shared,client:{},hasUnsaved:()=>false,onProgress:p=>events.push(p),...extra});
 return {ui,shared,events,history,frozen};
}
test('update publishes authoritative count only after activation and retains frozen history',async()=>{
 let finish;const f=setup({importer:async(c,file,o)=>{for(const stage of ['preparing','uploading','checking','saving'])o.onProgress({stage});await new Promise(r=>finish=r);return {importId:'new',recordCount:223425,metadata:{label:'Weekly export'}};}});
 const promise=f.ui.update({name:'weekly.csv'});assert.equal(f.shared.state.provider.label,'Old export');finish();
 const result=await promise;assert.equal(result.recordCount,223425);assert.equal(f.shared.state.provider.recordCount,223425);assert.deepEqual(f.history.results,f.frozen);
 assert.deepEqual(f.events.map(e=>e.stage),['preparing','uploading','checking','saving','done']);
 for(const stage of ['preparing','uploading','checking','saving'])assert.match(billUpdateHTML({stage}),/role="status"/);
 assert.match(billUpdateHTML({stage:'done'}),/Previous invoices were refreshed, not added again/);
});
test('dirty drafts and missing capability block import without changing saved data',async()=>{
 let calls=0;const f=setup({hasUnsaved:()=>true,importer:()=>calls++});await assert.rejects(f.ui.update({}),/Save.*edits/i);assert.equal(calls,0);
 const g=setup({importer:()=>calls++});g.shared.state.capabilities={};await assert.rejects(g.ui.update({}),/deployment/i);assert.equal(calls,0);assert.equal(g.shared.state.provider.recordCount,5610);
});
test('failure retains the old label and retries the same upload operation',async()=>{
 let imports=0,retries=0;const f=setup({importer:async()=>{imports++;const e=Error('Connection interrupted');e.retry=async()=>{retries++;return {importId:'new',recordCount:223425,metadata:{label:'Weekly'}};};throw e;}});
 let failure;try{await f.ui.update({});}catch(e){failure=e;}
 assert.equal(f.shared.state.provider.label,'Old export');await failure.retry();assert.equal(imports,1);assert.equal(retries,1);assert.equal(f.shared.state.provider.recordCount,223425);
});
test('duplicate current is a no-op and old restore/restart prompts are explicit callbacks',async()=>{
 let prompt=0;const f=setup({confirmRestore:async()=>{prompt++;return false;},confirmRestart:async()=>{prompt++;return false;},importer:async(c,file,o)=>{assert.equal(await o.confirmRestore({}),false);assert.equal(await o.confirmRestart({}),false);return {duplicate:true,alreadyCurrent:true};}});
 await f.ui.update({});assert.equal(prompt,2);assert.equal(f.shared.state.provider.recordCount,5610);assert.equal(f.events.at(-1).stage,'unchanged');
});
test('navigation aborts work and ignores late worker or server completion',async()=>{
 let release,signal;const f=setup({importer:async(c,file,o)=>{signal=o.signal;await new Promise(r=>release=r);o.onProgress({stage:'saving'});return {importId:'new',metadata:{label:'Late'},recordCount:223425};}});
 const pending=f.ui.update({});f.ui.dispose();release();await assert.rejects(pending,/cancelled/i);assert.equal(signal.aborted,true);assert.equal(f.shared.state.provider.label,'Old export');assert.equal(f.events.length,0);
});
test('older drafts expose an explicit compare action but completed revisions stay frozen',()=>{
 assert.match(draftSourceHTML({importId:'old',importLabel:'Prior export'},'new'),/refresh-comparisons/);
 assert.doesNotMatch(draftSourceHTML({importId:'old',completed:true},'new'),/refresh-comparisons/);
 assert.doesNotMatch(draftSourceHTML({importId:'new'},'new'),/refresh-comparisons/);
});
