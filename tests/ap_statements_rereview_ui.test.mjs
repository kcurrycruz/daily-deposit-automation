import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import * as manual from '../app/ap_statements/frontend/manual-review.mjs';
import {historyView} from '../app/ap_statements/frontend/history.mjs';
import {historyBrowserHTML} from '../app/ap_statements/frontend/history-browser.mjs';
import {statementOverviewHTML,billDataHTML} from '../app/ap_statements/frontend/simple-flow-view.mjs';
import {toCSV,statuses} from '../app/ap_statements/frontend/core.mjs';
import {invoiceResult} from '../app/ap_statements/frontend/reference-review.mjs';
const app=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
const item={id:'event',statementId:'s',revisionId:'old',vendor:'Alpha',filename:'old.pdf',statementDate:'2026-10-01',initials:'KC',status:'reviewed',completedAt:'2026-10-01T12:00:00Z'};
const doc={id:'s',vendor:'Alpha',reviewMode:'manual',confirmed:true,pageCount:1,rows:[{id:'r',invoiceNumber:'00042',type:'invoice',amount:13800,page:1,confidence:99}]};
const row={id:'r',vendor:'Alpha',invoiceNumber:'00042',kind:'invoice',originalAmount:13800,status:'missing',candidates:[],activity:[]};
const saved=()=>{const resolution=manual.createManualCheck(doc,row,{initials:'KC',decision:'Reviewed — no action needed',note:'Verified in BILL'});resolution.at='2026-10-23T15:00:00Z';resolution.manualCheck.checkedAt=resolution.at;return resolution;};

test('all-history and vendor history offer capability-gated re-review without replacing View revision',()=>{
 for(const html of [historyView({items:[item]},'desc',{canRereview:true}),historyBrowserHTML([item],{vendor:'Alpha'},50,{canRereview:true})]){
  assert.match(html,/data-action="history-rereview" data-event="event"/);assert.match(html,/View revision/);assert.match(html,/Quick preview/);
 }
 assert.doesNotMatch(historyView({items:[item]}),/data-action="history-rereview"/);
});

test('mode choice defaults to latest and explains starting from the latest revision without replacing history',()=>{
 assert.equal(typeof manual.rereviewChoiceHTML,'function');const html=manual.rereviewChoiceHTML('Alpha <Foods>');
 assert.match(html,/Alpha &lt;Foods&gt;/);assert.match(html,/value="latest" checked/);assert.match(html,/value="manual"/);
 assert.match(html,/latest revision/i);assert.match(html,/previous reviews.*unchanged/i);
});

test('manual controls require an explicit checkbox and initials; saved label is read-only evidence',()=>{
 assert.equal(typeof manual.manualCheckHTML,'function');const html=manual.manualCheckHTML(row,null);
 assert.match(html,/id="review-manual-check"/);assert.match(html,/id="review-manual-initials"/);assert.match(html,/self-reported/);
 const historical=manual.manualCheckHTML(row,saved(),true);
 assert.match(historical,/Checked manually in BILL/);assert.match(historical,/KC/);assert.doesNotMatch(historical,/<input/);
 const marked=statementOverviewHTML(doc,[row],false,{r:saved()});
 assert.match(marked,/0 found in BILL/);assert.match(marked,/badge green">Checked manually in BILL/);
 const follow={...saved(),decision:'Follow up with vendor'};
 assert.match(statementOverviewHTML(doc,[row],false,{r:follow}),/badge amber">Checked manually in BILL/);
});

test('manual extraction has no editable financial inputs but exposes the original values and explicit recheck',()=>{
 assert.equal(typeof manual.manualExtractionHTML,'function');const html=manual.manualExtractionHTML(doc);
 assert.match(html,/00042/);assert.match(html,/138\.00/);assert.match(html,/manual-recheck/);
 assert.doesNotMatch(html,/<input|save-extraction|confirm-extraction|delete-row|add-row/);
});

test('manual report columns retain method, initials and acknowledged time without claiming settlement',()=>{
 assert.equal(typeof manual.manualReviewReport,'function');
 assert.deepEqual(manual.manualReviewReport(row,saved()),['Checked manually in BILL','KC','2026-10-23T15:00:00Z']);
 assert.deepEqual(manual.manualReviewReport(row,{...saved(),at:undefined}),['','','']);
});

test('manual resolve action saves explicit bound proof through the normal save path and can clear it',async()=>{
 const start=app.indexOf("if (action === 'resolve')"),end=app.indexOf("if (action === 'reopen')",start),writes=[];
 const fields={'#review-decision':{value:'Reviewed — no action needed'},'#review-note':{value:'Checked now'},'#review-manual-check':{checked:true},'#review-manual-initials':{value:' kc '}};
 const context={...manual,action:'resolve',state:{selectedRow:'r',resolutions:{}},getDoc:()=>doc,comparisonsFor:()=>[row],
  document:{querySelector:s=>fields[s]||null},persistDoc:async()=>writes.push(structuredClone(context.state.resolutions.r)),render(){},renderDrawer(){},toast(){}};
 await vm.runInNewContext('(async()=>{'+app.slice(start,end)+'})()',context);
 assert.equal(writes[0].manualCheck.initials,'KC');assert.equal(writes[0].manualCheck.reference,'00042');assert.equal(writes[0].at,undefined);
 fields['#review-manual-check'].checked=false;
 await vm.runInNewContext('(async()=>{'+app.slice(start,end)+'})()',context);
 assert.equal(writes[1].manualCheck,undefined);assert.equal(writes[1].note,'Checked now');
});

test('re-review entry reuses a dirty local draft rather than fetching or reopening a historical snapshot',async()=>{
 assert.ok(app.includes('async function beginRereview('),'A safe re-review entry point must exist');
 let opened=0;const local={...doc,notes:'Unsaved draft note'};
 const context={state:{selected:'s',statements:[local]},dirty:new Set(['s']),shared:{state:{capabilities:{statementRereview:1},details:new Map([['s',{doc:local,completed:false}]])}},
  ready(){},closeQuickPreview(){},openDoc:id=>{assert.equal(id,'s');opened++;},toast(){},historicalDetail:{doc:{id:'s'}},historySelection:item,pendingRereview:null};
 vm.runInNewContext(app.slice(app.indexOf('async function beginRereview('),app.indexOf('function closeOverlay(')),context);
 await context.beginRereview('s');assert.equal(opened,1);assert.equal(local.notes,'Unsaved draft note');
});

test('global save carries unchanged manual provenance instead of asserting another fresh check',async()=>{
 const start=app.indexOf("if (action === 'save-session')"),end=app.indexOf("if (action === 'disconnect')",start),writes=[],prior=saved();
 const fields={'#review-decision':{value:prior.decision},'#review-note':{value:'Only notes changed'},'#review-manual-check':{checked:true},'#review-manual-initials':{value:'KC'}};
 const context={...manual,action:'save-session',state:{selected:'s',selectedRow:'r',drawerTab:'review',statements:[doc],resolutions:{r:prior}},getDoc:()=>doc,comparisonsFor:()=>[row],ready(){},
  document:{querySelector:s=>fields[s]||null},persistDoc:async()=>writes.push(structuredClone(context.state.resolutions.r)),render(){},renderDrawer(){},toast(){}};
 await vm.runInNewContext('(async()=>{'+app.slice(start,end)+'})()',context);
 assert.equal(writes[0].manualCheck.checkedAt,prior.manualCheck.checkedAt);assert.equal(writes[0].note,'Only notes changed');
});

test('unavailable current source offers a working retry that cannot discard dirty manual drafts',async()=>{
 const html=billDataHTML({loaded:false,label:'Current.csv',error:'offline'});
 assert.match(html,/temporarily unavailable/);assert.doesNotMatch(html,/Add your BILL data once/);assert.match(html,/data-action="retry-bill-source"/);
 const start=app.indexOf("if(action==='retry-bill-source')"),end=app.indexOf("if(action==='refresh-comparisons')",start);assert.ok(start>=0);
 const calls=[],context={action:'retry-bill-source',dirty:new Set(['s']),shared:{load:async options=>calls.push(options)},state:{selected:null},render(){},renderDrawer(){},toast(){}};
 const run=()=>vm.runInNewContext('(async()=>{'+app.slice(start,end)+'})()',context);
 await assert.rejects(run(),/save your edits/i);assert.equal(calls.length,0);context.dirty.clear();await run();assert.equal(calls[0].replace,true);
});

test('read-only historical manual revisions cannot trigger a latest-data recheck',()=>{
 const start=app.indexOf('if(state.selected&&docDetail(state.selected)?.readOnly'),end=app.indexOf("if(action==='history-view')",start);
 const context={action:'manual-recheck',state:{selected:'s'},docDetail:()=>({readOnly:true}),getDoc:()=>doc,...manual};
 assert.throws(()=>vm.runInNewContext(app.slice(start,end),context),/read-only/i);
});

test('a local draft arriving during the initial history read cannot be overwritten',async()=>{
 let release,started,adoptions=0;const pending=new Promise(resolve=>started=resolve);
 const state={selected:null,statements:[]},details=new Map();
 const context={state,dirty:new Set(),ready(){},...manual,shared:{state:{capabilities:{statementRereview:1},details},
  async statement(){started();return new Promise(resolve=>release=resolve);},adopt(detail){adoptions++;state.statements=[detail.doc];}},
  closeQuickPreview(){},receiveShared(){},openDoc(){},toast(){},historicalDetail:null,historySelection:null,pendingRereview:null};
 vm.runInNewContext(app.slice(app.indexOf('async function beginRereview('),app.indexOf('function closeOverlay(')),context);
 const work=context.beginRereview('s');await pending;
 const local={...doc,notes:'New local note'};state.statements=[local];details.set('s',{doc:local,completed:false});
 release({doc:{...doc,notes:'Stale readback'},completed:false});await work;
 assert.equal(adoptions,0);assert.equal(state.statements[0].notes,'New local note');
});

test('history mode selection forwards latest or manual and never selects an old revision to overwrite',async()=>{
 for(const mode of ['latest','manual']){
  const attempt={id:'s',version:7},calls=[],context={action:'start-rereview',pendingRereview:attempt,state:{view:'history'},historicalDetail:{},historySelection:item,
   document:{querySelector:()=>({value:mode})},shared:{async reopenStatement(...args){calls.push(args);}},openDoc:id=>calls.push(['open',id]),toast(){}};
  const start=app.indexOf("if(action==='start-rereview')"),end=app.indexOf("if(action==='vendor-confirm'",start);
  await vm.runInNewContext('(async()=>{'+app.slice(start,end)+'})()',context);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])),['s',7,{mode}]);assert.deepEqual(calls[1],['open','s']);assert.equal(context.historicalDetail,null);
 }
});

test('financial edit actions fail in manual mode while decisions and notes remain available',()=>{
 for(const action of ['add-row','delete-row','vendor-confirm','save-extraction','confirm-extraction','confirm-reading','attach-original'])assert.throws(()=>manual.assertManualFinancialAction(doc,action),/latest BILL data/);
 for(const action of ['resolve','save-notes','reopen','complete-dialog'])assert.doesNotThrow(()=>manual.assertManualFinancialAction(doc,action));
});

test('actual CSV action includes pinned source and original status alongside saved manual method metadata',async()=>{
 let csv;const resolution=saved(),detail={doc,readOnly:false,importLabel:'Old.csv',importId:'old-import',ruleVersion:'ap-match-v3'};
 const context={action:'export',...manual,invoiceResult,statuses,toCSV,MATCH_RULE_VERSION:'ap-match-v4',historicalDetail:null,historySelection:null,
  state:{selected:'s',statements:[doc],provider:{label:'New.csv'},resolutions:{r:resolution}},docDetail:()=>detail,getDoc:()=>doc,reviewDecision:()=>resolution,
  results:()=>[{...row,statementId:'s'}],download:(name,text)=>csv=text,toast(){}};
 const start=app.indexOf("if (action === 'export')"),end=app.indexOf('\n  } catch(error)',start);
 await vm.runInNewContext('(async()=>{'+app.slice(start,end)+'})()',context);
 assert.match(csv,/"reviewMethod","manualReviewerInitials","manualCheckedAtUTC"/);assert.match(csv,/Old\.csv/);assert.match(csv,/ap-match-v3/);
 assert.match(csv,/Not found/);assert.match(csv,/"Checked manually in BILL","KC","2026-10-23T15:00:00Z"/);
});
