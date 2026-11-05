import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import {createRequire} from 'node:module';
const root=resolve(import.meta.dirname,'../../..'),frontend=resolve(root,'app/ap_statements/frontend');
const {chromium}=createRequire(resolve(root,'workers/ap_mail/package.json'))('playwright');
const server=createServer(async(req,res)=>{
 try{
  if(req.url==='/'){
   res.setHeader('Content-Type','text/html');res.end(`<!doctype html><html><head><link rel="stylesheet" href="/styles.css"></head><body><div id="app"></div><div id="overlay-root"></div>
   <div id="toast"></div><input id="pdf-input" type="file" hidden><input id="csv-input" type="file" hidden>
   <script>window.calls=[];window.hwfcSharedClient={dispose(){},async request(action,payload){calls.push(action);
    if(action==='bootstrap')return {activeImport:null,statements:[],nextCursor:null,mappings:{},mappingVersions:{},capabilities:{mailIntake:1}};
    if(action==='mail_status')return {connection:{id:'connection',generation:1,version:1,label:'AP Statements',paused:false},counts:{queued:1}};
    if(action==='mail_list'||action==='mail_messages')return {items:[],nextCursor:null};throw Error(action);}};</script><script type="module" src="/app.mjs"></script></body></html>`);return;
  }
  const path=resolve(frontend,'.'+decodeURIComponent(req.url.split('?')[0]));
  if(!path.startsWith(frontend+sep)||!['.mjs','.css'].includes(extname(path))){res.writeHead(404).end();return;}
  res.setHeader('Content-Type',extname(path)==='.mjs'?'text/javascript':'text/css');res.end(await readFile(path));
 }catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{
 browser=await chromium.launch({headless:true,chromiumSandbox:true,...(process.env.AP_MAIL_BROWSER_BINARY?{executablePath:process.env.AP_MAIL_BROWSER_BINARY}:{})});
 const page=await browser.newPage({viewport:{width:1280,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:'+server.address().port);
 try{await page.waitForSelector('#mail-imports-summary .mail-summary',{timeout:6000});}
 catch(error){console.error(JSON.stringify({errors,body:await page.locator('body').innerText(),calls:await page.evaluate(()=>window.calls)}));throw error;}
 await page.click('[data-action="mail-open"]');await page.waitForSelector('#mail-imports-region .mail-imports');
 if(process.env.AP_MAIL_SCREENSHOT)await page.screenshot({path:process.env.AP_MAIL_SCREENSHOT,fullPage:true});
 const result=await page.evaluate(async()=>{
  const {patchMailImports}=await import('/mail-imports-ui.mjs');
  const region=document.querySelector('#mail-imports-region');
  const overlay=document.querySelector('#overlay-root');overlay.innerHTML='<div class="drawer" style="height:100px;overflow:auto"><canvas id="pdf-canvas"></canvas><input id="review-note" value="Typing a review"><div style="height:800px"></div></div>';
  const canvas=document.querySelector('#pdf-canvas'),note=document.querySelector('#review-note'),drawer=overlay.firstChild;
  note.focus();note.setSelectionRange(2,5);drawer.scrollTop=41;
  const form=document.querySelector('#mail-history-form'),after=document.querySelector('#mail-history-after');after.value='2026-10-01';
  const snapshot={enabled:true,loaded:true,connection:{id:'connection',version:1,label:'AP Statements',paused:false},counts:{},items:[],messages:[]};
  for(let i=0;i<10;i++){
   const before=window.calls.filter(a=>a==='mail_status').length;
   document.querySelector('[data-action="mail-refresh"]').click();
   for(let n=0;n<50&&window.calls.filter(a=>a==='mail_status').length===before;n++)await new Promise(r=>setTimeout(r,5));
   await new Promise(r=>setTimeout(r,5));snapshot.counts.queued=i;patchMailImports(region,snapshot);
  }
  return {canvasSame:canvas===document.querySelector('#pdf-canvas'),noteSame:note===document.querySelector('#review-note'),
   focused:document.activeElement===note,note:note.value,selection:note.selectionStart,scroll:drawer.scrollTop,
   formSame:form===document.querySelector('#mail-history-form'),date:after.value,requests:window.calls.filter(a=>a==='bootstrap').length};
 });
 assert.deepEqual(result,{canvasSame:true,noteSame:true,focused:true,note:'Typing a review',selection:2,scroll:41,formSame:true,date:'2026-10-01',requests:1});
 await page.evaluate(()=>{
  document.querySelector('#overlay-root').innerHTML='';
  const old=window.hwfcSharedClient.request;
  window.hwfcSharedClient.request=async(action,payload)=>{
   if(action==='mail_list'||action==='mail_receipt_updates')return {items:[{id:'completed-receipt',version:2,statement_id:'completed-statement',filename:'completed.pdf',status:'awaiting_review',display_status:'reviewed',original_available:true,preliminary_available:true}],nextCursor:null};
   if(action==='mail_evidence')return {receipt_id:'completed-receipt',receipt_version:2,preliminary:true,current_head:false,compared_at:'2026-11-04T12:00:00Z',source:{label:'Synthetic Bills.csv'},metadata:{},rows:[{invoiceNumber:'123',originalAmount:150,status:'amount',reason:'Amounts differ',candidates:[{invoiceNumber:'123',amount:100}]}],total:1,nextCursor:null};
   if(action==='mail_preview')return {url:location.origin+'/synthetic-original.pdf',expiresIn:300};
   if(action==='statement')return {doc:{id:'completed-statement',vendor:'Reviewed Vendor',filename:'completed.pdf',confirmed:true,rows:[],warnings:[],pageCount:1},
    completed:true,readOnly:true,version:2,resolutions:{},results:[],mappingSnapshot:{},originalAvailable:false};
   return old(action,payload);
  };
  document.querySelector('[data-action="mail-refresh"]').click();
 });
 await page.waitForSelector('[data-action="mail-review"]');
 await page.click('[data-action="mail-evidence"]');await page.waitForSelector('.mail-evidence');
 assert.match(await page.locator('.mail-evidence').innerText(),/Amount difference/);
 assert.match(await page.locator('.mail-evidence').innerText(),/Synthetic Bills.csv/);
 if(process.env.AP_MAIL_EVIDENCE_SCREENSHOT)await page.screenshot({path:process.env.AP_MAIL_EVIDENCE_SCREENSHOT,fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.querySelector('.mail-evidence .table-wrap').scrollWidth>document.querySelector('.mail-evidence .table-wrap').clientWidth),true);
 await page.setViewportSize({width:1280,height:900});
 await page.click('[data-action="mail-evidence-close"]');assert.equal(await page.locator('.mail-evidence').count(),0);
 await page.click('[data-action="mail-review"]');
 try{await page.waitForSelector('#overlay-root .drawer',{timeout:3000});}
 catch(error){console.error(JSON.stringify({errors,body:await page.locator('body').innerText()}));throw error;}
 assert.match(await page.locator('#overlay-root').innerText(),/Reviewed Vendor/);
 await page.evaluate(()=>document.querySelector('#overlay-root').innerHTML='');
 assert.deepEqual(errors,[]);
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.querySelector('#mail-history-form').getBoundingClientRect().width>0),true);
 await page.click('[data-action="mail-preview"]');await page.waitForSelector('#mail-private-preview');
 await page.evaluate(()=>{
  const timer=document.querySelector('#mail-private-preview').mailTimer,clear=window.clearTimeout;
  window.previewTimerCleared=false;window.clearTimeout=id=>{if(id===timer&&timer!==undefined)window.previewTimerCleared=true;return clear(id);};
  const old=window.hwfcSharedClient.request;window.hwfcSharedClient.request=(action,payload)=>action==='mail_status'?Promise.reject(Object.assign(Error('Locked'),{code:'denied'})):old(action,payload);
  document.querySelector('[data-action="mail-refresh"]').click();
 });
 await page.waitForSelector('#mail-private-preview',{state:'detached',timeout:3000});
 assert.equal(await page.evaluate(()=>window.previewTimerCleared),true);
 console.log('Mail browser DOM checks passed');
}finally{await browser?.close();await new Promise(r=>server.close(r));}
