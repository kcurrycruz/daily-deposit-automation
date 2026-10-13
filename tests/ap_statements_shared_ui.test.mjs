import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
test('save acknowledgements re-enable controls disabled during a shared write',()=>{
  const button={disabled:true};const context={docDetail:()=>null,saveState:'saving',sharedError:null,retryOperation:null,shared:{state:{ready:true,details:new Map()}},state:{selected:null},overlay:{querySelectorAll:()=>[]},document:{querySelector:()=>null,querySelectorAll:()=>[button]}};
  vm.runInNewContext(source.slice(source.indexOf('function sharedStatus('),source.indexOf('function receiveShared(')),context);
  context.sharedStatus('saved');assert.equal(button.disabled,false);context.sharedStatus('saving');assert.equal(button.disabled,true);
});
test('shared UI decoration does not duplicate navigation and save status on errors',()=>{
  let navAdds=0,statusAdds=0;const nav={querySelector:()=>navAdds?{}:null,insertAdjacentHTML(){navAdds++;}},actions={insertAdjacentHTML(){statusAdds++;}};
  const context={saveState:'saved',sharedError:null,shared:{state:{ready:true}},state:{view:'statements',statements:[]},icon:()=>'',esc:String,
    document:{querySelector:selector=>selector==='.nav'?nav:selector==='.top-actions'?actions:selector==='#shared-save-status'&&statusAdds?{}:null,querySelectorAll:()=>[]}};
  vm.runInNewContext(source.slice(source.indexOf('function decorateSharedUi('),source.indexOf('function historyPanel(')),context);
  context.decorateSharedUi();context.decorateSharedUi();assert.equal(navAdds,1);assert.equal(statusAdds,1);
});
test('startup retry assembles the entire workspace rather than returning a raw bootstrap reply',async()=>{
  let fail=true;const client={};const workspace={state:{ready:false},async load(){if(fail)throw Object.assign(Error('offline'),{retry:async()=>({activeImport:null})});this.state.ready=true;return this.state;}};
  const context={shared:null,window:{hwfcSharedClient:client},createSharedWorkspace:()=>workspace,receiveShared(){},sharedError:null,retryOperation:null,render(){},sharedStatus(status,error){context.status=status;context.retryOperation=error?.retry||null;}};
  vm.runInNewContext(source.slice(source.indexOf('async function startShared('),source.indexOf("window.addEventListener('hwfc:shared-ready'")),context);
  await context.startShared();fail=false;await context.retryOperation();assert.equal(workspace.state.ready,true);assert.equal(context.status,'saved');
});
test('opening an old completion does not substitute current draft fields or change draft decisions',async()=>{
  const id=crypto.randomUUID(),draft={id,vendor:'Edited vendor',notes:'Unsaved draft notes'},frozen={id,vendor:'Old vendor',notes:'Old completed notes'};
  const details=new Map([[id,{doc:draft,version:8}]]),current={note:'Draft review',decision:'Follow up with vendor'};
  const context={historicalDetail:null,historySelection:null,historyPage:{items:[{id:'event',statementId:id,revisionId:'revision'}]},state:{selected:id,statements:[draft],resolutions:{r:current}},shared:{state:{details},statement:async()=>({doc:frozen,resolutions:{r:{decision:'Reviewed — no action needed'}},results:[],readOnly:true})},target:{dataset:{event:'event'}},action:'history-open',openDoc(){}};
  const action=source.slice(source.indexOf("if(action==='history-open')"),source.indexOf("if(action==='complete-dialog')"));
  await vm.runInNewContext('(async()=>{'+action+'})()',context);
  vm.runInNewContext(source.slice(source.indexOf('function getDoc('),source.indexOf('function openDoc(')),context);
  assert.equal(context.getDoc().vendor,'Old vendor');assert.equal(context.getDoc().notes,'Old completed notes');assert.equal(details.get(id).doc,draft);assert.equal(context.state.resolutions.r,current);
});
test('export of a selected historical revision uses only that revision evidence and notes',()=>{
  const doc={id:'s',vendor:'Old vendor',filename:'old.pdf',statementDate:'2026-09-01',notes:'Old notes'},row={id:'r',statementId:'s',vendor:'Old vendor',invoiceNumber:'001',kind:'invoice',originalAmount:18400,outstanding:18400,status:'possible',reason:'Old reason'};
  const detail={doc,results:[row],resolutions:{r:{decision:'Reviewed — no action needed',note:'Old review note'}},readOnly:true,importId:'old-import',importLabel:'old.csv',ruleVersion:'ap-match-v2'};
  let exported;const context={state:{selected:'s',statements:[{...doc,filename:'new.pdf'}],resolutions:{r:{note:'New draft note'}},provider:{label:'new.csv'}},shared:{state:{details:new Map([['s',{doc:{...doc,filename:'new.pdf'},readOnly:false}]])}},historicalDetail:detail,historySelection:{initials:'KC',completedAt:'2026-09-01T12:00:00Z'},docDetail:()=>detail,getDoc:()=>doc,comparisonsFor:()=>[row],results:()=>[],reviewDecision:()=>detail.resolutions.r,statuses:{possible:{label:'Possible match'}},toCSV:rows=>rows,download:(name,rows)=>{exported=rows;},toast(){},action:'export'};
  vm.runInNewContext(source.slice(source.indexOf("if (action === 'export')"),source.indexOf('} catch(error)',source.indexOf("if (action === 'export')"))),context);
  assert.ok(exported[1]);assert.ok(exported[1].includes('old.pdf'));assert.ok(exported[1].includes('Old review note'));assert.ok(exported[1].includes('old-import'));assert.ok(!JSON.stringify(exported).includes('new.pdf'));
});
