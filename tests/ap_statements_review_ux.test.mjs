import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as history from '../app/ap_statements/frontend/history-browser.mjs';
import {uploadReviewHTML,statementOverviewHTML,vendorQuestionHTML} from '../app/ap_statements/frontend/simple-flow-view.mjs';
const pickerModule=await import('../app/ap_statements/frontend/vendor-picker.mjs').catch(()=>null);
const sourceModule=await import('../app/ap_statements/frontend/source-location.mjs').catch(()=>null);
const dropModule=await import('../app/ap_statements/frontend/statement-dropzone.mjs').catch(()=>null);
const app=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');

test('upload area is one keyboard-operable browse button with visible drag-drop instructions',()=>{
  const html=uploadReviewHTML({busy:false,errors:[]});
  assert.match(html,/<button[^>]*id="dropzone"[^>]*data-action="upload"/);
  assert.match(html,/aria-label="Add statements:/);
  assert.match(html,/Drag statement PDFs here/);assert.match(html,/Browse files/);
  assert.equal((html.match(/<button/g)||[]).length,1);
});
test('file dropping uses the same upload callback and never runs when busy',async()=>{
  assert.ok(dropModule,'The accessible drop target must exist');const handlers={},classes=new Set(),received=[];let allowed=true;
  const zone={addEventListener:(event,fn)=>handlers[event]=fn,contains:()=>false,classList:{add:v=>classes.add(v),remove:v=>classes.delete(v)}};
  dropModule.bindStatementDropzone(zone,{canUpload:()=>allowed,onFiles:async files=>received.push(files),onError:assert.fail});
  const files=[{name:'one.pdf'},{name:'two.pdf'}],event={preventDefault(){},dataTransfer:{files},relatedTarget:null};
  handlers.dragover(event);assert.equal(classes.has('dragging'),true);await handlers.drop(event);assert.equal(received[0],files);
  allowed=false;await handlers.drop(event);assert.equal(received.length,1);
});
test('vendor picker filters on input, supports arrow and Enter, and never saves a mapping',()=>{
  assert.ok(pickerModule,'The searchable vendor picker must exist');let saves=0;
  const picker=pickerModule.createVendorPicker(['Alpha Foods','Beta Produce','Alpha Dairy'],{onChange(){saves++;}});
  picker.input('alpha');assert.deepEqual(picker.matches(),['Alpha Dairy','Alpha Foods']);assert.equal(picker.state.selected,'');
  picker.key('ArrowDown');picker.key('Enter');assert.equal(picker.state.selected,'Alpha Dairy');
  assert.equal(picker.key('Escape'),false);picker.input('alpha');assert.equal(picker.key('Escape'),true);assert.equal(picker.key('Escape'),false);
  picker.input('no vendor');assert.deepEqual(picker.matches(),[]);assert.equal(picker.state.selected,'');
  assert.equal(picker.choose('Unlisted Vendor'),false);assert.ok(saves>0);
  const html=vendorQuestionHTML({vendor:'Unknown'}, {loaded:true,records:[{vendor:'Alpha Foods'}]},{});
  assert.match(html,/role="combobox"/);assert.match(html,/role="listbox"/);assert.match(html,/data-action="vendor-choose" disabled/);
});
test('vendor directory is a standalone view linking each vendor to their saved statements',()=>{
  assert.equal(typeof history.vendorDirectoryHTML,'function');
  const items=[{id:'1',vendor:'Alpha Foods'},{id:'2',vendor:'Alpha Foods'},{id:'3',vendor:'Beta'}];
  const html=history.vendorDirectoryHTML(items,'alpha');assert.match(html,/Alpha Foods/);assert.doesNotMatch(html,/>Beta</);assert.match(html,/data-action="vendor-history-open"/);assert.match(html,/2 saved reviews/);
});
test('every invoice row is clickable and keyboard reachable, not only its reference link',()=>{
  const row={id:'r',invoiceNumber:'271712',originalAmount:129981,status:'possible',preview:false};
  const html=statementOverviewHTML({confirmed:true,rows:[],declaredTotal:0},[row]);
  assert.match(html,/<tr[^>]*data-action="select-invoice"[^>]*data-id="r"[^>]*tabindex="0"/);
  assert.match(html,/<button[^>]*data-action="select-invoice"[^>]*>271712<\/button>/);
});
test('default attention selection opens its source page without resetting deliberate navigation',()=>{
  const block=app.slice(app.indexOf('if (row && !state.selectedRow)'),app.indexOf('const warnings = [...doc.warnings]'));
  const context={row:{id:'page-two',page:2},state:{selectedRow:null,page:1}};vm.runInNewContext(block,context);assert.equal(context.state.page,2);
  context.state.page=1;vm.runInNewContext(block,context);assert.equal(context.state.page,1);
});
function invoiceNavigation(){
  const focused=[],classes=new Set(),note={value:'Unsaved follow-up'};
  const drawer={scrollTop:620,classList:{toggle(name,on){on?classes.add(name):classes.delete(name);}}};
  const list={hidden:false},details={hidden:true,focus(){},scrollIntoView(){}},back={hidden:true},title={focus(){focused.push('detail');}},selected={focus(){focused.push('row');}};
  const nodes={'.drawer':drawer,'#invoice-list':list,'#invoice-details':details,'[data-invoice-back]':back,'#invoice-detail-title':title,'[data-action="select-invoice"][aria-current="true"]':selected};
  const context={action:'select-invoice',target:{dataset:{id:'r2'}},saveState:'saved',dirty:new Set(),state:{selected:'s',selectedRow:'r1',invoiceDetailsOpen:false},getDoc:()=>({}),comparisonsFor:()=>[{id:'r1',page:1},{id:'r2',page:2}],renders:0,
    renderDrawer(){context.renders++;note.value='';},overlay:{querySelector:s=>nodes[s]||null},document:{querySelector:s=>nodes[s]||null}};
  const start=app.indexOf('function showInvoicePage(');
  if(start>=0)vm.runInNewContext(app.slice(start,app.indexOf('function renderDrawer(',start)),context);
  const act=async action=>{context.action=action;await vm.runInNewContext('(async()=>{'+app.slice(app.indexOf("if(action==='select-invoice')"),app.indexOf("if(action==='refresh-comparisons')"))+'})()',context);};
  return {context,act,drawer,list,details,back,note,focused,classes};
}

test('an invoice opens a separate detail screen at the top with its source page and Back navigation',async()=>{
  const nav=invoiceNavigation();await nav.act('select-invoice');
  assert.equal(nav.context.state.page,2);assert.equal(nav.context.state.selectedRow,'r2');
  assert.equal(nav.context.state.invoiceListScroll,620);assert.equal(nav.drawer.scrollTop,0);
  assert.equal(nav.list.hidden,true);assert.equal(nav.details.hidden,false);assert.equal(nav.back.hidden,false);
  assert.equal(nav.classes.has('invoice-detail-page'),true);assert.deepEqual(nav.focused,['detail']);
});

test('Back restores list position and focus while preserving unsaved fields, including reopening that invoice',async()=>{
  const nav=invoiceNavigation();await nav.act('select-invoice');
  nav.context.dirty.add('s');nav.note.value='Unsaved follow-up';nav.drawer.scrollTop=850;
  await nav.act('back-invoices');
  assert.equal(nav.drawer.scrollTop,620);assert.equal(nav.list.hidden,false);assert.equal(nav.details.hidden,true);assert.equal(nav.back.hidden,true);
  assert.equal(nav.note.value,'Unsaved follow-up');assert.equal(nav.context.dirty.has('s'),true);
  nav.context.target.dataset.id='r2';await nav.act('select-invoice');
  assert.equal(nav.context.renders,1);assert.equal(nav.note.value,'Unsaved follow-up');
  assert.equal(nav.list.hidden,true);assert.equal(nav.details.hidden,false);assert.deepEqual(nav.focused,['detail','row','detail']);
});

test('another invoice cannot replace unsaved fields or interrupt a pending save',async()=>{
  const nav=invoiceNavigation();nav.context.dirty.add('s');
  await assert.rejects(nav.act('select-invoice'),/Save edits/);
  nav.context.dirty.clear();nav.context.saveState='saving';
  await assert.rejects(nav.act('select-invoice'),/save to finish/i);
  assert.equal(nav.context.renders,0);assert.equal(nav.context.state.selectedRow,'r1');assert.equal(nav.list.hidden,false);
});
test('reopening the same invoice returns to its source page after manual PDF navigation without dropping a note',async()=>{
  const nav=invoiceNavigation();await nav.act('select-invoice');await nav.act('back-invoices');
  nav.context.state.page=1;nav.context.dirty.add('s');nav.note.value='Keep this note';
  let previewPage=null;nav.context.previewPDF=()=>{previewPage=nav.context.state.page;};
  await nav.act('select-invoice');
  assert.equal(nav.context.state.page,2);assert.equal(previewPage,2);
  assert.equal(nav.note.value,'Keep this note');assert.equal(nav.context.renders,1);
});
test('PDF source locator highlights only a unique exact reference and amount, never suffixes or duplicate lines',()=>{
  assert.ok(sourceModule,'The source line locator must exist');
  const text=(str,x,y,width=70)=>({str,transform:[10,0,0,10,x,y],width,height:10});
  const items=[text('271712',40,400),text('$1,299.81',240,400),text('271712X',40,350),text('$1,299.81',240,350)];
  const hit=sourceModule.findSourceLine(items,{reference:'271712',amount:129981});
  assert.equal(hit.y,400);assert.equal(hit.text,'271712 $1,299.81');
  assert.equal(sourceModule.findSourceLine(items,{reference:'271712',amount:100}),null);
  assert.equal(sourceModule.findSourceLine([...items,text('271712',40,300),text('$1,299.81',240,300)],{reference:'271712',amount:129981}),null);
  assert.equal(sourceModule.findSourceLine([],{reference:'271712',amount:129981}),null);
  assert.equal(sourceModule.findSourceLine([text('271712',40,400),text('100.00',140,400),text('999999',340,400),text('1,299.81',440,400)],{reference:'271712',amount:129981}),null);
  assert.equal(sourceModule.findSourceLine([text('271712',40,400),text('1,299.81',140,400),text('999999',340,400),text('1,299.81',440,400)],{reference:'271712',amount:129981}),null);
});
test('a late old PDF render cannot overwrite the page selected more recently',async()=>{
  let release,started;const held=new Promise(resolve=>started=resolve),canvas={width:10,height:10,marker:'',getContext(){return {drawImage:buffer=>canvas.marker=buffer.marker};}};
  const context={renderToken:0,files:new Map([['s',new Blob(['synthetic'])]]),state:{page:1,drawerTab:'review'},comparisonsFor:()=>[],shared:{},
    document:{querySelector:s=>s==='#pdf-canvas'?canvas:null,createElement:()=>({width:0,height:0,marker:''})},
    extractor:{async renderPage(file,number,target){if(number===1){started();await new Promise(r=>release=r);}target.marker='page '+number;target.width=10;target.height=10;return null;}}};
  vm.runInNewContext(app.slice(app.indexOf('async function previewPDF('),app.indexOf('function collectRows(')),context);
  const first=context.previewPDF({id:'s'});await held;context.state.page=2;await context.previewPDF({id:'s'});release();await first;
  assert.equal(canvas.marker,'page 2');
});
test('save-state updates cannot enable vendor confirmation before a search result is chosen',()=>{
  const button={dataset:{action:'vendor-choose'},disabled:true},hidden={value:''};
  const context={state:{selected:null},saveState:'saving',sharedError:null,retryOperation:null,docDetail:()=>null,shared:{state:{ready:true}},overlay:{querySelectorAll:()=>[button]},document:{querySelector:s=>s==='#statement-bill-vendor'?hidden:null,querySelectorAll:()=>[]}};
  vm.runInNewContext(app.slice(app.indexOf('function sharedStatus('),app.indexOf('function receiveShared(')),context);
  context.sharedStatus('saved');assert.equal(button.disabled,true);
  hidden.value='Alpha Foods';context.sharedStatus('saved');assert.equal(button.disabled,false);
});
