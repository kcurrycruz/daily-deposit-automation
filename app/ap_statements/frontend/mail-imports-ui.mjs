import {nyTimestamp} from './history.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={queued:'Queued',scanning:'Scanning',awaiting_review:'Awaiting review',needs_attention:'Needs attention',already_imported:'Already imported',skipped:'Skipped'};
const reasons={similar:'Similar statement found. Review the saved copy before choosing.',waiting_source:'Upload a current BILL export to compare this statement.',storage:'Private storage is full or unavailable. Check storage before retrying.',exhausted:'Three attempts failed. Review this import before retrying.',wrong_account:'The connected Gmail account changed. Reconnect the expected account.',withdrawn:'The email or attachment is no longer available under this label.',unreadable:'The PDF could not be read reliably. Open the original and upload it manually if needed.',historical:'This older email needs your choice before importing.',auth:'Gmail access needs to be reconnected.'};
const button=(action,label,id='',disabled=false)=>`<button type="button" class="button small" data-action="${action}" data-id="${esc(id)}" ${disabled?'disabled':''}>${label}</button>`;
function statusHTML(s){
 if(!s.loaded&&!s.error)return '<span role="status">Checking email imports…</span>';
 const c=s.connection,counts=s.counts||{};
 return `${s.error?`<div class="notice amber" role="alert">${esc(s.error)} ${button('mail-refresh','Refresh')} ${button('mail-retry-last','Retry last action')}</div>`:''}
 ${!c?'<p>Email imports are not connected yet. You can still upload statements manually.</p>':`<div class="mail-status-line"><div><strong>${esc(c.label||'AP Statements')}</strong><small>${esc(c.email||'')} · ${c.paused?'Paused':'Automatic imports on'}</small></div>${button('mail-pause',c.paused?'Resume imports':'Pause imports','',s.busy)}</div>
 <p>${Number(counts.queued)||0} queued · ${Number(counts.scanning)||0} scanning · ${(Number(counts.needs_attention)||0)+(Number(counts.message_attention)||0)} need attention</p>
 <small>Last successful check: ${esc(c.lastSuccessAt?nyTimestamp(c.lastSuccessAt):'Waiting for first check')}. New mail is checked about every five minutes. Pausing stops new scans; an active scan may finish.</small>
 ${c.error?`<p class="notice amber">${esc(reasons[c.error]||'The last email check did not finish. Retry or check the connection.')}</p>`:''}`}`;
}
function rowsHTML(s){return (s.items||[]).map(r=>`<article class="mail-receipt"><div><strong>${esc(r.filename)}</strong><small>${esc(r.sender)} ${r.subject?`· ${esc(r.subject)}`:''}</small><small>Received: ${esc(r.received_at?nyTimestamp(r.received_at):'Not supplied')} · Imported: ${esc(r.imported_at?nyTimestamp(r.imported_at):'Not imported yet')}</small></div>
 <div><span class="badge ${r.status==='awaiting_review'?'blue':r.status==='needs_attention'?'amber':''}">${esc(labels[r.status]||'Needs attention')}</span>
 ${r.preliminary_available||r.status==='awaiting_review'?'<small>Preliminary comparison · check the PDF before completing.</small>':''}
 ${r.preliminary?.freshness?.stale?'<small class="mail-warning">The saved BILL export is over a week old. Update it before relying on the comparison.</small>':''}
 ${r.preliminary?.waitingForBill?'<small class="mail-warning">Waiting for saved BILL data. Upload a BILL export to compare invoices.</small>':''}
 ${r.preliminary?.rangeRefreshPending?'<small class="mail-warning">The saved BILL range needs refreshing. Excluded records require archive review.</small>':''}
 ${r.reason?`<p>${esc(reasons[r.reason]||'This import needs review before continuing.')}</p>`:''}
 ${r.assessment?.kind==='overlap'?`<small>${Number(r.assessment.added)||0} new · ${Number(r.assessment.repeated)||0} repeated invoices. The whole incoming statement is retained.</small>`:''}</div>
 <div class="action-row">${r.statement_id?button('mail-review','Open statement',r.id):''}${r.original_available?button('mail-preview','Original PDF',r.id):''}
 ${r.status==='needs_attention'&&r.reason==='similar'?`${r.assessment?.match?.id?button('mail-existing','View existing',r.id):''}${button('mail-use-existing','Use saved copy',r.id,s.busy)}${button('mail-import-separate','Import separately',r.id,s.busy)}${button('mail-skip','Skip',r.id,s.busy)}`:r.status==='needs_attention'?button('mail-retry','Retry scan',r.id,s.busy):''}</div></article>`).join('')||'<p>No email PDFs have been imported yet. Forward a statement into the selected Gmail label, or upload it manually.</p>';}
function messagesHTML(s){return (s.messages||[]).map((r,i)=>`<article class="mail-receipt"><div><strong>${esc(r.subject||'Email needs attention')}</strong><small>${esc(r.sender)} · Received ${esc(r.received_at?nyTimestamp(r.received_at):'Not supplied')}</small><p>${esc(reasons[r.error_code]||'No reliable PDF could be queued from this email.')}</p></div><div class="action-row">${button('mail-message-retry','Review / retry email',i,s.busy)}${button('mail-message-skip','Skip email',i,s.busy)}</div></article>`).join('');}
export function mailImportsHTML(s,{compact=false}={}){
 if(!s?.enabled)return '';
 if(compact)return `<section class="panel mail-summary"><strong>Email imports</strong><span data-mail-status>${s.loaded?`${Number(s.counts?.queued)||0} queued · ${Number(s.counts?.scanning)||0} scanning · ${Number(s.counts?.awaiting_review)||0} awaiting review`:'Checking imports…'}</span>${button('mail-open','View email imports')}</section>`;
 return `<section class="panel mail-imports"><div class="panel-title"><h2>Email imports</h2>${button('mail-refresh','Refresh')}</div><div data-mail-status>${statusHTML(s)}</div>
 <div data-mail-rows>${rowsHTML(s)}</div><div data-mail-more>${s.nextCursor?button('mail-more','Load older imports'):''}</div>
 <div data-mail-messages>${messagesHTML(s)}</div><div data-mail-message-more>${s.messageCursor?button('mail-message-more','More emails needing attention'):''}</div>
 <details class="mail-history"><summary>Import earlier emails</summary><p>New arrivals are imported automatically. Choose a date range to import older emails from this label. Duplicate checks still apply.</p>
 <form id="mail-history-form"><label for="mail-history-after">Received from (New York)</label><input id="mail-history-after" type="date" required>
 <label for="mail-history-before">Received before (New York)</label><input id="mail-history-before" type="date" required>
 <label for="mail-history-count">Maximum emails</label><input id="mail-history-count" type="number" min="1" max="1000" value="100" required>
 ${button('mail-history','Review import scope')}</form></details>
 <p class="mail-limitation">Email scans are preliminary. They do not verify payment settlement. Credits absent from your BILL export still need manual checking in BILL.</p></section>`;
}
export function patchMailImports(root,s,{compact=false}={}){
 if(!root)return;
 if(!s?.enabled){root.replaceChildren();return;}
 const template=root.ownerDocument.createElement('template');template.innerHTML=mailImportsHTML(s,{compact});
 if(!root.querySelector(compact?'.mail-summary':'.mail-imports')){root.replaceChildren(template.content);return;}
 const doc=root.ownerDocument,focused=root.contains(doc.activeElement)?doc.activeElement:null;
 const focus=focused?.dataset?.action?{action:focused.dataset.action,id:focused.dataset.id}:null;
 const top=root.scrollTop;
 for(const attr of ['status','rows','messages','more','message-more']){
  const selector=`[data-mail-${attr}]`,current=root.querySelector(selector),next=template.content.querySelector(selector);
  if(current&&next&&current.innerHTML!==next.innerHTML)current.innerHTML=next.innerHTML;
 }
 root.scrollTop=top;
 if(focus&&!root.contains(focused)){const replacement=[...root.querySelectorAll('[data-action]')].find(el=>el.dataset.action===focus.action&&el.dataset.id===focus.id);replacement?.focus({preventScroll:true});}
}
