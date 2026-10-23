import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
const app=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');

function reviewUI(){
 const canvas={page:'visible original'},drawer={scrollTop:420,contains:()=>false};
 const ui={canvas,drawer,previewStarts:0,sidebarUpdates:0};
 const context={state:{selected:'statement',provider:{},statements:[],mappings:{},resolutions:{}},dirty:new Set(),
  duplicateDrafts:{clear(){}},duplicateReturn:null,duplicateSaveAttempt:null,duplicateSourceKey:'',duplicateSearchTimer:null,duplicateSearchQuery:null,clearTimeout(){},
  overlay:{querySelector:s=>s==='.drawer'?drawer:null},document:{activeElement:null},
  render(){ui.sidebarUpdates++;},renderDuplicateUpdate(){ui.sidebarUpdates++;},renderDrawer(){ui.previewStarts++;canvas.page='Loading private original…';}};
 vm.runInNewContext(app.slice(app.indexOf('function receiveShared('),app.indexOf('async function startShared(')),context);
 return {ui,context};
}

test('background duplicate progress updates the sidebar without clearing an open statement preview',async()=>{
 const {ui,context}=reviewUI(),iid=crypto.randomUUID(),scan=crypto.randomUUID(),row=crypto.randomUUID();
 const doc={id:'statement',vendor:'Synthetic',confirmed:true,pageCount:1,warnings:[],rows:[{id:row,type:'invoice',invoiceNumber:'1001',amount:10000,page:1}]};
 const client={dispose(){},async request(action){
  if(action==='bootstrap')return {activeImport:{id:iid,metadata:{sourceFormat:'bill-native'}},importVersion:1,capabilities:{duplicateBills:1},mappings:{},statements:[{id:doc.id}],nextCursor:null};
  if(action==='statement')return {doc,version:1,completed:false,resolutions:{},results:[],importId:iid};
  if(action==='records_page')return {importId:iid,recordCount:1,records:[{id:iid+':0',vendor:'Synthetic',invoiceNumber:'1001',amount:10000}],nextCursor:null};
  if(action==='duplicate_ensure')return {scanId:scan,importId:iid,importVersion:1,state:'running',phase:'reading',canStep:false,checkpoint:1};
  throw Error('Unexpected action '+action);
 }};
 const workspace=createSharedWorkspace(client,{onState:(snapshot,change)=>context.receiveShared(snapshot,change)});context.shared=workspace;
 try{
  context.state.selected=null;await workspace.load();context.state.selected=doc.id;
  ui.previewStarts=0;ui.sidebarUpdates=0;ui.canvas.page='visible original';
  await workspace.duplicates.retry();
  assert.ok(ui.sidebarUpdates>=3,'loading, progress and completion notifications still update navigation');
  assert.equal(workspace.duplicates.state.phase,'running');
  assert.equal(ui.canvas.page,'visible original','duplicate progress must not replace the canvas with a loading panel');
  assert.equal(ui.previewStarts,0,'no additional original-PDF fetch/render is started');
  assert.equal(ui.drawer.scrollTop,420);
 }finally{workspace.dispose();}
});

test('real statement updates still refresh an open review after duplicate-only updates are isolated',()=>{
 const {ui,context}=reviewUI();context.shared={duplicates:{state:{phase:'ready',source:null}}};
 context.receiveShared({provider:{loaded:true},statements:[],mappings:{},resolutions:{}});
 assert.equal(ui.previewStarts,1);
});

test('a locked duplicate controller retains the existing review refresh path',()=>{
 const {ui,context}=reviewUI();context.shared={duplicates:{state:{phase:'locked',source:null}}};
 context.receiveShared({provider:{loaded:true},statements:[],mappings:{},resolutions:{}},{reason:'duplicates'});
 assert.equal(ui.previewStarts,1);
});
