import {comparisonInputKey,groupInvoices,invoiceKey,vendorKey} from './core.mjs';
import {resolveStatementVendor} from './vendor-identity.mjs';
import {adventureReferenceKeys} from './adventure-reference.mjs';
const fail=()=>Object.assign(Error('The BILL comparison source is incomplete or unavailable. Retry before reviewing.'),{code:'bill_incomplete'});
const hash=async value=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value))))].map(b=>b.toString(16).padStart(2,'0')).join('');
const validHash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
export function createComparisonSource(client,{onChange=()=>{},wait=ms=>new Promise(resolve=>setTimeout(resolve,ms))}={}){
  let disposed=false,provider={loaded:false,simulated:false,records:[],vendorDirectory:[],directoryComplete:false,scopes:{}},activeInfo=null;
  const directories=new Map(),latest=new Map(),queue=[];let running=0;
  const check=()=>{if(disposed)throw Error('AP is locked.');};
  const notify=()=>{if(!disposed)onChange(provider);};
  const scopeKey=info=>[info?.id,info?.workingSet?.workingSetId||'',info?.workingSet?.workingDigest||''].join(':');
  const sameScope=(page,info)=>!info?.workingSet||page.workingSetId===info.workingSet.workingSetId&&page.workingDigest===info.workingSet.workingDigest;
  async function request(action,payload){for(let attempt=0;;attempt++){try{const reply=await client.request(action,payload);check();return reply;}catch(error){if(error.code!=='bill_range_loading'||attempt>=59)throw error;await wait(1000);check();}}}
  function schedule(operation){return new Promise((resolve,reject)=>{queue.push({operation,resolve,reject});advance();});}
  function advance(){while(!disposed&&running<2&&queue.length){const item=queue.shift();running++;Promise.resolve().then(item.operation).then(item.resolve,item.reject).finally(()=>{running--;advance();});}}
  async function directoryFor(info,includeArchived=false){
    check();if(!info?.id)throw fail();
    const identity=scopeKey(info)+(includeArchived?':archive':'');
    if(!directories.has(identity)){
      const promise=(async()=>{
        const vendors=[],names=new Set(),cursors=new Set();let cursor=null,total=null,digest=null;
        do{
          const page=await request('bill_vendors_page',{import_id:info.id,...(info.workingSet?{working_set_id:info.workingSet.workingSetId}:{}),...(includeArchived?{include_archived:true}:{}),cursor,limit:500});check();
          if(page.importId!==info.id||!sameScope(page,info)||!Number.isInteger(page.total)||page.total<(info.workingSet?0:1)||page.total>500000||!Array.isArray(page.vendors)||!validHash(page.vendorDigest))throw fail();
          if(total!==null&&(total!==page.total||digest!==page.vendorDigest))throw fail();total=page.total;digest=page.vendorDigest;
          if(page.nextCursor!==null&&typeof page.nextCursor!=='string')throw fail();
          if(page.nextCursor&&!page.vendors.length)throw fail();
          for(const item of page.vendors){if(typeof item.vendor!=='string'||!vendorKey(item.vendor)||names.has(vendorKey(item.vendor)))throw fail();names.add(vendorKey(item.vendor));vendors.push({vendor:item.vendor});}
          if(vendors.length>total)throw fail();cursor=page.nextCursor;
          if(cursor&&cursors.has(cursor))throw fail();if(cursor)cursors.add(cursor);
        }while(cursor);
        const expectedDigest=includeArchived?info.workingSet?.archiveVendorDigest:info.workingSet?.vendorDigest||info.vendorDigest;
        if(vendors.length!==total||await hash(vendors)!==digest||expectedDigest&&expectedDigest!==digest)throw fail();
        return {vendors,digest,info};
      })();directories.set(identity,promise);
      promise.catch(()=>{if(directories.get(identity)===promise)directories.delete(identity);});
    }
    return directories.get(identity);
  }
  async function loadDirectory(info){
    check();const changed=activeInfo&&scopeKey(activeInfo)!==scopeKey(info);activeInfo=info;if(changed)latest.clear();
    provider={...info?.metadata,importId:info?.id||null,recordCount:info?.record_count||0,loaded:false,simulated:false,
              workingSet:info?.workingSet||null,records:[],vendorDirectory:[],directoryComplete:false,scopes:changed?{}:provider.scopes};
    if(!info){notify();return provider;}
    const result=await directoryFor(info);check();
    Object.assign(provider,{loaded:true,vendorDirectory:result.vendors,directoryComplete:true});notify();return provider;
  }
  function invalidate(id){latest.delete(id);if(provider.scopes[id])provider.scopes[id]={...provider.scopes[id],complete:false,error:null};notify();}
  function ensure(doc,mappings={}, {importInfo=activeInfo}={}){
    check();if(!importInfo)return Promise.resolve(null);
    const inputKey=comparisonInputKey(doc,mappings),key=scopeKey(importInfo)+':'+inputKey;
    if(latest.get(doc.id)?.key===key&&latest.get(doc.id).promise)return latest.get(doc.id).promise;
    const prior=provider.scopes[doc.id];
    if(prior?.complete&&prior.inputKey===inputKey&&prior.importId===importInfo.id&&prior.workingSet?.workingSetId===importInfo.workingSet?.workingSetId)return Promise.resolve(prior);
    const token=Symbol(),current={token,key,promise:null};latest.set(doc.id,current);
    provider.scopes[doc.id]={inputKey,importId:importInfo.id,workingSet:importInfo.workingSet||null,complete:false,directoryComplete:false,records:[],error:null};notify();
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
        const segment=keys.slice(start,start+100),query={importId:importInfo.id,...(importInfo.workingSet?{workingSetId:importInfo.workingSet.workingSetId}:{}),references:segment.filter(k=>k.type==='references').map(k=>k.value),amounts:segment.filter(k=>k.type==='amounts').map(k=>k.value)};
        let cursor=null,total=null,digest=null,count=0,lastOrdinal=-1;const cursors=new Set(),ids=new Set();
        do{
          const page=await request('bill_candidates_page',{query,cursor,limit:500});check();
          if(page.importId!==importInfo.id||!sameScope(page,importInfo)||!Number.isInteger(page.total)||page.total<0||page.total>(importInfo.workingSet?.activeCount??importInfo.record_count??500000)||!Array.isArray(page.records)||!validHash(page.queryDigest)||page.afterOrdinal!==lastOrdinal)throw fail();
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
      const scope={inputKey,importId:importInfo.id,workingSet:importInfo.workingSet||null,complete:true,records:[...all.values()],
                   vendorDirectory:directory.vendors,directoryComplete:true,metadata:importInfo.metadata||{},error:null};
      if(latest.get(doc.id)?.token===token&&comparisonInputKey(doc,mappings)===inputKey){provider.scopes[doc.id]=scope;notify();}
      return scope;
    }).catch(error=>{
      if(!disposed&&latest.get(doc.id)?.token===token){current.promise=null;provider.scopes[doc.id]={...provider.scopes[doc.id],complete:false,error:error.message,errorCode:error.code};notify();}
      throw error;
    });current.promise=promise;return promise;
  }
  async function lookupArchived(doc,mappings,reference,kind='invoice'){
    check();const info=activeInfo;if(!info?.workingSet)throw fail();
    const scope=await ensure(doc,mappings);check();
    const archiveDirectory=await directoryFor(info,true);check();
    const resolved=resolveStatementVendor(doc.vendor,archiveDirectory.vendors,mappings);
    const keys=[...new Set([invoiceKey(reference),...adventureReferenceKeys(resolved.vendor||doc.vendor,reference,kind)])].filter(Boolean);
    if(!keys.length||keys.length>100||!['invoice','credit'].includes(kind))throw fail();
    let cursor=null,total=null,digest=null,count=0,last=-1;const cursors=new Set(),found=new Map(),archived=new Set();
    do{
      const page=await request('bill_archived_candidates_page',{import_id:info.id,references:keys.map(invoiceKey=>({invoiceKey,kind})),cursor,limit:500});
      if(page.importId!==info.id||!sameScope(page,info)||!Number.isSafeInteger(page.total)||page.total<0||page.total>info.record_count||!validHash(page.queryDigest)||page.afterOrdinal!==last||!Array.isArray(page.records)||!Array.isArray(page.archivedIds))throw fail();
      if(total!==null&&(page.total!==total||page.queryDigest!==digest))throw fail();total=page.total;digest=page.queryDigest;
      const pageIds=new Set();
      for(const record of page.records){
        if(typeof record.id!=='string'||!record.id.startsWith(info.id+':'))throw fail();
        const suffix=record.id.slice(info.id.length+1);if(!/^(0|[1-9][0-9]*)$/.test(suffix))throw fail();const ordinal=Number(suffix);
        if(!Number.isSafeInteger(ordinal)||ordinal<=last||ordinal>=info.record_count||found.has(record.id)||!keys.includes(invoiceKey(record.invoiceNumber))||(record.kind??'invoice')!==kind)throw fail();
        found.set(record.id,record);pageIds.add(record.id);last=ordinal;count++;
      }
      if(page.archivedIds.some(id=>!pageIds.has(id)))throw fail();for(const id of page.archivedIds)archived.add(id);
      cursor=page.nextCursor;if(cursor!==null&&(typeof cursor!=='string'||!page.records.length||cursors.has(cursor)))throw fail();if(cursor)cursors.add(cursor);
    }while(cursor);
    if(count!==total||activeInfo!==info||provider.scopes[doc.id]!==scope||scope.inputKey!==comparisonInputKey(doc,mappings))throw fail();
    const merged=new Map((scope.archivedRecords||[]).map(r=>[r.id,r]));for(const [id,record] of found)merged.set(id,record);
    scope.vendorDirectory=archiveDirectory.vendors;scope.archivedRecords=[...merged.values()];scope.archivedIds=[...new Set([...(scope.archivedIds||[]),...archived])];notify();return scope;
  }
  return {loadDirectory,ensure,invalidate,lookupArchived,get provider(){return provider;},dispose(){disposed=true;latest.clear();directories.clear();for(const item of queue.splice(0))item.reject(Error('AP is locked.'));provider.scopes={};}};
}
