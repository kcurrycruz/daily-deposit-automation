import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');

function watchdogFixture(){
 const timers=new Map(),events=new Map();let reloads=0,mode='loading';
 const button={addEventListener(type,fn){this[type]=fn;}};
 const app={innerHTML:'',querySelector:selector=>selector==='#ap-startup-reload'?button:mode==='loading'?{}:null};
 const window={location:{reload(){reloads++;}},addEventListener:(name,fn)=>events.set(name,fn)};
 const context={window,document:{querySelector:()=>app},setTimeout(fn,ms){timers.set(1,{fn,ms});return 1;},clearTimeout(id){timers.delete(id);}};
 const path=new URL('../app/ap_statements/frontend/startup-watchdog.js',import.meta.url);
 try{vm.runInNewContext(readFileSync(path,'utf8'),context);}catch(error){if(error.code!=='ENOENT')throw error;}
 return {window,timers,events,app,button,get reloads(){return reloads;},set mode(value){mode=value;}};
}

test('missing app or bridge initialization produces a bounded manual recovery screen',()=>{
 for(const signal of ['markAppReady','markBridgeReady']){
  const f=watchdogFixture();assert.ok(f.window.hwfcStartupWatchdog,'independent startup guard must be installed');
  f.window.hwfcStartupWatchdog[signal]();const timer=f.timers.get(1);assert.equal(timer.ms,20000);timer.fn();
  assert.match(f.app.innerHTML,/could not connect/i);assert.match(f.app.innerHTML,/Reload/);assert.equal(f.reloads,0);
  f.button.click();assert.equal(f.reloads,1);
 }
});

test('successful initialization cancels watchdog without waiting for workspace data',()=>{
 const f=watchdogFixture();assert.ok(f.window.hwfcStartupWatchdog);
 f.window.hwfcStartupWatchdog.markAppReady();f.window.hwfcStartupWatchdog.markBridgeReady();
 assert.equal(f.timers.size,0);assert.equal(f.app.innerHTML,'');
});

test('late startup signals, existing workspace errors and pagehide never trigger automatic reload',()=>{
 for(const mode of ['workspace','error']){
  const f=watchdogFixture();assert.ok(f.window.hwfcStartupWatchdog);f.mode=mode;f.app.innerHTML='Keep existing '+mode;
  f.timers.get(1).fn();assert.equal(f.app.innerHTML,'Keep existing '+mode);
  f.window.hwfcStartupWatchdog.markAppReady();f.window.hwfcStartupWatchdog.markBridgeReady();assert.equal(f.reloads,0);
 }
 const f=watchdogFixture();assert.ok(f.window.hwfcStartupWatchdog);f.events.get('pagehide')();assert.equal(f.timers.size,0);
});

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

test('access denial shows an unlock instruction instead of a permanent spinner',()=>{
 const app={innerHTML:'',querySelector:()=>null},context={app,shared:{state:{ready:false,accessDenied:true},setDuplicateBusy(){}},billUpdating:false,saveState:'saved',sharedError:null,state:{view:'duplicates'},esc:String,backButtonHtml:()=>'<button>Go back to programs</button>',icon:()=>''};
 vm.runInNewContext(source.slice(source.indexOf('function render()'),source.indexOf('function guidePanel()')),context);context.render();
 assert.match(app.innerHTML,/session.*locked/i);assert.match(app.innerHTML,/unlock/i);assert.doesNotMatch(app.innerHTML,/aria-busy="true"|retry-shared/);
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
