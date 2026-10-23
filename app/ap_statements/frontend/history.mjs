import {dateISO} from './core.mjs';
import {statementDateHeader,reviewStatusHTML} from './statement-list.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const decisions=new Set(['Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed']);
export function completionPayload({doc,resolutions,results,initials,notes='',expectedVersion}){
  const normalized=String(initials||'').trim().toUpperCase();if(!/^[A-Z]{1,10}$/.test(normalized))throw Error('Reviewer initials must contain one to ten letters.');
  if(!doc.confirmed||!doc.rows.length||!results?.length)throw Error('Confirm the extraction before marking reviewed.');
  if(results.some(row=>row.status!=='matched'&&!decisions.has(resolutions?.[row.id]?.decision)))throw Error('Record a review decision for each unresolved item. Notes are optional.');
  return {statement_id:doc.id,expected_version:expectedVersion,initials:normalized,notes:String(notes)};
}
export function nyTimestamp(value){const date=new Date(value);return Number.isNaN(date.getTime())?'Not supplied':new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}).format(date);}
function midnightNY(date){
  const target=Date.parse(`${date}T00:00:00Z`);let guess=target;
  const format=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  for(let i=0;i<3;i++){const parts=Object.fromEntries(format.formatToParts(new Date(guess)).map(p=>[p.type,p.value]));const wall=Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day),Number(parts.hour),Number(parts.minute),Number(parts.second));guess+=target-wall;}
  return guess;
}
export function historyFilters(value={}){
  const filters={};for(const key of ['vendor','statementDate','initials','status'])if(value[key]?.trim())filters[key]=value[key].trim();
  if(filters.initials){filters.initials=filters.initials.toUpperCase();if(!/^[A-Z]{1,10}$/.test(filters.initials))throw Error('Enter valid reviewer initials.');}
  if(filters.statementDate&&!dateISO(filters.statementDate))throw Error('Enter a valid statement date.');
  for(const key of ['completedFrom','completedTo'])if(value[key]){
    const day=dateISO(value[key]);if(!day)throw Error('Enter a valid completion date.');
    const next=new Date(Date.parse(`${day}T12:00:00Z`)+86400000).toISOString().slice(0,10);
    filters[key]=new Date(key==='completedTo'?midnightNY(next)-1:midnightNY(day)).toISOString();
  }
  if(filters.completedFrom&&filters.completedTo&&filters.completedFrom>filters.completedTo)throw Error('Completion date range is reversed.');
  return filters;
}
export function historyView(page,direction='desc',{canRereview=false}={}){
 return `<section class="panel"><div class="panel-title"><h2>Previous Statements</h2><small>Saved review history</small></div><p class="history-hint">Hover for a first-page preview, or choose Quick preview. Reviewer initials are self-reported. View revision opens the evidence saved at that time. Resolved items reflect review progress, not payment settlement.</p><div class="table-wrap"><table class="main-table"><thead><tr><th>Vendor / statement</th>${statementDateHeader(direction,'history')}<th>Reviewer initials</th><th>Status</th><th>Completed (New York)</th><th></th></tr></thead><tbody>${page.items.map(item=>`<tr data-history-preview="${esc(item.id)}"><td><strong>${esc(item.vendor)}</strong><small style="display:block">${esc(item.filename)}</small>${item.notes?`<small style="display:block">${esc(item.notes)}</small>`:''}</td><td>${esc(item.statementDate||'Not supplied')}</td><td>${esc(item.initials)}</td><td>${reviewStatusHTML(item.status,item.progress)}</td><td>${esc(nyTimestamp(item.completedAt))}</td><td><div class="action-row"><button class="button small" data-action="history-preview" data-event="${esc(item.id)}" aria-label="Quick preview ${esc(item.filename)}">Quick preview</button><button class="button small" data-action="history-open" data-event="${esc(item.id)}">View revision</button>${canRereview?`<button class="button small primary" data-action="history-rereview" data-event="${esc(item.id)}">Re-review</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>${!page.items.length?'<div class="empty">No completed statements match these filters.</div>':''}${page.nextCursor?'<div class="table-foot"><button class="button" data-action="history-more">Load more</button></div>':''}</section>`;
}
