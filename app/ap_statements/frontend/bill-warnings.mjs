const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function billWarningsHTML(state){
 return `<section class="bill-warning-details" aria-label="BILL source warnings"><strong>${esc(state.label)}</strong><p>${state.items.length.toLocaleString()} of ${Number.isInteger(state.total)?state.total.toLocaleString():'…'} warnings loaded. Source row numbers refer to the original CSV.</p>${state.loading?'<p role="status">Loading warning details…</p>':''}${state.error?'<p role="alert">Warning details are unavailable. Your saved data is unchanged. Retry loading the details.</p>':''}<ol>${state.items.map(w=>`<li><strong>CSV row(s) ${esc(w.rows)}</strong><p>${esc(w.reason)}</p></li>`).join('')}</ol>${state.error||state.nextCursor?`<button class="button small" data-action="bill-warnings-more" ${state.loading?'disabled':''}>${state.error?'Retry warning details':'Load more warnings'}</button>`:''}</section>`;
}
export function createBillWarnings(client,{onChange=()=>{}}={}){
 let token=0;const state={importId:null,label:'',items:[],nextCursor:null,total:null,loading:false,error:null};
 const cursors=new Set();
 async function load(source,{more=false}={}){
  const same=source.id===state.importId;
  if(same&&state.loading)return;
  if(same&&more&&state.total!==null&&state.nextCursor===null&&!state.error)return;
  if(!same||!more){Object.assign(state,{importId:source.id,label:source.label,items:[],nextCursor:null,total:null});cursors.clear();}
  const current=++token,cursor=state.nextCursor;state.loading=true;state.error=null;onChange(state);
  try{const page=await client.request('bill_warnings_page',{import_id:source.id,cursor,limit:500});
   if(current!==token)return;
   if(page.importId!==source.id||!Array.isArray(page.warnings)||!Number.isSafeInteger(page.total)||page.total<0||page.total>750000||state.total!==null&&state.total!==page.total||page.nextCursor!==null&&typeof page.nextCursor!=='string')throw Error('Incomplete warning details');
   if(page.nextCursor&&(cursors.has(page.nextCursor)||!page.warnings.length))throw Error('Incomplete warning details');
   if(page.warnings.some(w=>typeof w.rows!=='string'||typeof w.reason!=='string')||state.items.length+page.warnings.length>page.total||page.nextCursor===null&&state.items.length+page.warnings.length!==page.total)throw Error('Incomplete warning details');
   state.items.push(...page.warnings);state.total=page.total;state.nextCursor=page.nextCursor;if(page.nextCursor)cursors.add(page.nextCursor);
  }catch(error){if(current===token)state.error=error.message;}
  finally{if(current===token){state.loading=false;onChange(state);}}
 }
 return {state,load,dispose(){token++;state.items=[];}};
}
