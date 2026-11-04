// Independent status polling. This controller never reloads or renders the workspace.
export function createMailImports(client,{capability=0,onChange=()=>{},onImported=async()=>{},hasUnsaved=()=>false,
 visible=()=>globalThis.document?.visibilityState!=='hidden',setTimeoutFn=setTimeout,clearTimeoutFn=clearTimeout}={}){
 const empty=()=>({enabled:false,loaded:false,connection:null,counts:{},items:[],messages:[],nextCursor:null,messageCursor:null,error:null,busy:false});
 const state=empty();state.enabled=capability===1;
 let disposed=false,epoch=0,timer=null,inFlight=null,writeFlight=false,failures=0,lastWrite=null,expanded=false;
 const adopted=new Set();
 const emit=()=>{if(!disposed)onChange(state);};
 const clear=()=>{if(timer!==null)clearTimeoutFn(timer);timer=null;};
 function schedule(){clear();if(!disposed&&state.enabled&&visible())timer=setTimeoutFn(()=>{timer=null;load();},Math.min(300000,30000*2**Math.min(failures,4)));}
 function setCapability(value){
  const enabled=value===1;if(enabled===state.enabled)return;
  epoch++;clear();Object.assign(state,empty(),{enabled});adopted.clear();lastWrite=null;expanded=false;emit();
 }
 const mergeRows=(head,tail)=>[...new Map([...head,...tail].map(row=>[row.id,row])).values()].sort((a,b)=>(Date.parse(b.discovered_at)||0)-(Date.parse(a.discovered_at)||0));
 async function adoptRows(rows,token){
  if(hasUnsaved())return;
  const ids=[...new Set(rows.filter(r=>r.status==='awaiting_review'&&r.statement_id&&!adopted.has(r.statement_id)).map(r=>r.statement_id))];
  for(let n=0;n<ids.length;n+=50){const batch=ids.slice(n,n+50);await onImported(batch);if(disposed||token!==epoch)return;batch.forEach(id=>adopted.add(id));}
 }
 async function load(){
  if(disposed||!state.enabled||!visible())return state;
  if(inFlight)return inFlight;
  const token=epoch;
  const work=(async()=>{
   try{
    const status=await client.request('mail_status',{});
    if(disposed||token!==epoch)return state;
    const [receipts,messages]=await Promise.all([client.request('mail_list',{limit:50}),client.request('mail_messages',{limit:50})]);
    if(disposed||token!==epoch)return state;
    if(status.connection?.id===state.connection?.id&&status.connection?.generation<state.connection.generation)return state;
    const newHead=receipts.items.some(row=>!state.items.some(old=>old.id===row.id));
    Object.assign(state,status,{items:expanded?mergeRows(receipts.items,state.items):receipts.items,messages:messages.items,
     nextCursor:!expanded||newHead?receipts.nextCursor:state.nextCursor,messageCursor:messages.nextCursor,loaded:true,error:lastWrite?state.error:null});failures=0;
    await adoptRows(state.items,token);if(disposed||token!==epoch)return state;
    emit();
   }catch(error){
    if(disposed||token!==epoch)return state;
    if(error.code==='denied'||error.code==='mail_denied'){
     epoch++;clear();Object.assign(state,empty(),{locked:true});adopted.clear();lastWrite=null;emit();return state;
    }
    failures++;state.error=error.message||'Email imports are unavailable. Try again.';emit();
   }finally{if(token===epoch&&!disposed)schedule();}
   return state;
  })();inFlight=work;
  try{return await work;}finally{if(inFlight===work)inFlight=null;}
 }
 async function perform(action,payload,requestId=crypto.randomUUID()){
  if(disposed||!state.enabled||writeFlight)throw Error('Email imports are unavailable or another action is finishing.');
  epoch++;clear();writeFlight=true;state.busy=true;state.error=null;
  const current={action,payload:structuredClone(payload),requestId};lastWrite=current;emit();
  try{
   if(inFlight)await inFlight;
   if(disposed)throw Error('AP is locked.');
   const result=await client.request(action,current.payload,{requestId});
   if(disposed)return;
   lastWrite=null;return result;
  }catch(error){if(!disposed){state.error=error.message||'This import action was not saved. Retry the same action.';emit();}throw error;}
  finally{writeFlight=false;state.busy=false;if(!disposed){emit();await load();}}
 }
 async function more(kind){
  if(disposed||state.busy||inFlight)return;
  const messages=kind==='messages',cursor=state[messages?'messageCursor':'nextCursor'];if(!cursor)return;
  const token=epoch;clear();
  const work=(async()=>{
   const page=await client.request(messages?'mail_messages':'mail_list',{limit:50,cursor});
   if(disposed||token!==epoch)return;
   if(messages)state.messages=[...new Map([...state.messages,...page.items].map(row=>[row.connection_id+':'+row.message_id,row])).values()];
   else{expanded=true;state.items=mergeRows(page.items,state.items);await adoptRows(page.items,token);}
   if(disposed||token!==epoch)return;
   state[messages?'messageCursor':'nextCursor']=page.nextCursor;emit();
  })();inFlight=work;
  try{return await work;}finally{if(inFlight===work)inFlight=null;if(!disposed)schedule();}
 }
 function dispose(){disposed=true;epoch++;clear();Object.assign(state,empty());adopted.clear();lastWrite=null;onChange(state);}
 return {state,load,setCapability,dispose,more,
  visibilityChanged(){clear();if(visible())return load();},
  pause(paused){const c=state.connection;if(!c)throw Error('Email imports are not connected.');return perform('mail_pause',{connection_id:c.id,expected_version:c.version,paused});},
  retry(row){return perform('mail_retry',{receipt_id:row.id,expected_version:row.version});},
  importHistory(bounds){const c=state.connection;if(!c)throw Error('Email imports are not connected.');return perform('mail_history',{connection_id:c.id,expected_version:c.version,...bounds});},
  resolveSimilar(row,choice){return perform('mail_choice',{receipt_id:row.id,expected_version:row.version,choice});},
  messageChoice(row,choice){return perform('mail_message_'+choice,{connection_id:row.connection_id,message_id:row.message_id,expected_version:row.version});},
  async previewOriginal(id){if(disposed)throw Error('AP is locked.');const token=epoch,result=await client.request('mail_preview',{receipt_id:id});if(disposed||token!==epoch)throw Error('The import changed. Try preview again.');return result;},
  retryLast(){if(!lastWrite)throw Error('No import action needs retrying.');return perform(lastWrite.action,lastWrite.payload,lastWrite.requestId);},
 };
}
