import {reconcile,groupInvoices,vendorKey,MATCH_RULE_VERSION,comparisonInputKey} from './core.mjs';
import {createComparisonSource} from './comparison-source.mjs';
import {LIMITS} from './shared-client.mjs';
import {reviewNotesOnly} from './session.mjs';
import {createDuplicateBills} from './duplicate-bills.mjs';
const clone=value=>JSON.parse(JSON.stringify(value));
const unloaded=()=>({loaded:false,simulated:false,records:[],label:'Loading shared BILL records…'});
const fields=(value,names)=>Object.fromEntries(names.split(' ').filter(k=>value[k]!==undefined).map(k=>[k,value[k]]));
export function comparisonSnapshot(doc,provider,mappings){return reconcile(doc,provider,mappings).map(row=>fields(row,'id invoiceNumber kind originalAmount outstanding activity date confidence duplicate page status reason candidates matchMethod referenceRule statementId vendor simulated'));}
export function legacyMigrationPreview(session,mappings={}){
  const real=(session?.statements||[]).filter(doc=>!doc.demo);
  return {statements:real.map(doc=>({doc:{...clone(doc),confirmed:false},resolutions:reviewNotesOnly(Object.fromEntries(Object.entries(session.resolutions||{}).filter(([id])=>doc.rows.some(row=>row.id===id))))})),
    originalsAvailable:0,importMetadata:session?.provider?.loaded&&!session.provider.simulated?fields(session.provider,'label asOf refreshedAt sourceFormat'):null,mappings:clone(mappings)};
}
export function createSharedWorkspace(client,{onState=()=>{},onSaveState=()=>{}}={}){
  const state={ready:false,provider:unloaded(),importId:null,activeImport:null,capabilities:{},statements:[],details:new Map(),mappings:{},mappingVersions:{},resolutions:{}};
  const localFiles=new Map(),preparations=new Map();let disposed=false,loaded=false;
  let comparison=null,adoption=0,sourceUnavailableError=null;
  let foreground=0,externalBusy=false;
  const duplicates=createDuplicateBills(client,{onChange:()=>{if(loaded&&!disposed)onState(state,{reason:'duplicates'});}});
  const updateDuplicateBusy=()=>duplicates.setBusy(foreground>0||externalBusy);
  async function inForeground(work){foreground++;updateDuplicateBusy();try{return await work();}finally{foreground--;updateDuplicateBusy();}}
  function check(){if(disposed)throw Error('AP is locked.');}
  const emit=()=>{check();if(state.ready&&loaded)duplicates.adoptSource({importId:state.importId,importVersion:state.importVersion,capability:state.capabilities.duplicateBills});onState(state);};
  function makeComparison(){const source=createComparisonSource(client,{onChange:provider=>{if(comparison===source&&!disposed){state.provider=sourceUnavailableError?{...provider,error:sourceUnavailableError}:provider;if(loaded)emit();}}});return source;}
  async function ensureComparisons(doc){
    check();if(doc.reviewMode==='manual')return state.details.get(doc.id)?.results||null;
    if(state.provider.error)throw Error('Current BILL data is unavailable. Retry the comparison before saving or completing.');
    if(!comparison||!state.provider.loaded)return null;
    const detail=state.details.get(doc.id);
    if(detail?.completed||detail?.readOnly)return null;
    const info=state.activeImport;
    if(detail&&detail.importId!==state.importId){
      detail.importId=state.importId;detail.importInfo=info;detail.importLabel=info?.metadata?.label||'';
      // Keep human notes, but decisions against superseded evidence need review.
      for(const row of groupInvoices(doc))if(state.resolutions[row.id])state.resolutions[row.id]={note:state.resolutions[row.id].note||''};
      comparison.invalidate(doc.id);
    }
    const result=await inForeground(()=>comparison.ensure(doc,state.mappings,{importInfo:info}));check();
    const scope=state.provider.scopes?.[doc.id];
    if(info&&(!scope?.complete||scope.importId!==info.id||scope.inputKey!==comparisonInputKey(doc,state.mappings)))throw Error('The BILL comparison changed or is unavailable. Retry before saving.');
    return result;
  }
  async function prepareStatement(doc){
    check();const detail=state.details.get(doc.id);
    if(doc.reviewMode==='manual'||detail?.completed||detail?.readOnly)return null;
    if(!comparison)return ensureComparisons(doc);
    const token=Symbol();preparations.set(doc.id,token);let source=comparison;const sourceUnavailable=!!state.provider.error;
    comparison.invalidate(doc.id);
    try{
      const current=await client.request('bill_current',{});check();
      if(preparations.get(doc.id)!==token)return null;
      if(sourceUnavailable||state.provider.error||current.importId!==state.importId||current.importVersion!==state.importVersion)await adoptImport(current);
      if(preparations.get(doc.id)!==token)return null;
      source=comparison;
      return await ensureComparisons(doc);
    }catch(error){
      if(preparations.get(doc.id)!==token||comparison!==source)return null;
      const scope=state.provider.scopes?.[doc.id];if(scope){scope.complete=false;scope.error=error.message;emit();}
      throw error;
    }finally{if(preparations.get(doc.id)===token)preparations.delete(doc.id);}
  }
  async function refreshComparisons(id){
    check();const detail=state.details.get(id),doc=state.statements.find(item=>item.id===id);
    if(!detail||!doc||detail.completed||detail.readOnly)throw Error('Open an editable statement before comparing again.');
    const manual=doc.reviewMode==='manual',previous=manual?clone(detail):null;
    const ids=new Set((manual?detail.results:groupInvoices(doc)).map(row=>row.id));
    const reviews=Object.fromEntries([...ids].filter(id=>state.resolutions[id]).map(id=>[id,clone(state.resolutions[id])]));
    const notes=reviewNotesOnly(reviews);
    if(manual)doc.reviewMode='latest';
    Object.assign(state.resolutions,notes);
    try{
      if(comparison){await prepareStatement(doc);check();}
      else {detail.importId=state.importId;detail.importInfo=state.activeImport;}
      if(manual&&!state.provider.loaded)throw Error('Latest BILL data is unavailable. The manual review has been retained.');
      emit();return state.provider.scopes?.[id]||null;
    }catch(error){
      if(manual&&!disposed&&state.details.get(id)===detail){
        doc.reviewMode='manual';
        Object.assign(detail,{...previous,doc});
        for(const [rowId,review] of Object.entries(reviews)){
          if(JSON.stringify(state.resolutions[rowId])===JSON.stringify(notes[rowId]))state.resolutions[rowId]=review;
        }
        emit();
      }
      throw error;
    }
  }
  async function adoptImport(result){
    check();const token=++adoption;
    const current=await client.request('bill_current',{});check();
    if(token!==adoption||!Number.isSafeInteger(current.importVersion)||current.importVersion<(state.importVersion||0))throw Error('The BILL data changed in a newer update. Retry loading current data.');
    const info=current.importId?{id:current.importId,metadata:current.metadata,record_count:current.recordCount,storage_format:current.storageFormat}:null;
    const pending=makeComparison();
    try{const provider=await pending.loadDirectory(info);check();
      const verified=await client.request('bill_current',{});check();
      if(token!==adoption||verified.importVersion!==current.importVersion||verified.importId!==current.importId)throw Error('The BILL data changed in a newer update. Retry loading current data.');
      // Do not display previous source scopes while new comparisons are loading.
      provider.scopes={};
      comparison?.dispose();comparison=pending;sourceUnavailableError=null;state.provider=provider;state.activeImport=info;state.importId=info?.id||null;state.importVersion=current.importVersion;
      for(const doc of state.statements)ensureComparisons(doc).catch(()=>{});
      emit();return provider;
    }catch(error){pending.dispose();throw error;}
  }
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
      try{const result=await inForeground(()=>operation(request));check();onSaveState('saved');return result;}
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
    return {...metadata,records,recordCount:records.length,loaded:true,simulated:false};
  }
  async function load({replace=false}={}){
    adoption++;
    check();if(loaded&&!replace)return state;
    // Work is assembled separately. A failed refresh cannot replace unsaved edits.
    const summaries=[],cursors=new Set();let cursor=null,home,pendingComparison;
    try{
      do{const page=await client.request('bootstrap',{cursor,limit:50});check();home??=page;
        if(page.activeImport?.id!==home.activeImport?.id)throw Error('The shared import changed while loading. Retry.');
        summaries.push(...page.statements);cursor=page.nextCursor;if(cursor&&cursors.has(cursor))throw Error('Shared statement list is incomplete.');cursors.add(cursor);
      }while(cursor);
      const snapshotCapable=home.capabilities?.billSnapshots===2;
      pendingComparison=snapshotCapable?makeComparison():null;
      const details=[];for(const summary of summaries)details.push(await client.request('statement',{statement_id:summary.id}));check();
      let provider,sourceError;
      try{provider=snapshotCapable?await pendingComparison.loadDirectory(home.activeImport):(home.activeImport?await loadProvider(home.activeImport.id,home.activeImport.metadata):{...unloaded(),label:'No BILL records imported'});}
      catch(error){
        check();
        if(!['unavailable','timeout','bill_incomplete'].includes(error.code)||!details.some(detail=>detail.doc.reviewMode==='manual'))throw error;
        sourceError=error;
        provider={...home.activeImport?.metadata,...unloaded(),label:home.activeImport?.metadata?.label||'Saved BILL data',error:'Current BILL data is unavailable. Pinned manual reviews remain available.'};
      }
      state.statements=[];state.details.clear();state.resolutions={};state.mappings=home.mappings;state.mappingVersions=home.mappingVersions||{};
      sourceUnavailableError=sourceError?provider.error:null;state.provider=provider;state.importId=home.activeImport?.id||null;state.importVersion=home.importVersion||0;
      comparison?.dispose();comparison=pendingComparison;state.activeImport=home.activeImport;state.capabilities=home.capabilities||{};
      for(const detail of details){if(detail.doc.reviewMode!=='manual'&&(!snapshotCapable&&detail.importId!==state.importId||JSON.stringify(detail.mappingSnapshot||{})!==JSON.stringify(state.mappings)))detail.resolutions=reviewNotesOnly(detail.resolutions||{});adopt(detail);}
      // Initial dashboard counts must not race the scoped invoice lookups.
      if(comparison&&!sourceError){
        const checks=await Promise.allSettled(state.statements.map(doc=>ensureComparisons(doc)));check();
        const failed=checks.find(result=>result.status==='rejected');if(failed)throw failed.reason;
      }
      state.ready=true;loaded=true;emit();
      return state;
    }catch(error){if(pendingComparison&&pendingComparison!==comparison)pendingComparison.dispose();if(error.code==='denied'){dispose();state.accessDenied=true;onState(state);}else if(!loaded&&!disposed){state.ready=false;state.provider=unloaded();emit();}throw error;}
  }
  function dispose(){disposed=true;duplicates.dispose();comparison?.dispose();client.dispose();localFiles.clear();state.statements=[];state.details.clear();state.resolutions={};state.mappings={};state.mappingVersions={};state.capabilities={};state.activeImport=null;sourceUnavailableError=null;state.provider=unloaded();state.importId=null;state.ready=false;}
  async function upload(file,kind,request,attachment={}){
    if(!file||!Number.isInteger(file.size)||file.size<1||file.size>LIMITS.file)throw Error('Each PDF or CSV must be at most 20 MiB.');
    const bytes=new Uint8Array(await file.arrayBuffer());check();
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
    const begun=await request('upload_begin',{kind,filename:file.name,size:bytes.length,file_hash:hash});
    for(let at=0;at<bytes.length;at+=LIMITS.chunk){let binary='';for(const byte of bytes.subarray(at,at+LIMITS.chunk))binary+=String.fromCharCode(byte);await request('upload_chunk',{upload_id:begun.upload_id,index:at/LIMITS.chunk,data:btoa(binary)});}
    return request('upload_finish',{upload_id:begun.upload_id,...attachment});
  }
  function saveData(doc,expectedVersion,resolutions){
    const detail=state.details.get(doc.id),manual=doc.reviewMode==='manual';
    if(manual&&!detail)throw Error('Reload the pinned manual review before saving.');
    const rows=manual?detail.results:groupInvoices(doc),ids=new Set(rows.map(r=>r.id));
    return {statement_id:doc.id,expected_version:expectedVersion,doc:clone(doc),resolutions:Object.fromEntries(Object.entries(resolutions).filter(([id])=>ids.has(id))),
      import_id:manual?detail.importId:comparison?(detail?.importId||state.importId):state.importId,mapping_snapshot:clone(manual?detail.mappingSnapshot:state.mappings),results:manual?clone(detail.results):comparisonSnapshot(doc,state.provider,state.mappings),rule_version:manual?detail.ruleVersion:MATCH_RULE_VERSION};
  }
  async function saveStatement(doc,expectedVersion,{resolutions=state.resolutions}={}){
    await ensureComparisons(doc);
    const payload=saveData(doc,expectedVersion,resolutions);
    payload.resolutions=clone(payload.resolutions);
    const rowIds=new Set(payload.results.map(row=>row.id));
    const localReviews=()=>Object.fromEntries(Object.entries(state.resolutions).filter(([id])=>rowIds.has(id)));
    const reviewsAtSave=JSON.stringify(localReviews());
    return write(async request=>{
      const reply=await request('save_revision',payload);
      // The database stamps review dates. Read the exact acknowledged revision
      // instead of adopting the unstamped client payload or a colleague's edits.
      const saved=await request('statement',{statement_id:doc.id,revision_id:reply.revision_id});
      if(saved.doc.id!==doc.id||saved.revisionId!==reply.revision_id||saved.revisionVersion!==reply.version||saved.version!==reply.version||saved.completed||saved.archived)
        throw Object.assign(Error('This statement changed after saving. Reload latest before continuing; your local edits are retained.'),{code:'conflict'});
      const current=state.statements.find(item=>item.id===doc.id)||doc;
      if(JSON.stringify(current)!==JSON.stringify(payload.doc)||JSON.stringify(localReviews())!==reviewsAtSave)
        throw Object.assign(Error('Your local edits have changed since this save. They are retained; reload latest only when ready to discard them.'),{code:'conflict'});
      const detail=adopt({...saved,readOnly:false});emit();return detail;
    });
  }
  function uploadStatement(file,extract){
    localFiles.set(file,file);let extracted=null,finished=null;
    return write(async request=>{
      finished=await upload(file,'pdf',request);
      const stored=await request('statement',{statement_id:finished.statement_id});adopt(stored);emit();
      if(finished.duplicate){localFiles.delete(file);return {...stored,duplicate:true};}
      if(!extracted){try{extracted=await extract(file);}catch(error){extracted={...stored.doc,confirmed:false,warnings:[...(stored.doc.warnings||[]),`Extraction could not finish: ${error.message}. Review the original and add rows manually.`]};}}
      extracted={...extracted,id:finished.statement_id,fileSize:file.size,fileModified:file.lastModified||0,confirmed:false};
      await ensureComparisons(extracted);
      const payload=saveData(extracted,stored.version,{});
      const saved=await request('save_revision',payload);
      const detail=adopt({...stored,doc:extracted,version:saved.version,results:payload.results,importId:state.importId,mappingSnapshot:clone(state.mappings),ruleVersion:MATCH_RULE_VERSION});
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
      if(state.importId!==begun.import_id)retainManualReviews();
      state.importId=begun.import_id;state.provider=authoritative;emit();return authoritative;
    });
  }
  function saveMapping(mapping,expectedVersion){
    const payload={vendor:mapping.vendor,bill_vendor:mapping.bill_vendor,expected_version:expectedVersion};
    return write(async request=>{const reply=await request('save_mapping',payload);if(vendorKey(state.mappings[payload.vendor]||payload.vendor)!==vendorKey(payload.bill_vendor))for(const doc of state.statements.filter(d=>d.vendor===payload.vendor&&d.reviewMode!=='manual'))for(const row of groupInvoices(doc))if(state.resolutions[row.id])state.resolutions[row.id]={note:state.resolutions[row.id].note||''};state.mappings[payload.vendor]=payload.bill_vendor;state.mappingVersions[payload.vendor]=reply.version;emit();return reply;});
  }
  function retainManualReviews(){
    const ids=new Set(state.statements.filter(doc=>doc.reviewMode==='manual').flatMap(doc=>(state.details.get(doc.id)?.results||[]).map(row=>row.id)));
    state.resolutions={...reviewNotesOnly(state.resolutions),...Object.fromEntries(Object.entries(state.resolutions).filter(([id])=>ids.has(id)))};
  }
  function reopenStatement(id,expectedVersion,{mode}={}){
    check();
    if(mode!==undefined&&(!['manual','latest'].includes(mode)||state.capabilities.statementRereview!==1))return Promise.reject(Error('Statement re-review setup is unavailable. Reload the workspace.'));
    const existing=state.details.get(id);
    if(existing&&!existing.completed&&!existing.readOnly&&state.statements.some(doc=>doc.id===id))return Promise.resolve(existing);
    const payload={statement_id:id,expected_version:expectedVersion,...(mode?{review_mode:mode}:{})};
    return write(async request=>{
      const ack=await request('reopen_statement',payload);
      const detail=await request('statement',{statement_id:id,...(mode?{revision_id:ack.revision_id}:{})});
      if(mode&&(detail.doc.id!==id||detail.revisionId!==ack.revision_id||detail.revisionVersion!==ack.version||detail.version!==ack.version||detail.completed||detail.archived))throw Object.assign(Error('This statement changed while reopening. Reload the current draft; local edits are retained.'),{code:'conflict'});
      const local=state.details.get(id);
      if(mode&&local&&!local.completed&&!local.readOnly&&state.statements.some(doc=>doc.id===id))throw Object.assign(Error('An editable draft is already open. Its local edits are retained.'),{code:'conflict'});
      adopt({...detail,readOnly:false});emit();return state.details.get(id);
    });
  }
  async function originalPdf(statementId){const link=await client.request('pdf_preview',{statement_id:statementId});check();const response=await fetch(link.url,{referrerPolicy:'no-referrer'});if(!response.ok)throw Error('Original preview expired or is unavailable. Reopen to retry.');const bytes=await response.arrayBuffer();check();return new Blob([bytes],{type:'application/pdf'});}
  return {state,load,loadProvider,importBills,adoptImport,ensureComparisons,prepareStatement,refreshComparisons,uploadStatement,saveStatement,saveMapping,originalPdf,duplicates,
    setDuplicateBusy(value){externalBusy=!!value;updateDuplicateBusy();},
    attachOriginal(file,id,expectedVersion){return write(async request=>{await upload(file,'pdf',request,{statement_id:id,expected_version:expectedVersion});const detail=await request('statement',{statement_id:id});adopt(detail);emit();return detail;});},
    migrateLegacy(preview,confirmed=false){if(!confirmed)return Promise.resolve({cancelled:true});const items=clone(preview.statements);if(!items.length)return Promise.reject(Error('No real legacy statements to migrate.'));return write(async request=>{const results=[];for(const item of items)results.push(await request('migrate_legacy',{confirmed:true,statements:[item]}));await load({replace:true});return results;});},
    async completeStatement(payload){const frozen=clone(payload),detail=state.details.get(frozen.statement_id);if(!detail||detail.readOnly)throw Error('Open the current editable draft before completing.');const doc=state.statements.find(doc=>doc.id===frozen.statement_id)||detail.doc;await ensureComparisons(doc);const snapshot=saveData(doc,frozen.expected_version,state.resolutions);return write(async request=>{const saved=await request('save_revision',snapshot);const reply=await request('complete_revision',{...frozen,expected_version:saved.version});Object.assign(detail,{doc:snapshot.doc,results:snapshot.results,resolutions:snapshot.resolutions,importId:snapshot.import_id,mappingSnapshot:snapshot.mapping_snapshot,ruleVersion:snapshot.rule_version,completed:true,readOnly:true,version:reply.version});state.statements=state.statements.filter(doc=>doc.id!==frozen.statement_id);emit();return reply;});},
    extractionOnly(){state.provider={loaded:false,simulated:false,records:[],label:'Extraction-only view'};state.importId=null;retainManualReviews();emit();},
    history(filters={},cursor=null){return client.request('history_page',{filters,cursor,limit:50});},
    reopenStatement,
    archiveStatement(id,expectedVersion){return write(async request=>{const reply=await request('archive_statement',{statement_id:id,expected_version:expectedVersion});state.statements=state.statements.filter(doc=>doc.id!==id);emit();return reply;});},
    async statement(id,revisionId){check();const detail=await client.request('statement',{statement_id:id,...(revisionId?{revision_id:revisionId}:{})});check();return {...detail,readOnly:!!revisionId||detail.completed};},
    write,adopt,
    dispose};
}
