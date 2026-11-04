import {createServer} from 'node:http';
import {readFile,readdir,stat} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const own=dirname(fileURLToPath(import.meta.url));
const frontend=resolve(own,'../../app/ap_statements/frontend');
const modules=['extraction.mjs','core.mjs','source-location.mjs','vendor-identity.mjs','adventure-reference.mjs','dot-matrix.worker.js'];
const failure=code=>Object.assign(Error(code),{code});
const contentType=path=>({'.mjs':'text/javascript','.js':'text/javascript','.wasm':'application/wasm','.gz':'application/gzip','.html':'text/html'}[extname(path)]||'application/octet-stream');

async function assetMap(){
 const files=new Map([['/',resolve(own,'page.html')],['/page.mjs',resolve(own,'page.mjs')]]);
 for(const file of modules)files.set('/frontend/'+file,resolve(frontend,file));
 async function walk(folder,url){
  for(const entry of await readdir(folder,{withFileTypes:true})){
   const path=resolve(folder,entry.name),key=url+'/'+entry.name;
   if(entry.isDirectory())await walk(path,key);
   else if(entry.isFile()&&/\.(?:js|mjs|wasm|gz)$/.test(entry.name))files.set(key,path);
  }
 }
 await walk(resolve(frontend,'vendor'),'/frontend/vendor');return files;
}

export async function openExtractionPage(){
 const assets=await assetMap();let browser,context;
 const server=createServer(async(req,res)=>{
  try{
   const url=new URL(req.url,'http://127.0.0.1');
   const path=assets.get(url.pathname);
   if(req.method!=='GET'||!path){res.writeHead(404);res.end();return;}
   res.writeHead(200,{'Content-Type':contentType(path),'Cache-Control':'no-store',
    'Cross-Origin-Opener-Policy':'same-origin','Cross-Origin-Embedder-Policy':'require-corp','Cross-Origin-Resource-Policy':'same-origin',
    'Content-Security-Policy':"default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' blob:; img-src 'self' data: blob:; font-src 'self' data: blob:; base-uri 'none'; frame-src 'none'; object-src 'none'"});
   res.end(await readFile(path));
  }catch{res.writeHead(400);res.end();}
 });
 await new Promise((accept,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',accept);});
 const origin='http://127.0.0.1:'+server.address().port;
 const close=async()=>{
  try{await context?.close();}finally{try{await browser?.close();}finally{
   server.closeAllConnections();await new Promise(accept=>server.close(accept));
  }}
 };
 try{
  const {chromium}=createRequire(import.meta.url)('playwright');
  browser=await chromium.launch({headless:true,chromiumSandbox:true,
   ...(process.env.AP_MAIL_BROWSER_BINARY?{executablePath:process.env.AP_MAIL_BROWSER_BINARY}:{}),
   args:['--disable-dev-shm-usage','--enable-automation']});
  context=await browser.newContext({serviceWorkers:'block',acceptDownloads:false,permissions:[]});
  await context.route('**/*',async route=>{
   const request=route.request();let allowed=false;
   try{const url=new URL(request.url());allowed=url.origin===origin&&assets.has(url.pathname)&&request.method()==='GET';}catch{}
   await (allowed?route.continue():route.abort('blockedbyclient'));
  });
  const page=await context.newPage();
  await page.goto(origin,{waitUntil:'load',timeout:30000});
  await page.waitForFunction(()=>typeof window.extractStatement==='function',null,{timeout:30000});
  return {page,browser,close,origin};
 }catch(error){await close();throw failure('not_configured');}
}

export async function extractPDFFile(path,filename,onProgress=()=>{}){
 const info=await stat(path);
 if(!info.isFile()||info.size<1||info.size>20*1024*1024)throw failure('limit');
 if(typeof filename!=='string'||Buffer.byteLength(filename)>1024)throw Error('Invalid filename.');
 const pdf=await readFile(path);
 if(!pdf.subarray(0,5).equals(Buffer.from('%PDF-')))throw Error('Invalid PDF.');
 const view=await openExtractionPage();
 try{
  await view.page.exposeFunction('reportScanProgress',value=>{
   if(Number.isInteger(value?.page)&&Number.isInteger(value?.total)&&value.page>=1&&value.total<=100)
    onProgress({page:value.page,total:value.total,stage:'scanning'});
  });
  const doc=await view.page.evaluate(async({data,filename})=>window.extractStatement(data,filename),{data:pdf.toString('base64'),filename});
  if(!doc?.rows?.length||doc.confirmed!==false)throw failure('unreadable');
  return doc;
 }finally{await view.close();}
}

async function main(){
 let size=0,buffer=[];
 for await(const chunk of process.stdin){size+=chunk.length;if(size>16384)throw Error('Input limit.');buffer.push(chunk);}
 const input=JSON.parse(Buffer.concat(buffer).toString('utf8'));
 if(!input||typeof input.path!=='string'||Object.keys(input).some(key=>!['path','filename'].includes(key)))throw Error('Invalid request.');
 const doc=await extractPDFFile(input.path,input.filename,value=>process.stdout.write(JSON.stringify({type:'progress',value})+'\n'));
 const result=JSON.stringify({type:'result',doc});
 if(Buffer.byteLength(result)>1024*1024)throw failure('limit');
 process.stdout.write(result+'\n');
}
if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url){
 main().catch(error=>{process.stdout.write(JSON.stringify({type:'error',code:['limit','not_configured'].includes(error.code)?error.code:'unreadable'})+'\n');process.exitCode=1;});
}
