import {comparisonInputKey,groupInvoices,invoiceKey,vendorKey} from './core.mjs';
import {resolveStatementVendor} from './vendor-identity.mjs';
import {adventureReferenceKeys} from './adventure-reference.mjs';
const fail=()=>Object.assign(Error('The BILL comparison source is incomplete or unavailable. Retry before reviewing.'),{code:'bill_incomplete'});
const hash=async value=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value))))].map(b=>b.toString(16).padStart(2,'0')).join('');
const validHash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
export function createComparisonSource(client,{onChange=()=>{}}={}){
  let disposed=false,provider={loaded:false,simulated:false,records:[],vendorDirectory:[],directoryComplete:false,scopes:{}},activeInfo=null;
  const directories=new Map(),latest=new Map(),queue=[];let running=0;
  const check=()=>{if(disposed)throw Error('AP is locked.');};
  const notify=()=>{if(!disposed)onChange(provider);};
  function schedule(operation){return new Promise((resolve,reject)=>{queue.push({operation,resolve,reject});advance();});}
  function advance(){while(!disposed&&running<2&&queue.length){const item=queue.shift();running++;Promise.resolve().then(item.operation).then(item.resolve,item.reject).finally(()=>{running--;advance();});}}
  async function directoryFor(info){
    check();if(!info?.id)throw fail();
    if(!directories.has(info.id)){
      const promise=(async()=>{
        const vendors=[],names=new Set(),cursors=new Set();let cursor=null,total=null,digest=null;
        do{
          const page=await client.request('bill_vendors_page',{import_id:info.id,cursor,limit:500});check();
          if(page.importId!==info.id||!Number.isInteger(page.total)||page.total<1||page.total>500000||!Array.isArray(page.vendors)||!validHash(page.vendorDigest))throw fail();
          if(total!==null&&(total!==page.total||digest!==page.vendorDigest))throw fail();total=page.total;digest=page.vendorDigest;
          if(page.nextCursor!==null&&typeof page.nextCursor!=='string')throw fail();
          if(page.nextCursor&&!page.vendors.length)throw fail();
          for(const item of page.vendors){if(typeof item.vendor!=='string'||!vendorKey(item.vendor)||names.has(vendorKey(item.vendor)))throw fail();names.add(vendorKey(item.vendor));vendors.push({vendor:item.vendor});}
          if(vendors.length>total)throw fail();cursor=page.nextCursor;
          if(cursor&&cursors.has(cursor))throw fail();if(cursor)cursors.add(cursor);
        }while(cursor);
        if(vendors.length!==total||await hash(vendors)!==digest||info.vendorDigest&&info.vendorDigest!==digest)throw fail();
        return {vendors,digest,info};
      })();directories.set(info.id,promise);
      promise.catch(()=>{if(directories.get(info.id)===promise)directories.delete(info.id);});
    }
    return directories.get(info.id);
  }
  async function loadDirectory(info){
    check();activeInfo=info;
    provider={...info?.metadata,importId:info?.id||null,recordCount:info?.record_count||0,loaded:false,simulated:false,
              records:[],vendorDirectory:[],directoryComplete:false,scopes:provider.scopes};
    if(!info){notify();return provider;}
    const result=await directoryFor(info);check();
    Object.assign(provider,{loaded:true,vendorDirectory:result.vendors,directoryComplete:true});notify();return provider;
  }
  function invalidate(id){latest.delete(id);if(provider.scopes[id])provider.scopes[id]={...provider.scopes[id],complete:false,error:null};notify();}
  function ensure(doc,mappings={}, {importInfo=activeInfo}={}){
    check();if(!importInfo)return Promise.resolve(null);
    const inputKey=comparisonInputKey(doc,mappings),key=importInfo.id+':'+inputKey;
    if(latest.get(doc.id)?.key===key&&latest.get(doc.id).promise)return latest.get(doc.id).promise;
    const prior=provider.scopes[doc.id];
    if(prior?.complete&&prior.inputKey===inputKey&&prior.importId===importInfo.id)return Promise.resolve(prior);
    const token=Symbol(),current={token,key,promise:null};latest.set(doc.id,current);
    provider.scopes[doc.id]={inputKey,importId:importInfo.id,complete:false,directoryComplete:false,records:[],error:null};notify();
    const promise=schedule(async()=>{
      const directory=await directoryFor(importInfo);check();
      const resolved=resolveStatementVendor(doc.vendor,directory.vendors,mappings),vendor=resolved.vendor?vendorKey(resolved.vendor):null;
      const refs=new Map(),amounts=new Map();
      for(const row of groupInvoices(doc)){
        if(!['invoice','credit'].includes(row.kind))continue;
        const reference=invoiceKey(row.invoiceNumber);
        if(reference)refs.set(JSON.stringify([reference,row.kind]),{invoiceKey:reference,kind:row.kind});
        for(const alias of adventureReferenceKeys(resolved.vendor,reference,row.kind))refs.set(JSON.stringify([alias,row.kind]),{invoiceKey:alias,kind:row.kind});
        if(vendor&&Number.isSafeInteger(row.originalAmount))amounts.set(JSON.stringify([vendor,row.kind,row.originalAmount]),{vendorKey:vendor,kind:row.kind,amount:row.originalAmount});
      }
      const keys=[...[...refs.values()].map(value=>({type:'references',value})),...[...amounts.values()].map(value=>({type:'amounts',value}))],all=new Map();
      for(let start=0;start<keys.length;start+=100){
        const segment=keys.slice(start,start+100),query={importId:importInfo.id,references:segment.filter(k=>k.type==='references').map(k=>k.value),amounts:segment.filter(k=>k.type==='amounts').map(k=>k.value)};
        let cursor=null,total=null,digest=null,count=0,lastOrdinal=-1;const cursors=new Set(),ids=new Set();
        do{
          const page=await client.request('bill_candidates_page',{query,cursor,limit:500});check();
          if(page.importId!==importInfo.id||!Number.isInteger(page.total)||page.total<0||page.total>(importInfo.record_count||500000)||!Array.isArray(page.records)||!validHash(page.queryDigest)||page.afterOrdinal!==lastOrdinal)throw fail();
          if(total!==null&&(total!==page.total||digest!==page.queryDigest))throw fail();total=page.total;digest=page.queryDigest;
          if(page.nextCursor!==null&&typeof page.nextCursor!=='string')throw fail();
          if(page.nextCursor&&!page.records.length)throw fail();
          for(const record of page.records){
            if(typeof record.id!=='string'||!record.id.startsWith(importInfo.id+':'))throw fail();
            const raw=record.id.slice(importInfo.id.length+1);if(!/^(0|[1-9][0-9]*)$/.test(raw))throw fail();
            const ordinal=Number(raw);if(!Number.isSafeInteger(ordinal)||ordinal<=lastOrdinal||ordinal>=(importInfo.record_count||500000)||ids.has(record.id))throw fail();
            ids.add(record.id);lastOrdinal=ordinal;count++;
            if(all.has(record.id)&&JSON.stringify(all.get(record.id))!==JSON.stringify(record))throw fail();all.set(record.id,record);
          }
          if(count>total)throw fail();cursor=page.nextCursor;
          if(cursor&&cursors.has(cursor))throw fail();if(cursor)cursors.add(cursor);
        }while(cursor);
        if(count!==total)throw fail();
      }
      const scope={inputKey,importId:importInfo.id,complete:true,records:[...all.values()],
                   vendorDirectory:directory.vendors,directoryComplete:true,metadata:importInfo.metadata||{},error:null};
      if(latest.get(doc.id)?.token===token&&comparisonInputKey(doc,mappings)===inputKey){provider.scopes[doc.id]=scope;notify();}
      return scope;
    }).catch(error=>{
      if(!disposed&&latest.get(doc.id)?.token===token){current.promise=null;provider.scopes[doc.id]={...provider.scopes[doc.id],complete:false,error:error.message};notify();}
      throw error;
    });current.promise=promise;return promise;
  }
  return {loadDirectory,ensure,invalidate,get provider(){return provider;},dispose(){disposed=true;latest.clear();directories.clear();for(const item of queue.splice(0))item.reject(Error('AP is locked.'));provider.scopes={};}};
}
