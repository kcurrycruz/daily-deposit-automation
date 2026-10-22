import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');

test('pre-module startup uses the same circle-only loading screen',()=>{
  const html=readFileSync(new URL('../app/ap_statements/frontend/index.html',import.meta.url),'utf8');
  const startup=html.slice(html.indexOf('<div id="app">'),html.indexOf('<div id="overlay-root">'));
  assert.match(startup,/startup-spinner/);
  assert.match(startup,/role="status"/);
  assert.doesNotMatch(startup,/<h1|startup-card|eyebrow/);
});

test('startup renders only a busy screen, not empty metrics or missing BILL prompts',()=>{
  const app={innerHTML:'',querySelector:()=>null};
  const context={app,shared:undefined,sharedError:null,state:{view:'statements'},esc:String,backButtonHtml:()=>'',icon:()=>'',stats(){throw Error('Unloaded dashboard must not be evaluated');}};
  vm.runInNewContext(source.slice(source.indexOf('function render()'),source.indexOf('function guidePanel()')),context);
  assert.doesNotThrow(()=>context.render());assert.match(app.innerHTML,/aria-busy="true"/);assert.match(app.innerHTML,/Loading your AP workspace/);
  assert.doesNotMatch(app.innerHTML,/No BILL data|Add your BILL|Statements uploaded/);
  assert.doesNotMatch(app.innerHTML,/<h1|startup-card|brand-icon|<button/,'Loading uses only a circle and screen-reader status, not a card or menu.');
  context.sharedError=Error('offline');context.render();assert.match(app.innerHTML,/retry-shared/);assert.doesNotMatch(app.innerHTML,/aria-busy="true"/);
});

async function pendingFixture(){
  const id=crypto.randomUUID(),importId=crypto.randomUUID(),vendors=[{vendor:'Alpha'}];let release,started,fail=false;
  const held=new Promise(r=>started=r),wait=new Promise(r=>release=r);
  const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(vendors))))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const doc={id,vendor:'Alpha',filename:'synthetic.pdf',confirmed:true,rows:[{id:'r',invoiceNumber:'001',type:'invoice',amount:100,page:1,confidence:99}]};
  const states=[];
  const workspace=createSharedWorkspace({dispose(){},async request(action,payload){
    if(action==='bootstrap')return {activeImport:{id:importId,record_count:1,metadata:{}},capabilities:{billSnapshots:2},statements:[{id}],mappings:{},nextCursor:null};
    if(action==='statement')return {doc,importId,resolutions:{},version:1};
    if(action==='bill_vendors_page')return {importId,vendors,total:1,vendorDigest:digest,nextCursor:null};
    if(action==='bill_candidates_page'){started();await wait;if(fail)throw Error('Comparison unavailable');return {importId,records:[],total:0,queryDigest:'a'.repeat(64),afterOrdinal:-1,nextCursor:null};}
    throw Error(action);
  }},{onState:s=>states.push({ready:s.ready,complete:s.provider.scopes?.[id]?.complete})});
  return {workspace,states,held,release,fail(){fail=true;},recover(){fail=false;}};
}

test('workspace becomes ready only after all initial invoice comparisons finish',async()=>{
  const f=await pendingFixture(),loading=f.workspace.load();await f.held;
  assert.equal(f.workspace.state.ready,false);assert.ok(f.states.every(s=>!s.ready));
  f.release();await loading;assert.equal(f.workspace.state.ready,true);assert.equal(f.states.at(-1).complete,true);f.workspace.dispose();
});

test('initial comparison failure remains behind retry screen and can recover',async()=>{
  const f=await pendingFixture();f.fail();const loading=f.workspace.load();await f.held;f.release();
  await assert.rejects(loading,/unavailable/i);assert.equal(f.workspace.state.ready,false);
  f.recover();await f.workspace.load();assert.equal(f.workspace.state.ready,true);f.workspace.dispose();
});
