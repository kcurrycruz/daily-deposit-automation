import {createInterface} from 'node:readline';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {preliminaryReconcile,groupInvoices} from '../../app/ap_statements/frontend/core.mjs';
import {assessStatement} from '../../app/ap_statements/frontend/statement-duplicates.mjs';
import {createComparisonSource} from '../../app/ap_statements/frontend/comparison-source.mjs';
const failure=code=>Object.assign(Error(code),{code});
const bounded=value=>{
 if(Buffer.byteLength(JSON.stringify(value))>1024*1024)throw failure('limit');
 return value;
};
export function calculatePreview(doc,provider,mappings={}){
 const records=provider.scopes?.[doc.id]?.records||provider.records||[];
 if(groupInvoices(doc).length*Math.max(1,records.length)>1_000_000)throw failure('limit');
 const rows=preliminaryReconcile(doc,provider,mappings);
 if(rows.reduce((n,row)=>n+(row.candidates?.length||0),0)>2000)throw failure('limit');
 return bounded({preliminary:true,rows});
}
export function assessIncoming(doc,candidates,mappings={}){
 return bounded(assessStatement(doc,candidates,mappings));
}
export async function prepareComparison(doc,info,mappings,request){
 if(!info){const provider={loaded:false,simulated:false,records:[],scopes:{}};return {provider,evidence:calculatePreview(doc,provider,mappings)};}
 const source=createComparisonSource({request});
 try{
  await source.loadDirectory(info);await source.ensure(doc,mappings);
  const provider=structuredClone(source.provider);bounded(provider);
  return bounded({provider,evidence:calculatePreview(doc,provider,mappings)});
 }finally{source.dispose();}
}

async function main(){
 const lines=createInterface({input:process.stdin,crlfDelay:Infinity});
 const iterator=lines[Symbol.asyncIterator]();const first=await iterator.next();
 if(first.done||Buffer.byteLength(first.value)>1024*1024)throw failure('invalid');
 const input=JSON.parse(first.value);let sequence=0;
 async function request(action,payload){
  const id=++sequence;
  process.stdout.write(JSON.stringify({type:'read',request_id:id,action,payload})+'\n');
  const next=await iterator.next();
  if(next.done||Buffer.byteLength(next.value)>1024*1024)throw failure('unavailable');
  const reply=JSON.parse(next.value);
  if(reply.type!=='reply'||reply.request_id!==id)throw failure('unavailable');
  if(!reply.ok)throw failure(reply.error?.code||'unavailable');
  return reply.value;
 }
 try{
  let value;
  if(input.mode==='prepare')value=await prepareComparison(input.doc,input.info,input.mappings||{},request);
  else if(input.mode==='compare')value=calculatePreview(input.doc,input.provider,input.mappings||{});
  else if(input.mode==='assess')value=assessIncoming(input.doc,input.candidates,input.mappings||{});
  else throw failure('invalid');
  process.stdout.write(JSON.stringify({type:'result',value:bounded(value)})+'\n');
 }finally{lines.close();process.stdin.destroy();}
}
if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url){
 main().catch(error=>{
  const codes=['invalid','limit','stale_source','stale_claim','denied','not_configured','auth','quota'];
  process.stdout.write(JSON.stringify({type:'error',code:codes.includes(error.code)?error.code:'unavailable'})+'\n');
  process.stdin.destroy();process.exitCode=1;
 });
}
