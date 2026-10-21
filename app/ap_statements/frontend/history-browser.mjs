import {historyView,nyTimestamp} from './history.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const status=value=>({reconciled:'Reconciled',reviewed:'Reviewed · limits remain',follow_up:'Follow-up'})[value]||value;

// Read metadata only. No original PDFs or revision evidence are prefetched.
export async function loadHistoryIndex(readPage){
  const items=new Map(),seen=new Set();let cursor=null;
  do{
    const page=await readPage(cursor);
    if(!Array.isArray(page?.items)||!(page.nextCursor===null||typeof page.nextCursor==='string'))throw Error('Saved history is incomplete. Retry loading.');
    for(const item of page.items){if(!item.id||!item.statementId||!item.vendor)throw Error('Saved history is incomplete. Retry loading.');items.set(item.id,item);}
    cursor=page.nextCursor;
    if(cursor){if(seen.has(cursor)||!page.items.length)throw Error('Saved history is incomplete. Retry loading.');seen.add(cursor);}
  }while(cursor);
  return [...items.values()];
}
export function historyVendors(items){
  const vendors=new Map();for(const item of items)vendors.set(item.vendor,(vendors.get(item.vendor)||0)+1);
  return [...vendors].map(([vendor,count])=>({vendor,count})).sort((a,b)=>a.vendor.localeCompare(b.vendor));
}
export function filterHistory(items,filters={}){
  return items.filter(item=>['vendor','statementDate','initials','status'].every(key=>!filters[key]||item[key]===filters[key])&&
    (!filters.completedFrom||Date.parse(item.completedAt)>=Date.parse(filters.completedFrom))&&
    (!filters.completedTo||Date.parse(item.completedAt)<=Date.parse(filters.completedTo)))
    .sort((a,b)=>Date.parse(b.completedAt)-Date.parse(a.completedAt)||b.id.localeCompare(a.id));
}
export function vendorDirectoryHTML(items,query=''){
  const vendors=historyVendors(items).filter(item=>item.vendor.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return `<div class="vendor-directory">${vendors.map(({vendor,count})=>`<button class="panel vendor-directory-card" data-action="vendor-history-open" data-vendor="${esc(vendor)}"><strong>${esc(vendor)}</strong><span>${count} saved review${count===1?'':'s'}</span><small>View previous statements →</small></button>`).join('')}${!vendors.length?'<p class="empty">No saved vendors match this search.</p>':''}</div>`;
}
export function historyBrowserHTML(items,filters={},limit=50,{showVendors=true}={}){
  const rows=filterHistory(items,filters),vendors=historyVendors(items);
  if(!showVendors)return historyView({items:rows.slice(0,limit),nextCursor:rows.length>limit?'local':null});
  return `<div class="history-browser"><aside class="history-vendors panel"><h2>Vendors</h2><nav aria-label="Statement vendors"><button data-action="history-vendor" data-vendor="" ${!filters.vendor?'aria-current="true"':''}>All vendors <span>${items.length}</span></button>${vendors.map(({vendor,count})=>`<button data-action="history-vendor" data-vendor="${esc(vendor)}" ${filters.vendor===vendor?'aria-current="true"':''}><span>${esc(vendor)}</span><small>${count}</small></button>`).join('')}</nav></aside><div class="history-results">${historyView({items:rows.slice(0,limit),nextCursor:rows.length>limit?'local':null})}</div></div>`;
}

// A small in-memory thumbnail cache, cleared when AP closes. Never localStorage.
export function createHistoryPreview({loadPdf,paint,onChange}){
  const state={item:null,pinned:false,phase:'idle',image:null,error:null},cache=new Map();let token=0,disposed=false;
  const emit=()=>{if(!disposed)onChange(state);};
  function hide(force=false){if(state.pinned&&!force)return;token++;Object.assign(state,{item:null,pinned:false,phase:'idle',image:null,error:null});emit();}
  async function show(item,{pinned=false}={}){
    if(disposed)return;
    if(state.item?.id===item.id&&state.phase!=='error'){state.pinned||=pinned;emit();return;}
    const current=++token;Object.assign(state,{item,pinned,phase:'loading',image:null,error:null});emit();
    try{
      let image=cache.get(item.statementId);
      if(!image){const file=await loadPdf(item.statementId);if(disposed||token!==current)return;image=await paint(file);}
      if(disposed||token!==current)return;
      if(!/^data:image\/(?:png|jpeg);base64,/.test(image))throw Error('The PDF preview could not be rendered.');
      cache.delete(item.statementId);cache.set(item.statementId,image);if(cache.size>4)cache.delete(cache.keys().next().value);
      Object.assign(state,{phase:'ready',image});emit();
    }catch(error){if(!disposed&&current===token){Object.assign(state,{phase:'error',error:error.message,image:null});emit();}}
  }
  return {state,show,hide,dispose(){hide(true);cache.clear();disposed=true;token++;}};
}
export function historyPreviewHTML(state){
  if(!state.item)return '';
  const item=state.item;
  return `<section class="history-preview" role="dialog" aria-label="Statement quick preview" tabindex="-1"><header><div><strong>${esc(item.vendor)}</strong><small>${esc(item.filename)}</small></div><button class="close" data-action="history-preview-close" aria-label="Close preview">×</button></header><div class="history-preview-meta"><span>Statement: ${esc(item.statementDate||'Not supplied')}</span><span>${esc(status(item.status))} · ${esc(item.initials)}</span><small>Reviewed ${esc(nyTimestamp(item.completedAt))}</small></div><div class="history-preview-page" aria-live="polite">${state.phase==='ready'?`<img src="${esc(state.image)}" alt="First page of ${esc(item.filename)}">`:state.phase==='error'?`<p>Original PDF preview unavailable.</p><button class="button small" data-action="history-preview-retry">Retry preview</button>`:'<p role="status"><span class="spinner" aria-hidden="true"></span>Loading private PDF…</p>'}</div><footer><small>Page 1 · read-only preview</small><button class="button small primary" data-action="history-open" data-event="${esc(item.id)}">View revision</button></footer></section>`;
}
