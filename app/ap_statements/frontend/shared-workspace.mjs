import {reconcile,groupInvoices,vendorKey} from './core.mjs';
import {LIMITS} from './shared-client.mjs';
import {reviewNotesOnly} from './session.mjs';
const clone=value=>JSON.parse(JSON.stringify(value));
const unloaded=()=>({loaded:false,simulated:false,records:[],label:'Loading shared BILL records…'});
const fields=(value,names)=>Object.fromEntries(names.split(' ').filter(k=>value[k]!==undefined).map(k=>[k,value[k]]));
export function comparisonSnapshot(doc,provider,mappings){return reconcile(doc,provider,mappings).map(row=>fields(row,'id invoiceNumber kind originalAmount outstanding activity date confidence duplicate page status reason candidates matchMethod statementId vendor simulated'));}
export function createSharedWorkspace(client,{onState=()=>{},onSaveState=()=>{}}={}){
  const state={ready:false,provider:unloaded(),importId:null,statements:[],details:new Map(),mappings:{},mappingVersions:{},resolutions:{}};
  const localFiles=new Map();let disposed=false,loaded=false;
  function check(){if(disposed)throw Error('AP is locked.');}
  const emit=()=>{check();onState(state);};
  function write(operation){
    const steps=[];
    async function execute(){
      check();onSaveState('saving');let index=0;
      const request=async(action,payload)=>{
        check();const current=index++,identity=JSON.stringify({action,payload});
        if(!steps[current])steps[current]={id:crypto.randomUUID(),identity};
        if(steps[current].identity!==identity)throw Error('Retry payload changed. Reload latest before continuing.');
        if('reply' in steps[current])return clone(steps[current].reply);
        const reply=await client.request(action,payload,{requestId:steps[current].id});check();steps[current].reply=clone(reply);return reply;
      };
      try{const result=await operation(request);check();onSaveState('saved');return result;}
      catch(error){error.retry=execute;if(!disposed)onSaveState('not_saved',error);throw error;}
    }
    return execute();
  }
  function adopt(detail){
    state.details.set(detail.doc.id,detail);
    if(!detail.completed&&!detail.archived){const i=state.statements.findIndex(d=>d.id===detail.doc.id);if(i<0)state.statements.push(detail.doc);else state.statements[i]=detail.doc;}
    Object.assign(state.resolutions,detail.resolutions||{});return detail;
  }
  async function loadProvider(importId,metadata={}){
    check();const records=[];let after=-1,total=null;const seen=new Set();
    do{
      const page=await client.request('records_page',{import_id:importId,after_ordinal:after,limit:LIMITS.batch});check();
      if(page.importId!==importId||!Number.isInteger(page.recordCount)||page.recordCount<1||page.recordCount>LIMITS.records||total!==null&&total!==page.recordCount)throw Error('Shared import is incomplete. Matching is unavailable.');
      total=page.recordCount;const expected=Math.min(LIMITS.batch,total-records.length);
      if(!Array.isArray(page.records)||page.records.length!==expected||!expected)throw Error('Shared import is incomplete. Matching is unavailable.');
      for(const record of page.records){if(seen.has(record.id)||record.id!==`${importId}:${records.length}`)throw Error('Shared import is incomplete.');seen.add(record.id);records.push(record);}
      const next=records.length<total?records.length-1:null;
      if(page.nextCursor!==next)throw Error('Shared import is incomplete.');after=next;
    }while(after!==null);
    return {...metadata,records,loaded:true,simulated:false};
  }
  async function load({replace=false}={}){
    check();if(loaded&&!replace)return state;
    // Work is assembled separately. A failed refresh cannot replace unsaved edits.
    const summaries=[],cursors=new Set();let cursor=null,home;
    try{
      do{const page=await client.request('bootstrap',{cursor,limit:50});check();home??=page;
        if(page.activeImport?.id!==home.activeImport?.id)throw Error('The shared import changed while loading. Retry.');
        summaries.push(...page.statements);cursor=page.nextCursor;if(cursor&&cursors.has(cursor))throw Error('Shared statement list is incomplete.');cursors.add(cursor);
      }while(cursor);
      const provider=home.activeImport?await loadProvider(home.activeImport.id,home.activeImport.metadata):{...unloaded(),label:'No BILL records imported'};
      const details=[];for(const summary of summaries)details.push(await client.request('statement',{statement_id:summary.id}));check();
      state.statements=[];state.details.clear();state.resolutions={};state.mappings=home.mappings;state.mappingVersions=home.mappingVersions||{};
      state.provider=provider;state.importId=home.activeImport?.id||null;
      for(const detail of details){if(detail.importId!==state.importId||JSON.stringify(detail.mappingSnapshot||{})!==JSON.stringify(state.mappings))detail.resolutions=reviewNotesOnly(detail.resolutions||{});adopt(detail);}
      state.ready=true;loaded=true;emit();return state;
    }catch(error){if(!loaded){state.ready=false;state.provider=unloaded();emit();}throw error;}
  }
  async function upload(file,kind,request){
    if(!file||!Number.isInteger(file.size)||file.size<1||file.size>LIMITS.file)throw Error('Each PDF or CSV must be at most 20 MiB.');
    const bytes=new Uint8Array(await file.arrayBuffer());check();
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
    const begun=await request('upload_begin',{kind,filename:file.name,size:bytes.length,file_hash:hash});
    for(let at=0;at<bytes.length;at+=LIMITS.chunk){let binary='';for(const byte of bytes.subarray(at,at+LIMITS.chunk))binary+=String.fromCharCode(byte);await request('upload_chunk',{upload_id:begun.upload_id,index:at/LIMITS.chunk,data:btoa(binary)});}
    return request('upload_finish',{upload_id:begun.upload_id});
  }
  function saveData(doc,expectedVersion,resolutions){
    const rows=groupInvoices(doc),ids=new Set(rows.map(r=>r.id));
    return {statement_id:doc.id,expected_version:expectedVersion,doc:clone(doc),resolutions:Object.fromEntries(Object.entries(resolutions).filter(([id])=>ids.has(id))),
      import_id:state.importId,mapping_snapshot:clone(state.mappings),results:comparisonSnapshot(doc,state.provider,state.mappings),rule_version:'ap-match-v2'};
  }
  function saveStatement(doc,expectedVersion,{resolutions=state.resolutions}={}){
    const payload=saveData(doc,expectedVersion,resolutions);
    return write(async request=>{const reply=await request('save_revision',payload);const detail=adopt({...(state.details.get(doc.id)||{}),doc:clone(payload.doc),version:reply.version,resolutions:clone(payload.resolutions),results:payload.results,importId:payload.import_id,mappingSnapshot:payload.mapping_snapshot,ruleVersion:payload.rule_version});emit();return detail;});
  }
  function uploadStatement(file,extract){
    localFiles.set(file,file);let extracted=null,finished=null;
    return write(async request=>{
      finished=await upload(file,'pdf',request);
      const stored=await request('statement',{statement_id:finished.statement_id});adopt(stored);emit();
      if(finished.duplicate){localFiles.delete(file);return stored;}
      if(!extracted){try{extracted=await extract(file);}catch(error){extracted={...stored.doc,confirmed:false,warnings:[...(stored.doc.warnings||[]),`Extraction could not finish: ${error.message}. Review the original and add rows manually.`]};}}
      extracted={...extracted,id:finished.statement_id,fileSize:file.size,fileModified:file.lastModified||0,confirmed:false};
      const payload=saveData(extracted,stored.version,{});
      const saved=await request('save_revision',payload);
      const detail=adopt({...stored,doc:extracted,version:saved.version,results:payload.results,importId:state.importId,mappingSnapshot:clone(state.mappings),ruleVersion:'ap-match-v2'});
      localFiles.delete(file);emit();return detail;
    });
  }
  function importBills(file,parsedProvider){
    const provider=clone(parsedProvider);if(!provider.loaded||provider.simulated||!provider.records?.length||provider.records.length>LIMITS.records)return Promise.reject(Error('Choose a real BILL export with at most 100,000 normalized records.'));
    return write(async request=>{
      const original=await upload(file,'csv',request);const {records,...metadata}=provider;
      const begun=await request('import_begin',{upload_id:original.upload_id,provider:metadata,record_count:records.length});
      if(begun.state!=='ready')for(let start=0;start<records.length;start+=LIMITS.batch)await request('import_records',{import_id:begun.import_id,start,records:records.slice(start,start+LIMITS.batch)});
      await request('import_finish',{import_id:begun.import_id});
      const authoritative=await loadProvider(begun.import_id,metadata);
      if(state.importId!==begun.import_id)state.resolutions=reviewNotesOnly(state.resolutions);
      state.importId=begun.import_id;state.provider=authoritative;emit();return authoritative;
    });
  }
  function saveMapping(mapping,expectedVersion){
    const payload={vendor:mapping.vendor,bill_vendor:mapping.bill_vendor,expected_version:expectedVersion};
    return write(async request=>{const reply=await request('save_mapping',payload);if(vendorKey(state.mappings[payload.vendor]||payload.vendor)!==vendorKey(payload.bill_vendor))for(const doc of state.statements.filter(d=>d.vendor===payload.vendor))for(const row of groupInvoices(doc))if(state.resolutions[row.id])state.resolutions[row.id]={note:state.resolutions[row.id].note||''};state.mappings[payload.vendor]=payload.bill_vendor;state.mappingVersions[payload.vendor]=reply.version;emit();return reply;});
  }
  async function originalPdf(statementId){const link=await client.request('pdf_preview',{statement_id:statementId});check();const response=await fetch(link.url,{referrerPolicy:'no-referrer'});if(!response.ok)throw Error('Original preview expired or is unavailable. Reopen to retry.');const bytes=await response.arrayBuffer();check();return new Blob([bytes],{type:'application/pdf'});}
  return {state,load,loadProvider,importBills,uploadStatement,saveStatement,saveMapping,originalPdf,
    archiveStatement(id,expectedVersion){return write(async request=>{const reply=await request('archive_statement',{statement_id:id,expected_version:expectedVersion});state.statements=state.statements.filter(doc=>doc.id!==id);emit();return reply;});},
    async statement(id,revisionId){check();const detail=await client.request('statement',{statement_id:id,...(revisionId?{revision_id:revisionId}:{})});check();return detail;},
    write,adopt,
    dispose(){disposed=true;client.dispose();localFiles.clear();state.statements=[];state.details.clear();state.resolutions={};state.mappings={};state.mappingVersions={};state.provider=unloaded();state.importId=null;state.ready=false;}};
}
