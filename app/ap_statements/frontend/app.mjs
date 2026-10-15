import { money, cents, uid, totals, groupInvoices, reconcile, statuses, toCSV, vendorKey } from './core.mjs';
import { importBillSource } from './bill-import.mjs';
import { loadSession, loadVendorMappings, reviewNotesOnly } from './session.mjs';
import {createSharedWorkspace,legacyMigrationPreview} from './shared-workspace.mjs';
import {completionPayload,historyFilters,historyView,nyTimestamp} from './history.mjs';
import { backButtonHtml, requestProgramHub } from './navigation.mjs';
import { emptyWorkspace, workflowGuide } from './guide.mjs';
import {statementComparisons,invoiceFound,completionReviews,confirmVendor,readingIssues} from './simple-flow.mjs';
import {billDataHTML,uploadReviewHTML,vendorQuestionHTML,statementOverviewHTML} from './simple-flow-view.mjs';

const icons = {
  ledger: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  flag: '<path d="M5 21V4m0 0h12l-2 4 2 4H5"/>',
  users: '<circle cx="9" cy="7" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2m1-16a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v2"/>',
  plug: '<path d="m8 3 2 4m5-4 2 4M6 7h13v3a6 6 0 0 1-6 6v5m-5-7a6 6 0 0 1-2-4V7"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4h16v-4"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  down: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  shield: '<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Zm-4 9 3 3 5-6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
  save: '<path d="M4 3h13l3 3v15H4Zm4 0v6h8V3M8 21v-7h8v7"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.ledger}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const initial = emptyWorkspace();
const state = { ...initial, view: 'statements', filter: 'all', query: '', mappings: {}, resolutions: {}, selected: null, selectedRow: null, drawerTab: 'review', page: 1, busy: false, progress: '', fraction: 0, errors: [] };
const files = new Map();
let extractor;
let toastTimer;
let priorFocus;
let renderToken = 0;
const app = document.querySelector('#app');
const overlay = document.querySelector('#overlay-root');
const browserStorage = () => { try { return window.localStorage; } catch { return null; } };
let restoredNotice = '';
let shared,saveState='loading',retryOperation=null,sharedError=null;
let historyPage={items:[],nextCursor:null},historySelection=null,activeHistoryFilters={};
let historicalDetail=null;
let migrationPreview=null,pendingAttachment=null;
function docDetail(id){return historicalDetail?.doc.id===id?historicalDetail:shared?.state.details.get(id);}
const comparisonsFor=doc=>docDetail(doc.id)?.readOnly?docDetail(doc.id).results:statementComparisons(doc,state.provider,state.mappings);
const dirty=new Set();
function ready(){if(!shared?.state.ready)throw Error('Shared workspace is not ready. Finish setup or retry loading.');}
function sharedStatus(status,error){saveState=status;sharedError=error||null;retryOperation=error?.retry||null;const badge=document.querySelector('#shared-save-status');if(badge)badge.textContent=({saving:'Saving…',saved:'Saved to shared workspace',not_saved:'Not saved',loading:'Loading shared workspace…',unsaved:'Unsaved changes'})[status]||status;overlay.querySelectorAll?.('input,textarea,select,button[data-action="resolve"],button[data-action="save-extraction"],button[data-action="confirm-extraction"],button[data-action="save-notes"],button[data-action="vendor-confirm"],button[data-action="vendor-choose"],button[data-action="confirm-reading"],button[data-action="complete-dialog"],button[data-action="complete-statement"]').forEach(el=>{if(el.id==='row-select')el.disabled=status==='saving';else if(el.id!=='page-select')el.disabled=status==='saving'||!!docDetail(state.selected)?.readOnly;});document.querySelectorAll('[data-action="upload"],[data-action="import"],[data-action="mapping"],[data-action="save-session"]').forEach(el=>{el.disabled=status==='saving'||!shared?.state.ready;});}
function receiveShared(snapshot){state.provider=snapshot.provider;state.statements=snapshot.statements;state.mappings=snapshot.mappings;state.resolutions=snapshot.resolutions;render();}
async function startShared(){if(shared||!window.hwfcSharedClient)return;shared=createSharedWorkspace(window.hwfcSharedClient,{onState:receiveShared,onSaveState:sharedStatus});try{await retrySharedLoad();}catch{}}
async function retrySharedLoad(){try{await shared.load();sharedStatus('saved');render();}catch(error){error.retry=retrySharedLoad;sharedStatus('not_saved',error);render();throw error;}}
window.addEventListener('hwfc:shared-ready',startShared);
window.addEventListener('pagehide',()=>{shared?.dispose();files.clear();state.statements=[];state.resolutions={};state.provider=emptyWorkspace().provider;overlay.innerHTML='';app.innerHTML='';},{once:true});
async function persistDoc(doc){ready();const detail=shared.state.details.get(doc.id);const result=await shared.saveStatement(doc,detail.version,{resolutions:state.resolutions});dirty.delete(doc.id);return result;}
function markDirty(){if(saveState==='saving')return;if(state.selected){dirty.add(state.selected);sharedStatus('unsaved');}}
function decorateSharedUi(){
  const nav=document.querySelector('.nav');if(nav&&!nav.querySelector('[data-action="history-view"]'))nav.insertAdjacentHTML('beforeend',`<button data-action="history-view" class="${state.view==='history'?'active':''}">${icon('clock')}Previous Statements</button>`);
  const note=document.querySelector('.local-note');if(note)note.innerHTML=`${icon('shield')}<strong>Private shared workspace</strong>Original PDFs, BILL imports and acknowledged saves are kept for your team. Initials are self-reported. Unsaved edits remain in this tab.`;
  const profile=document.querySelector('.profile small');if(profile)profile.textContent='Shared AP workspace';
  for(const button of document.querySelectorAll('[data-action="save-session"]'))button.innerHTML=`${icon('save')}Save changes`;
  for(const button of document.querySelectorAll('[data-action="clear"]'))button.textContent='Reset local view';
  const actions=document.querySelector('.top-actions');if(actions&&!document.querySelector('#shared-save-status'))actions.insertAdjacentHTML('afterbegin',`<span id="shared-save-status" role="status">${esc(({saving:'Saving…',saved:'Saved to shared workspace',not_saved:'Not saved',loading:'Loading shared workspace…',unsaved:'Unsaved changes'})[saveState])}</span>`);
  const prep=document.querySelector('.guide-preparation');if(prep&&state.statements.length)prep.innerHTML='<strong>Keep your progress</strong><p>Save changes to retain corrections and notes for the team.</p><small>Original PDFs are saved privately. Wait for a save acknowledgement before leaving.</small>';
  const content=document.querySelector('.content');document.querySelector('#shared-error')?.remove();if(content&&sharedError)content.insertAdjacentHTML('afterbegin',`<div id="shared-error" class="notice amber"><div><strong>${sharedError.code==='conflict'?'Conflict':'Not saved'}</strong><p>${esc(sharedError.message)}</p><button class="button small" data-action="retry-shared">Retry same operation</button> <button class="button small" data-action="reload-latest">Reload latest (discards unsaved edits)</button></div></div>`);
  const vendorHelp=document.querySelector('.wide-panel p');if(state.view==='vendors'&&vendorHelp)vendorHelp.textContent='Map statement names to the exact vendor names in BILL. Acknowledged mappings are shared with the team.';
  if(state.view==='history'&&content){const heading=content.querySelector('.heading h1');if(heading)heading.textContent='Previous Statements';const subtitle=content.querySelector('.heading p');if(subtitle)subtitle.textContent='Find completed work and open the exact evidence saved by your team.';content.querySelector('.connection-layout')?.remove();content.insertAdjacentHTML('beforeend',historyPanel());}
  for(const button of document.querySelectorAll('[data-action="upload"],[data-action="import"],[data-action="mapping"],[data-action="save-session"]'))if(!shared?.state.ready||saveState==='saving')button.disabled=true;
}
function historyPanel(){return `<section class="panel wide-panel history-filters"><div class="form-grid">${[['vendor','Vendor','text'],['statementDate','Statement date','date'],['initials','Reviewer initials','text'],['completedFrom','Completed from (New York)','date'],['completedTo','Completed to (New York)','date']].map(([key,label,type])=>`<label class="field">${label}<input id="history-${key}" type="${type}" value="${esc(activeHistoryFilters[key]||'')}"></label>`).join('')}<label class="field">Status<select id="history-status">${[['','All'],['reconciled','Reconciled'],['reviewed','Reviewed'],['follow_up','Follow-up']].map(([key,label])=>`<option value="${key}" ${activeHistoryFilters.status===key?'selected':''}>${label}</option>`).join('')}</select></label></div><button class="button primary" data-action="history-search">Search previous work</button></section>${historyView(historyPage)}`;}
async function refreshHistory(more=false){ready();const page=await shared.history(historyFilters(activeHistoryFilters),more?historyPage.nextCursor:null);historyPage={items:more?[...historyPage.items,...page.items]:page.items,nextCursor:page.nextCursor};render();}
const results = () => state.statements.flatMap(statement => comparisonsFor(statement));
const reviewDecision = id => historicalDetail?(historicalDetail.resolutions[id]?.decision?historicalDetail.resolutions[id]:null):(state.resolutions[id]?.decision ? state.resolutions[id] : null);
const isAttention = row => !['matched','presence'].includes(row.status) && !reviewDecision(row.id);
function invalidateReviewDecisions(rows) {
  for (const row of rows) {
    const prior = state.resolutions[row.id];
    if (prior) state.resolutions[row.id] = { note: prior.note || '' };
  }
}
function stats() {
  const rows = results();
  return { rows, total: rows.length, matched: rows.filter(r => r.status === 'matched').length, attention: rows.filter(isAttention).length, reviewed: rows.filter(r => reviewDecision(r.id)).length, balance: state.statements.reduce((s, d) => s + (d.declaredTotal ?? totals(d).sum), 0) };
}
const badge = (status, label) => `<span class="badge ${statuses[status]?.tone || 'gray'}"><span class="dot"></span>${esc(label || statuses[status]?.label || status)}</span>`;
const initials = name => name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
function vendorCell(doc) { return `<div class="vendor-cell"><div class="vendor-avatar">${esc(initials(doc.vendor))}</div><div><strong>${esc(doc.vendor)}</strong><small>${esc(doc.filename)}</small></div></div>`; }
function sourcePill() { return state.provider.loaded ? 'Saved BILL data' : 'No BILL data yet'; }
function docSummary(doc) {
  const rows = comparisonsFor(doc);
  const check = totals(doc);
  if (!doc.confirmed) return { status: 'extraction', label: rows.length ? `${rows.filter(invoiceFound).length} found · check PDF` : 'Check PDF reading' };
  if (check.difference !== 0 && check.difference !== null) return { status: 'extraction', label: 'Check statement total' };
  if (rows.every(r => r.status === 'matched') && rows.length) return { status: 'matched' };
  if (!state.provider.loaded) return { status: 'unverified' };
  if(rows.length&&!rows.some(isAttention))return {status:'presence',label:'Ready to finish'};
  return { status: 'balance', label: `${rows.filter(isAttention).length} to review` };
}
function render() {
  const data = stats();
  const title = { statements: 'Your statement workspace', exceptions: 'Focus on what needs attention', vendors: 'Keep your vendors connected', connection: 'Your saved BILL data' }[state.view];
  const subtitle = { statements: 'Upload arriving statements, check the results, and finish with your initials.', exceptions: 'Every difference has a reason. Review the evidence, then record your decision.', vendors: 'Map statement names to the vendor names used in BILL.', connection: 'Use a CSV export to compare invoices. No API access is needed for this step.' }[state.view];
  app.innerHTML = `<div class="shell"><aside class="sidebar"><div class="brand"><span class="brand-icon">${icon('ledger')}</span>Statement Desk</div>${backButtonHtml()}<div class="nav-label">Workspace</div><nav class="nav" aria-label="Workspace navigation">${[['statements','folder','Statements',state.statements.length],['exceptions','flag','Needs attention',data.attention],['connection','plug','BILL data','']].map(([view, glyph, label, count]) => `<button data-action="view" data-view="${view}" class="${state.view === view ? 'active' : ''}" ${state.view === view ? 'aria-current="page"' : ''} title="${label}">${icon(glyph)}${label}${count !== '' ? `<span class="count">${count}</span>` : ''}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="local-note">${icon('shield')}<strong>Your files stay with you</strong>PDFs are read in this browser. Save session keeps extracted rows and notes, not originals. Select PDFs again after leaving. Saved financial metadata is visible to anyone using this browser profile.</div><div class="profile"><div class="avatar">AP</div><div>Accounts payable<small>Prototype workspace</small></div></div></div></aside><main class="main"><header class="topbar"><div class="breadcrumb">AP workspace <span>/</span><strong>${state.view === 'connection' ? 'BILL connection' : state.view[0].toUpperCase() + state.view.slice(1)}</strong></div><div class="top-actions"><button class="button small subtle" data-action="save-session">${icon('save')}Save session</button><span class="connection-pill"><span class="dot"></span>${sourcePill()}</span></div></header><div class="content"><div class="heading"><div><div class="eyebrow">A clearer month-end</div><h1>${title}</h1><p>${subtitle}</p></div><div class="action-row">${(state.view === 'statements' && state.statements.length) || state.view === 'exceptions' ? `<button class="button" data-action="export">${icon('down')}Export report</button><button class="button primary" data-action="upload" ${state.busy ? 'disabled' : ''}>${icon('plus')}Upload statements</button>` : ''}</div></div>${restoredNotice ? `<div class="notice blue">${esc(restoredNotice)}</div>` : ''}${billDataHTML(state.provider)}${state.view === 'statements' || state.view === 'exceptions' ? `${workflowBody(data)}` : state.view === 'vendors' ? vendorsPanel() : state.view === 'connection' ? connectionPanel() : ''}</div></main></div>`;
  bindDropzone();
  decorateSharedUi();
}
function guidePanel() { return uploadReviewHTML(state); }
function workflowBody(data) {
  const upload=state.view==='statements'?guidePanel():'';
  if(!state.statements.length&&state.view==='statements')return upload;
  return `${upload}${metrics(data)}<section class="panel">${state.view==='statements'?statementPanel(data):exceptionPanel(data)}</section>`;
}
function goToGuideStep(step) {
  if (step === 'upload') document.querySelector('#pdf-input').click();
  if (step === 'source') { state.view = 'connection'; render(); }
  if (step === 'extraction' && state.statements.length) {
    openDoc(workflowGuide(state).documentId,null,{tab:'extraction'});
  }
  if (step === 'review' && state.statements.length) {
    const next = results().find(isAttention);
    if (next) openDoc(next.statementId, next.id);
    else { state.view = 'exceptions'; state.filter = 'all'; state.query = ''; render(); }
  }
}
function metrics(data) {
  return `<div class="metrics">${[
    ['Statements uploaded', state.statements.length, `${new Set(state.statements.map(d => d.vendor)).size} vendors in this workspace`, 'folder', ''],
    state.provider.sourceFormat === 'bill-native'
      ? ['Invoices found', data.rows.filter(invoiceFound).length, 'PDF check required · balances unverified', 'check', '']
      : ['Matched invoices', data.matched, 'Invoice and balance agree', 'check', 'good'],
    ['Needs attention', data.attention, `${data.reviewed} items reviewed by your team`, 'flag', 'warn'],
    ['Statement balances', money(data.balance), 'Reported totals across uploaded statements', 'ledger', ''],
  ].map(([label, value, detail, glyph, tone]) => `<div class="metric"><div class="metric-top">${label}<span class="metric-icon">${icon(glyph)}</span></div><div class="metric-value">${value}</div><div class="metric-detail ${tone}">${detail}</div></div>`).join('')}</div>`;
}
function toolbar() {
  return `<div class="toolbar"><div class="tabs" role="group" aria-label="Filter results">${[['all','All items'],['attention','Needs review'],['matched','Invoices found'],['reviewed','Reviewed']].map(([key,label]) => `<button class="${state.filter === key ? 'active' : ''}" data-action="filter" data-filter="${key}" aria-pressed="${state.filter === key}">${label}</button>`).join('')}</div><label class="search">${icon('search')}<input id="search" placeholder="Search vendor or invoice…" value="${esc(state.query)}" aria-label="Search vendor or invoice"></label></div>`;
}
function matchesQuery(text) { return text.toLowerCase().includes(state.query.toLowerCase().trim()); }
function statementPanel(data) {
  const docs = state.statements.filter(doc => {
    const rows = comparisonsFor(doc);
    return matchesQuery(`${doc.vendor} ${doc.filename} ${doc.rows.map(r => r.invoiceNumber).join(' ')}`) && (state.filter === 'all' || state.filter === 'attention' && (rows.some(isAttention) || !doc.confirmed) || state.filter === 'matched' && rows.some(invoiceFound) || state.filter === 'reviewed' && rows.some(r => reviewDecision(r.id)));
  });
  return `<div class="panel-title"><h2>Vendor statements</h2><small>${state.statements.length} documents</small></div>${toolbar()}${docs.length ? `<div class="table-wrap"><table class="main-table"><thead><tr><th>Vendor / statement</th><th>As of</th><th>Invoices</th><th>Balance</th><th>Status</th><th></th></tr></thead><tbody>${docs.map(doc => { const summary = docSummary(doc); return `<tr data-action="open-doc" data-id="${doc.id}"><td><button data-action="open-doc" data-id="${doc.id}" style="text-align:left;padding:0">${vendorCell(doc)}</button></td><td class="numeric">${esc(doc.statementDate || 'Set date')}</td><td>${groupInvoices(doc).filter(r => r.kind === 'invoice').length}<small style="display:block;color:#9aa18f;font-size:9px;margin-top:4px">${doc.pageCount} ${doc.pageCount === 1 ? 'page' : 'pages'}${doc.ocr ? ' · OCR' : ''}</small></td><td class="numeric">${money(doc.declaredTotal ?? totals(doc).sum)}</td><td>${badge(summary.status, summary.label)}</td><td>${icon('arrow')}</td></tr>`; }).join('')}</tbody></table></div>` : `<div class="empty">${icon('folder')}<h3>${state.statements.length ? 'No statements match this filter' : 'Ready for your first statement'}</h3>${state.statements.length ? 'Try another filter or search.' : 'Upload a PDF to review its invoices, credits, and balances.'}</div>`}<div class="table-foot"><span>${docs.length} statements shown</span><button class="mini-link" data-action="clear">Clear workspace</button></div>`;
}
function exceptionPanel() {
  const rows = results().filter(row => matchesQuery(`${row.vendor} ${row.invoiceNumber} ${row.reason}`) && (state.filter === 'all' || state.filter === 'attention' && isAttention(row) || state.filter === 'matched' && invoiceFound(row) || state.filter === 'reviewed' && reviewDecision(row.id)));
  return `<div class="panel-title"><h2>Invoice review queue</h2><small>${rows.length} items</small></div><div style="height:20px"></div>${toolbar()}${rows.length ? `<div class="table-wrap"><table class="main-table result-table"><thead><tr><th>Vendor</th><th>Invoice</th><th>Statement balance</th><th>Result</th><th></th></tr></thead><tbody>${rows.map(row => `<tr data-action="open-result" data-doc="${row.statementId}" data-id="${row.id}"><td><button style="padding:0;text-align:left" data-action="open-result" data-doc="${row.statementId}" data-id="${row.id}"><strong>${esc(row.vendor)}</strong><small style="display:block;color:#929d87;font-size:9px;margin-top:4px">${row.kind === 'invoice' ? 'Invoice' : esc(row.kind)} · Page ${row.page}</small></button></td><td class="invoice-link">${esc(row.invoiceNumber || 'Account activity')}</td><td class="numeric">${money(row.outstanding)}</td><td>${badge(row.status)}${reviewDecision(row.id) ? '<span class="resolved-label">✓ Reviewed · decision recorded</span>' : ''}</td><td>${icon('arrow')}</td></tr>`).join('')}</tbody></table></div>` : `<div class="empty">${icon('check')}<h3>No items in this view</h3>Change the filter or upload another statement.</div>`}<div class="table-foot"><span>${rows.length} items shown</span><button class="mini-link" data-action="export">Download CSV</button></div>`;
}
function rail(data) {
  const percent = data.total ? Math.round(data.matched / data.total * 100) : 0;
  return `<div class="side-card"><div class="eyebrow" style="margin-bottom:15px">At a glance</div><h3>Reconciliation progress</h3><div class="review-number">${percent}%<small>matched</small></div><div class="review-bar"><span class="good" style="width:${percent}%"></span><span class="warn" style="width:${100-percent}%"></span></div><div class="legend-row"><span><i class="legend-dot"></i>Matched</span><strong>${data.matched}</strong></div><div class="legend-row"><span><i class="legend-dot" style="background:#e1b873"></i>Needs attention</span><strong>${data.attention}</strong></div><div class="legend-row"><span><i class="legend-dot" style="background:#9baf8a"></i>Reviewed</span><strong>${data.reviewed}</strong></div><p>A match confirms the compared records, not QuickBooks sync or historical completeness.</p><button class="button small" style="width:100%" data-action="view" data-view="exceptions">Open review queue ${icon('arrow')}</button></div><div class="side-card"><h3>A simpler statement check</h3><ol class="steps"><li><span class="step-number">1</span><div><strong>Upload your PDFs</strong>Digital and scanned statements.</div></li><li><span class="step-number">2</span><div><strong>Check the extraction</strong>Verify rows, credits, and totals.</div></li><li><span class="step-number">3</span><div><strong>Review the exceptions</strong>See the source and record a decision.</div></li></ol></div>`;
}
function vendorsPanel() {
  const vendors = [...new Set(state.statements.map(d => d.vendor))];
  return `<section class="panel"><div class="panel-title"><h2>Vendor name mappings</h2><small>${vendors.length} vendors</small></div><div class="wide-panel"><p>Statement names and BILL vendor names can differ. Enter the exact name from your imported records. Mappings are saved in this browser.</p></div><div class="table-wrap"><table class="vendor-table"><thead><tr><th>Statement vendor</th><th>BILL vendor name</th><th>Statements</th><th></th></tr></thead><tbody>${vendors.map((vendor,i) => `<tr><td><strong>${esc(vendor)}</strong></td><td><input id="mapping-${i}" value="${esc(state.mappings[vendor] || vendor)}" aria-label="BILL vendor name for ${esc(vendor)}"></td><td>${state.statements.filter(d => d.vendor === vendor).length}</td><td><button class="button small" data-action="mapping" data-vendor="${esc(vendor)}" data-input="mapping-${i}">Save mapping</button></td></tr>`).join('')}</tbody></table></div>${vendors.length ? '' : '<div class="empty">Upload a statement to add its vendor.</div>'}</section>`;
}
function connectionPanel() {
  return `<section class="panel wide-panel bill-settings"><h2>Keep BILL data up to date</h2>
    <div class="notice blue">${icon('info')}<div><strong>BILL API is not connected.</strong> Comparisons use your saved CSV records and depend on the export’s coverage. This does not verify payment settlement or QuickBooks sync.</div></div>
    <p>Upload the original <strong>Bills CSV</strong> about once a week. It stays in this shared workspace and is reused whenever a statement arrives. A separate vendor export is not needed.</p>
    <p>Include paid and unpaid bills, including older invoices still listed on your statements. Keep invoice numbers as text.</p>
    <label class="field">Export snapshot date (optional)<input type="date" id="provider-date" value="${esc(state.provider.asOf||'')}"></label>
    <div class="action-row"><button class="button primary" data-action="import">${state.provider.loaded?'Update BILL data':'Upload BILL data'}</button><button class="button" data-action="view" data-view="statements">Back to statements</button></div>
    <p class="muted">Updating replaces the current comparison source and resets invoice review decisions. Notes, original PDFs and completed history remain saved.</p>
    <details><summary>Import details and limitations</summary>${importSummaryHTML()}<p>Checks use the export’s coverage. Invoice found does not verify payment settlement, historical balances, or QuickBooks sync.</p></details>
    <details><summary>Advanced options</summary><div class="action-row"><button class="button small" data-action="view" data-view="vendors">Manage vendor names</button><button class="button small" data-action="migration-preview">Import old browser work</button><button class="button small" data-action="template">Download CSV template</button><button class="button small" data-action="disconnect">Use extraction only</button></div></details>
  </section>`;
}
function importSummaryHTML() {
  if (state.provider.sourceFormat !== 'bill-native') return '';
  const provider = state.provider;
  return `<div class="notice amber"><div><strong>Native BILL export · invoice checks only</strong><p>${provider.importedRowCount} source rows · ${provider.collapsedRowCount} repeated line-item rows combined · ${provider.excludedRowCount} rows excluded · ${provider.sourceIssueCount} source warnings.</p><p>Invoice found means the reference and original numeric amount agree. Currency, payment settlement, outstanding balance, and QuickBooks sync are not verified. Paid amounts and credits are shown as reported evidence only.</p></div></div>${provider.importNotes ? `<details><summary>Review import warnings and excluded source rows</summary><pre class="raw-text">${esc(provider.importNotes)}</pre></details>` : ''}`;
}
function reportedMoney(value, currency) {
  if (value == null) return 'Not supplied';
  return currency === 'USD' ? money(value) : new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value / 100);
}
function candidateSummary(bill) {
  return `${bill.vendor} · ${bill.invoiceNumber}: ${bill.comparisonScope === 'invoice-only' ? `${reportedMoney(bill.amount, bill.currency)} (${bill.currency || 'currency not supplied'})` : money(bill.amount)}`;
}
function billEvidence(bill) {
  return [['Vendor',bill.vendor], ...billDetails(bill)];
}
function billDetails(bill) {
  if (bill.comparisonScope !== 'invoice-only') return [['Reference', bill.invoiceNumber], ['Original amount', money(bill.amount)], ['Applied credits', money(bill.creditAmount || 0)], ['Cleared payments', money(bill.clearedPaymentAmount || 0)], ['Scheduled payments', money(bill.scheduledAmount || 0)]];
  return [['Reference', bill.invoiceNumber], ['Export source rows', bill.sourceRows], ['Original numeric amount', reportedMoney(bill.amount, bill.currency)], ['Currency', bill.currency || 'Not supplied'], ['BILL status (reported)', bill.status], ['Paid amount (reported)', reportedMoney(bill.reportedPaidAmount, bill.currency)], ['Amount due (reported)', reportedMoney(bill.reportedAmountDue, bill.currency)], ['Credits (reported)', reportedMoney(bill.reportedCreditAmount, bill.currency)], ['Full payment date (reported)', bill.reportedFullPaymentDate || 'Not supplied'], ['Comparison scope', 'Invoice presence only; settlement and balance not verified']];
}
function toast(message, error = false) {
  const node = document.querySelector('#toast'); node.textContent = message; node.className = error ? 'toast-error' : ''; node.style.display = 'block'; clearTimeout(toastTimer); toastTimer = setTimeout(() => { node.style.display = 'none'; }, 6500);
}
function download(name, text, type = 'text/csv;charset=utf-8') { const url = URL.createObjectURL(new Blob([text], { type })); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 2000); }
function modal(title, body, action, label = 'Continue') {
  priorFocus = document.activeElement;
  overlay.innerHTML = `<div class="overlay modal-overlay"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><h2 id="modal-title">${title}</h2>${body}<div class="action-row"><button class="button" data-action="close">Cancel</button><button class="button primary" data-action="${action}">${label}</button></div></section></div>`;
  overlay.querySelector('button')?.focus();
}
function closeOverlay() { if(overlay.querySelector('.drawer')&&dirty.has(state.selected)){toast('Save your edits before closing this statement.',true);return;}overlay.innerHTML = ''; state.selected = null; state.selectedRow = null;historicalDetail=null; priorFocus?.focus?.(); renderToken++; }
function getDoc() { return historicalDetail?.doc.id===state.selected?historicalDetail.doc:(state.statements.find(d => d.id === state.selected)||shared?.state.details.get(state.selected)?.doc); }
function openDoc(id,row=null,{historical=false,tab=null}={}) {
  if(!historical)historicalDetail=null;priorFocus=document.activeElement;state.selected=id;state.selectedRow=row;
  state.drawerTab=tab||(row||getDoc().rows.length?'review':'extraction');state.invoiceDetailsOpen=!!row;
  state.page=row?comparisonsFor(getDoc()).find(r=>r.id===row)?.page||1:1;
  renderDrawer();overlay.querySelector('.close')?.focus();
}
function renderDrawer() {
  const doc = getDoc(); if (!doc) return;
  const check = totals(doc);
  const reviewRows = comparisonsFor(doc);
  const row = reviewRows.find(r => r.id === state.selectedRow) || reviewRows.find(isAttention) || reviewRows[0];
  if (row && !state.selectedRow) state.selectedRow = row.id;
  const warnings = [...doc.warnings];
  if (check.difference !== 0 && check.difference !== null) warnings.push(`Extracted activity differs from the statement total by ${money(check.difference)}. Check missing rows, credits, or duplicate totals.`);
  if (check.difference === null) warnings.push('No statement total was identified. Enter it or verify completeness manually.');
  overlay.innerHTML = `<div class="overlay"><section class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><header class="drawer-head"><div><div class="eyebrow">Statement review</div><h2 id="drawer-title">${esc(doc.vendor)}</h2><small>${esc(doc.filename)} · ${doc.pageCount} ${doc.pageCount === 1 ? 'page' : 'pages'}${doc.ocr ? ' · scanned PDF' : ''}</small></div><button class="close" data-action="close" aria-label="Close statement">${icon('close')}</button></header><div class="drawer-body"><div class="drawer-tabs"><button class="button ${state.drawerTab === 'extraction' ? 'primary' : ''}" data-action="drawer-tab" data-tab="extraction">Check PDF</button><button class="button ${state.drawerTab === 'review' ? 'primary' : ''}" data-action="drawer-tab" data-tab="review">Results</button><button class="button ${state.drawerTab === 'notes' ? 'primary' : ''}" data-action="drawer-tab" data-tab="notes">Notes</button><button class="button subtle danger" data-action="remove-doc">Remove statement</button></div>${state.drawerTab === 'extraction' ? extractionView(doc, check, warnings) : state.drawerTab === 'notes' ? notesView(doc) : `<div class="source-layout result-overview-layout"><div>${vendorQuestionHTML(doc,state.provider,state.mappings,!!docDetail(doc.id)?.readOnly)}${statementOverviewHTML(doc,reviewRows,!!docDetail(doc.id)?.readOnly)}</div>${pdfPanel(doc)}</div>${row ? `<details class="invoice-details" ${state.invoiceDetailsOpen?'open':''}><summary>Invoice details & follow-up</summary>${reviewView(doc,row,reviewRows,false)}</details>` : '<div class="empty">No rows read. Open Check PDF to correct the statement.</div>'}`}</div></section></div>`;
  if (state.drawerTab !== 'notes') previewPDF(doc);
  if(saveState==='saving')sharedStatus('saving',sharedError);
  overlay.querySelectorAll('input,textarea').forEach(input=>input.addEventListener('input',markDirty));
  const noteLabel=overlay.querySelector('#review-note')?.parentElement;if(noteLabel)noteLabel.firstChild.textContent='Review note (optional)';
  const reviewNote=overlay.querySelector('#review-note');if(reviewNote&&historicalDetail)reviewNote.value=historicalDetail.resolutions[state.selectedRow]?.note||'';
  const detail=docDetail(doc.id),body=overlay.querySelector('.drawer-body');
  if(detail?.readOnly){body.insertAdjacentHTML('afterbegin',`<div class="notice blue"><div><strong>Saved revision · read-only</strong><p>${esc(historySelection?.initials||'')} · ${esc(nyTimestamp(historySelection?.completedAt))} · ${esc(detail.ruleVersion)} · Import ${esc(detail.importId||'none')}</p><p>These are the original saved comparisons, not results recalculated against the latest import.</p><button class="button" data-action="reopen-statement">Reopen current statement as a draft</button> <button class="button" data-action="export">Export saved evidence</button></div></div>`);overlay.querySelectorAll('input,textarea,select,[data-action="save-extraction"],[data-action="confirm-extraction"],[data-action="save-notes"],[data-action="resolve"],[data-action="reopen"],[data-action="add-row"],[data-action="delete-row"],[data-action="remove-doc"]').forEach(el=>{if(!['page-select','row-select'].includes(el.id))el.disabled=true;});}
  else if(body)body.insertAdjacentHTML('beforeend','<div class="action-row"><button class="button primary" data-action="complete-dialog">Mark statement reviewed</button><small>Reviewer initials required · notes optional</small></div>');
  if(detail&&!detail.originalAvailable&&body)body.insertAdjacentHTML('afterbegin','<div class="notice amber"><div><strong>Original PDF not attached</strong><p>Select the original PDF to finish this migrated draft. Your previous notes and corrections are retained.</p><button class="button" data-action="attach-original">Attach original PDF</button></div></div>');
}
function extractionView(doc, check, warnings) {
  return `${warnings.length ? `<div class="notice amber">${icon('info')}<div>${warnings.map(w => `<div>${esc(w)}</div>`).join('')}</div></div>` : `<div class="notice">${icon('check')}<div>Extracted activity agrees with the statement total. Verify invoice numbers before confirming.</div></div>`}<div class="form-grid"><label class="field">Statement vendor<input id="doc-vendor" value="${esc(doc.vendor)}"></label><label class="field">Statement date<input type="date" id="doc-date" value="${esc(doc.statementDate)}"></label><label class="field">Printed statement total (USD)<input id="doc-total" value="${doc.declaredTotal == null ? '' : (doc.declaredTotal / 100).toFixed(2)}" inputmode="decimal"></label><label class="field">Extracted activity total<input readonly value="${money(check.sum)}"></label></div><div class="source-layout"><div><div class="page-control"><strong>Extracted transactions · ${doc.rows.length}</strong><button class="button small" data-action="add-row">${icon('plus')}Add row</button></div><div class="table-wrap"><table class="edit-table"><thead><tr><th>Reference</th><th>Type</th><th>Amount</th><th>Invoice balance</th><th>Page</th><th></th></tr></thead><tbody>${doc.rows.map(row => `<tr data-row="${row.id}"><td><input class="ref" name="reference" value="${esc(row.invoiceNumber)}" aria-label="Invoice reference"></td><td><select name="type" aria-label="Transaction type">${['invoice','credit','payment','opening'].map(type => `<option ${row.type === type ? 'selected' : ''}>${type}</option>`).join('')}</select></td><td><input name="amount" value="${(row.amount / 100).toFixed(2)}" inputmode="decimal" aria-label="Original amount"></td><td><input name="balance" value="${row.balance == null ? '' : (row.balance / 100).toFixed(2)}" inputmode="decimal" aria-label="Invoice outstanding balance"></td><td><input class="small-col" name="page" type="number" min="1" max="${doc.pageCount}" value="${row.page}" aria-label="Source page"></td><td><button data-action="delete-row" data-id="${row.id}" aria-label="Remove row">${icon('trash')}</button></td></tr>`).join('')}</tbody></table></div><p style="font-size:10px;line-height:1.7;color:#849277">Amounts are signed: invoices positive, credits and payments negative. Leave invoice balance blank when only a running account balance is supplied. Reference numbers remain text.</p><div class="action-row"><button class="button" data-action="save-extraction">Save corrections</button><button class="button primary" data-action="confirm-extraction">${icon('check')}Confirm extracted rows</button></div><details style="margin-top:20px;font-size:11px;color:#748967"><summary>Extracted source text</summary><pre class="raw-text">${esc(doc.rawText || doc.rows.map(r => r.source).join('\n'))}</pre></details></div>${pdfPanel(doc)}</div>`;
}
function pdfPanel(doc) { const available=files.has(doc.id)||shared?.state.details.get(doc.id)?.originalAvailable;return `<div><div class="page-control"><strong>Original statement</strong><label>Page <select id="page-select" aria-label="Preview page">${Array.from({length:doc.pageCount},(_,i) => `<option value="${i+1}" ${state.page === i+1 ? 'selected' : ''}>${i+1}</option>`).join('')}</select></label></div>${available?'<div class="pdf-view"><canvas id="pdf-canvas" aria-label="Original PDF page"></canvas><div id="pdf-loading">Loading private original…</div></div>':`<div class="no-source">${icon('ledger')}<br>Original PDF not attached. This migrated draft is incomplete.</div>`}</div>`; }
function reviewView(doc, row, rows, showPDF=true) {
  const bill = row.candidates[0];
  const resolution = reviewDecision(row.id);
  return `<label class="field">Select invoice or account activity<select id="row-select">${rows.map(r => `<option value="${r.id}" ${r.id === row.id ? 'selected' : ''}>${esc(r.invoiceNumber || r.kind)} · ${statuses[r.status].label}</option>`).join('')}</select></label><div class="notice ${row.status === 'matched' ? '' : 'amber'}">${icon(row.status === 'matched' ? 'check' : 'info')}<div>${badge(row.status)}<div style="margin-top:7px">${esc(row.reason)}</div></div></div><div class="evidence-grid"><div class="evidence-card"><h3>Vendor statement</h3>${[['Reference',row.invoiceNumber || 'Account activity'],['Original amount',money(row.originalAmount)],['Outstanding balance',money(row.outstanding)],['Statement date',doc.statementDate || 'Not identified'],['Source page',row.page]].map(([k,v]) => `<div class="evidence-line"><span>${k}</span><strong>${esc(v)}</strong></div>`).join('')}</div><div class="evidence-card"><h3>Imported BILL record</h3>${bill ? billEvidence(bill).map(([k,v]) => `<div class="evidence-line"><span>${k}</span><strong>${esc(v)}</strong></div>`).join('') : `<p style="font-size:11px;line-height:1.8;color:#829175">${state.provider.loaded ? 'No matching record available in this dataset.' : 'No BILL records connected. This invoice has not been checked.'}</p>`}${row.candidates.length > 1 ? `<p style="font-size:11px;color:#a47a3f">${row.candidates.length} candidates: ${row.candidates.map(b => esc(candidateSummary(b))).join(' · ')}</p>` : ''}</div></div><div class="${showPDF?'source-layout':'invoice-review-detail'}"><div><h3 style="font-size:12px">Statement activity for this reference</h3>${row.activity.map(a => `<div class="activity-list"><div>${esc(a.type)} · ${esc(a.invoiceNumber || 'account')}<small>${esc(a.date || 'Date not supplied')} · page ${a.page}</small></div><strong>${money(a.amount)}</strong></div>`).join('')}${doc.confirmed ? `<label class="field">Review decision<select id="review-decision">${['Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed'].map(v => `<option ${resolution?.decision === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label><label class="field">Review note<textarea id="review-note" placeholder="Explain your decision or next step…">${esc(state.resolutions[row.id]?.note || '')}</textarea></label><div class="action-row"><button class="button primary" data-action="resolve">${icon('check')}Save review decision</button>${resolution ? '<button class="button" data-action="reopen">Reopen item</button>' : ''}</div>${resolution ? `<p style="font-size:10px;color:#7e916c">Reviewed ${esc(new Date(resolution.at).toLocaleString())}. The original matching result is preserved.</p>` : ''}` : '<p class="muted">Confirm the PDF reading above before recording review decisions.</p>'}</div>${showPDF?pdfPanel(doc):''}</div>`;
}
function notesView(doc) { return `<label class="field">Assigned reviewer (optional)<input id="assignee" value="${esc(doc.assignee)}" placeholder="Name or initials"></label><label class="field">Statement notes (optional)<textarea id="doc-notes" style="min-height:170px" placeholder="Vendor follow-up, unresolved opening balances, or review context…">${esc(doc.notes)}</textarea></label><button class="button primary" data-action="save-notes">Save notes</button><p style="font-size:11px;line-height:1.8;color:#879578">Acknowledged saves retain notes in the private shared workspace.</p>`; }
async function previewPDF(doc) {
  const canvas = document.querySelector('#pdf-canvas'); if (!canvas) return;
  const token = ++renderToken;
  try { extractor ??= await import('./extraction.mjs'); const original=files.get(doc.id)||await shared.originalPdf(doc.id); if (token !== renderToken) return; await extractor.renderPage(original, state.page, canvas); if (token === renderToken) document.querySelector('#pdf-loading')?.remove(); }
  catch(error) { if (token === renderToken) { const loading = document.querySelector('#pdf-loading'); if (loading) loading.textContent = `Preview unavailable: ${error.message}`; } }
}
function collectRows(doc, excludedRow = null) {
  const rows = [...overlay.querySelectorAll('[data-row]')].filter(tr => tr.dataset.row !== excludedRow).map(tr => {
    const original = doc.rows.find(r => r.id === tr.dataset.row);
    const amount = cents(tr.querySelector('[name="amount"]').value);
    const rawBalance = tr.querySelector('[name="balance"]').value.trim();
    const balance = rawBalance ? cents(rawBalance) : null;
    const reference = tr.querySelector('[name="reference"]').value.trim();
    const type = tr.querySelector('[name="type"]').value;
    const page = Number(tr.querySelector('[name="page"]').value);
    if (amount == null || rawBalance && balance == null) throw new Error('Enter valid amounts with at most two decimal places.');
    if (type === 'invoice' && !reference) throw new Error('Each invoice needs a reference number.');
    if (!Number.isInteger(page) || page < 1 || page > doc.pageCount) throw new Error('Source page must be within the document.');
    return { ...original, amount, balance, invoiceNumber: reference, type, page };
  });
  return rows;
}
function collectDoc(doc, excludedRow = null) {
  const rows = collectRows(doc, excludedRow);
  const vendor = document.querySelector('#doc-vendor').value.trim() || 'Unidentified vendor';
  const statementDate = document.querySelector('#doc-date').value;
  const total = document.querySelector('#doc-total').value.trim();
  if (total && cents(total) == null) throw new Error('Enter a valid printed statement total.');
  // Commit only after every input validates; rejected edits preserve evidence.
  Object.assign(doc, { rows, vendor, statementDate, declaredTotal: total ? cents(total) : null, confirmed: false });
}
async function uploadPDFs(fileList) {
  ready();
  if (state.busy) return;
  const pdfs = [...fileList].filter(file => file.name.toLowerCase().endsWith('.pdf'));
  if (!pdfs.length) { toast('Choose PDF statement files.', true); return; }
  if (pdfs.length > 20) { toast('Upload at most 20 PDFs in one batch, up to 20 MiB each.', true); return; }
  if(pendingAttachment){if(pdfs.length!==1)throw Error('Select one original PDF for this migrated statement.');const saved=await shared.attachOriginal(pdfs[0],pendingAttachment.id,pendingAttachment.version);pendingAttachment=null;files.set(saved.doc.id,pdfs[0]);renderDrawer();document.querySelector('#pdf-input').value='';return;}
  state.busy = true; state.errors = []; state.query = ''; state.filter = 'all'; state.view = 'statements'; render();
  try {
    for (let i = 0; i < pdfs.length; i++) {
      const file = pdfs[i];
      try {
        const saved=await shared.uploadStatement(file,async original=>{extractor ??= await import('./extraction.mjs');return extractor.extractPDF(original, progress => { state.progress = `${i+1}/${pdfs.length} · ${file.name} · page ${progress.page}/${progress.total} · ${progress.stage}`; state.fraction = (i + progress.fraction) / pdfs.length; const status = document.querySelector('.guide-progress'); if (status) status.textContent = `Reading your PDFs… ${state.progress}`; });});
        files.set(saved.doc.id,file);
      } catch (error) { state.errors.push(`${file.name}: ${error.message}`); }
      render();
    }
  } catch(error) { state.errors.push(`PDF processing unavailable: ${error.message}`); }
  finally { await extractor?.stopOCR?.(); state.busy = false; state.progress = ''; render(); document.querySelector('#pdf-input').value = ''; }
  toast(`${state.statements.length} statements ready. Open a statement to see the automatic invoice check and verify the PDF reading.`, !!state.errors.length);
}
function bindDropzone() {
  const zone = document.querySelector('#dropzone'); if (!zone) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); if (!state.busy) zone.classList.add('dragging'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('dragging'); uploadPDFs(e.dataTransfer.files); });
}
document.querySelector('#pdf-input').addEventListener('change', e => uploadPDFs(e.target.files));
document.querySelector('#csv-input').addEventListener('change', async e => {
  const file = e.target.files[0]; if (!file) return;
  try {
    ready();
    const { records, summary } = importBillSource(await file.text());
    const provider = { loaded: true, simulated: false, records, label: file.name, refreshedAt: new Date().toISOString(), asOf: document.querySelector('#provider-date')?.value || '', sourceFormat: summary.format,
      importedRowCount: summary.inputRows, collapsedRowCount: summary.collapsedRows, excludedRowCount: summary.excludedRows, sourceIssueCount: summary.issues.length,
      importNotes: summary.issues.map(issue => `CSV row(s) ${issue.rows}: ${issue.reason}`).join('\n') };
    await shared.importBills(file,provider);state.view='statements';render();
    toast(`${records.length} BILL comparison records imported. ${summary.excludedRows} rows excluded; ${summary.issues.length} source warnings. Check export coverage.`, summary.issues.length > 0);
  }
  catch(error) { sharedError=error;retryOperation=error.retry||null;render();toast(error.message, true); }
  e.target.value = '';
});
document.addEventListener('input', e => {
  if (e.target.id === 'search') { const pos = e.target.selectionStart; state.query = e.target.value; render(); const input = document.querySelector('#search'); input?.focus(); input?.setSelectionRange(pos,pos); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'page-select') { state.page = Number(e.target.value); previewPDF(getDoc()); }
  if (e.target.id === 'row-select') { if(saveState==='saving'){e.target.value=state.selectedRow;toast('Wait for the save to finish before selecting another invoice.',true);return;}if(dirty.has(state.selected)){e.target.value=state.selectedRow;toast('Save your edits before selecting another invoice.',true);return;}state.selectedRow = e.target.value; const row = comparisonsFor(getDoc()).find(r => r.id === state.selectedRow); state.page = row?.page || 1; renderDrawer(); }
  if (e.target.id === 'provider-date') state.provider.asOf = e.target.value;
});
document.addEventListener('click', async e => {
  if (e.target.classList.contains('overlay')) { closeOverlay(); return; }
  const target = e.target.closest('[data-action]'); if (!target || target.disabled) return;
  const action = target.dataset.action;
  try {
    if(saveState==='saving'&&!['close','confirm-back-to-programs'].includes(action))throw Error('Please wait for the current save to finish.');
    if(action==='attach-original'){const detail=shared.state.details.get(state.selected);pendingAttachment={id:state.selected,version:detail.version};document.querySelector('#pdf-input').click();}
    if(action==='migration-preview'){ready();const legacy=loadSession(browserStorage()),mappings=loadVendorMappings(browserStorage());if(legacy.error||mappings.error)throw Error(legacy.error||mappings.error);migrationPreview=legacyMigrationPreview(legacy.session,mappings.mappings);modal('Import old browser work?',`<p>${migrationPreview.statements.length} real statements found. None of their original PDFs are saved in browser storage.</p><p>This creates unconfirmed shared drafts and retains notes. No completion history or reviewer initials will be invented. Existing browser data is not deleted.</p>${migrationPreview.importMetadata?`<p>Older BILL source: ${esc(migrationPreview.importMetadata.label)}. Select its original CSV once through Import BILL CSV to store the full shared comparison source.</p>`:''}<p>Imported drafts require the original PDFs and a fresh extraction check.</p>`,'confirm-migration','Import previous work');}
    if(action==='confirm-migration'){await shared.migrateLegacy(migrationPreview,true);migrationPreview=null;closeOverlay();render();toast('Previous notes imported as unconfirmed drafts. Attach their original PDFs to continue.');}
    if(state.selected&&docDetail(state.selected)?.readOnly&&['save-extraction','confirm-extraction','add-row','delete-row','save-notes','resolve','reopen','remove-doc','save-session','attach-original','vendor-confirm','vendor-choose','confirm-reading','complete-dialog','complete-statement'].includes(action))throw Error('This saved revision is read-only. Explicitly reopen the current statement to continue work.');
    if(action==='history-view'){state.view='history';historySelection=null;await refreshHistory();}
    if(action==='history-search'){for(const key of ['vendor','statementDate','initials','status','completedFrom','completedTo'])activeHistoryFilters[key]=document.querySelector(`#history-${key}`).value;await refreshHistory();}
    if(action==='history-more')await refreshHistory(true);
    if(action==='history-open'){historySelection=historyPage.items.find(item=>item.id===target.dataset.event);historicalDetail=await shared.statement(historySelection.statementId,historySelection.revisionId);openDoc(historicalDetail.doc.id,null,{historical:true});}
    if(action==='vendor-confirm'||action==='vendor-choose'){
      const doc=getDoc();if(dirty.has(doc.id))throw Error('Save your edits before confirming the vendor.');
      ready();const name=action==='vendor-confirm'?target.dataset.vendor:document.querySelector('#statement-bill-vendor').value;
      await confirmVendor(doc,name,shared,persistDoc);render();renderDrawer();toast('Vendor confirmed. Future statements will use this choice.');
    }
    if(action==='confirm-reading'){
      const doc=getDoc();if(dirty.has(doc.id))throw Error('Save edits before confirming the PDF reading.');
      if(readingIssues(doc).length||!doc.vendor||doc.vendor==='Unidentified vendor'){state.drawerTab='extraction';renderDrawer();throw Error('Check the highlighted PDF fields, then confirm the corrected rows.');}
      doc.confirmed=true;await persistDoc(doc);render();renderDrawer();toast('PDF reading confirmed and saved.');
    }
    if(action==='select-invoice'){
      if(dirty.has(state.selected))throw Error('Save edits before selecting another invoice.');
      state.invoiceDetailsOpen=true;state.selectedRow=target.dataset.id;state.page=comparisonsFor(getDoc()).find(row=>row.id===state.selectedRow)?.page||1;renderDrawer();
    }
    if(action==='complete-dialog'){const doc=getDoc();if(dirty.has(doc.id))throw Error('Save corrections or notes before marking reviewed.');completionPayload({doc,results:comparisonsFor(doc),resolutions:completionReviews(comparisonsFor(doc),state.resolutions),initials:'AP',expectedVersion:shared.state.details.get(doc.id).version});modal('Mark statement reviewed',`<p>Finish your review of the PDF and the invoices found in BILL. Found invoices are acknowledged together; differences require a decision. This does not verify payment settlement or QuickBooks sync.</p><label class="field">Reviewer initials<input id="completion-initials" maxlength="10" placeholder="e.g. KC" required></label><label class="field">Completion note (optional)<textarea id="completion-note"></textarea></label>`,'complete-statement','Mark reviewed');state.selected=doc.id;}
    if(action==='complete-statement'){const doc=getDoc();const proposed=completionReviews(comparisonsFor(doc),state.resolutions);const payload=completionPayload({doc,results:comparisonsFor(doc),resolutions:proposed,initials:document.querySelector('#completion-initials').value,notes:document.querySelector('#completion-note').value,expectedVersion:shared.state.details.get(doc.id).version});state.resolutions=proposed;shared.state.resolutions=proposed;await shared.completeStatement(payload);closeOverlay();state.view='history';await refreshHistory();toast('Review completed and saved.');}
    if(action==='reopen-statement'){const id=state.selected;if(dirty.has(id)&&state.statements.some(doc=>doc.id===id)){historicalDetail=null;historySelection=null;openDoc(id);toast('Returned to your unsaved draft. Edits retained.');}else{const latest=await shared.statement(id);historicalDetail=null;if(!latest.completed){shared.adopt(latest);receiveShared(shared.state);openDoc(id);toast('A colleague already reopened this statement. Loaded the current draft.');}else{await shared.reopenStatement(id,latest.version);state.view='statements';historySelection=null;openDoc(id);}}}
    if (action === 'back-to-programs') modal('Go back to programs?', '<p>Save changes or export your report before leaving.</p><p>Unsaved edits will be lost. Acknowledged revisions and original PDFs remain in your private shared workspace.</p>', 'confirm-back-to-programs', 'Go back to programs');
    if (action === 'retry-shared') {if(retryOperation)await retryOperation();render();if(state.selected)renderDrawer();}
    if (action === 'reload-latest') modal('Reload latest shared work?','<p>This discards unsaved edits in this tab. Shared records are retained.</p>','confirm-reload','Reload latest');
    if (action === 'confirm-reload') {await shared.load({replace:true});dirty.clear();sharedError=null;sharedStatus('saved');closeOverlay();render();}
    if (action === 'confirm-back-to-programs') requestProgramHub(window, true);
    if (action === 'view') { state.view = target.dataset.view; state.filter = state.view === 'exceptions' ? 'attention' : 'all'; state.query = ''; render(); }
    if (action === 'filter') { state.filter = target.dataset.filter; render(); }
    if (action === 'upload') document.querySelector('#pdf-input').click();
    if (action === 'guide-step') goToGuideStep(target.dataset.step);
    if (action === 'guide-next') {
      const next = workflowGuide(state);
      if (next.action === 'export') document.querySelector('[data-action="export"]').click();
      else goToGuideStep(next.action);
    }
    if (action === 'import') document.querySelector('#csv-input').click();
    if (action === 'open-doc') openDoc(target.dataset.id);
    if (action === 'open-result') openDoc(target.dataset.doc, target.dataset.id);
    if (action === 'close') closeOverlay();
    if (action === 'drawer-tab') { if(dirty.has(state.selected))throw Error('Save your edits before changing tabs.');state.drawerTab = target.dataset.tab; renderDrawer(); }
    if (action === 'save-extraction' || action === 'confirm-extraction') {
      const doc = getDoc(); const priorRows = groupInvoices(doc); collectDoc(doc);
      invalidateReviewDecisions(priorRows);
      if (action === 'confirm-extraction') {
        if (!doc.rows.length || doc.vendor === 'Unidentified vendor') throw new Error('Set the vendor and add transaction rows before confirming.');
        doc.confirmed = true; doc.rows.forEach(r => { r.confidence = 99; }); state.drawerTab = 'review';
      }
      await persistDoc(doc);render(); renderDrawer(); toast(action === 'confirm-extraction' ? 'Extraction confirmed and saved. Matching results are ready for review.' : 'Corrections saved to the shared workspace.');
    }
    if (action === 'add-row') { const doc = getDoc(); const priorRows = groupInvoices(doc); collectDoc(doc); invalidateReviewDecisions(priorRows); doc.rows.push({ id: uid(), type: 'invoice', invoiceNumber: '', amount: 0, balance: null, page: state.page, confidence: 99, source: 'Manually added row' }); doc.confirmed = false; render(); renderDrawer(); }
    if (action === 'delete-row') { const doc = getDoc(); const priorRows = groupInvoices(doc); collectDoc(doc, target.dataset.id); invalidateReviewDecisions(priorRows); render(); renderDrawer(); }
    if (action === 'save-notes') { const doc = getDoc(); doc.notes = document.querySelector('#doc-notes').value; doc.assignee = document.querySelector('#assignee').value; await persistDoc(doc);toast('Optional notes saved to the shared workspace.'); }
    if (action === 'resolve') { if(!getDoc().confirmed)throw Error('Check and confirm the PDF reading before saving a decision.');const current=comparisonsFor(getDoc()).find(row=>row.id===state.selectedRow);if(current?.status==='vendor'&&document.querySelector('#review-decision').value==='Reviewed — no action needed')throw Error('Confirm the vendor above, or record a follow-up decision.');const note = document.querySelector('#review-note').value.trim(); state.resolutions[state.selectedRow] = { note, decision: document.querySelector('#review-decision').value };await persistDoc(getDoc()); render(); renderDrawer(); toast('Review saved. The matching evidence is preserved.'); }
    if (action === 'reopen') { delete state.resolutions[state.selectedRow];await persistDoc(getDoc()); render(); renderDrawer(); }
    if (action === 'mapping') {
      const value = document.getElementById(target.dataset.input).value.trim();
      if (!value) throw new Error('Enter the BILL vendor name.');
      const vendor = target.dataset.vendor;
      if (vendorKey(state.mappings[vendor] || vendor) !== vendorKey(value)) {
        for (const doc of state.statements.filter(doc => doc.vendor === vendor)) {
          invalidateReviewDecisions(groupInvoices(doc));
        }
      }
      ready();await shared.saveMapping({vendor,bill_vendor:value},shared.state.mappingVersions[vendor]||0);
      render();
      toast('Vendor mapping saved. Changed comparisons need review; previous notes are retained.');
    }
    if (action === 'save-session') { ready();if(state.selected&&state.drawerTab==='review'&&document.querySelector('#review-note')){const prior=state.resolutions[state.selectedRow]||{};state.resolutions[state.selectedRow]={...prior,note:document.querySelector('#review-note').value};}if(state.selected&&state.drawerTab==='extraction')collectDoc(getDoc());if(state.selected&&state.drawerTab==='notes'){getDoc().notes=document.querySelector('#doc-notes').value;getDoc().assignee=document.querySelector('#assignee').value;}for(const doc of [...state.statements])await persistDoc(doc);render();if(state.selected)renderDrawer();toast('Changes saved to the shared workspace.'); }
    if (action === 'disconnect') {shared.extractionOnly();render(); toast('Extraction-only view. The stored BILL source is retained and returns when you reload.'); }
    if (action === 'clear') modal('Reset local view?', '<p>Reload shared records and discard unsaved edits in this tab. This does not delete shared statements, BILL records, or previous work.</p>', 'confirm-clear', 'Reset local view');
    if (action === 'confirm-clear') {await shared.load({replace:true});dirty.clear();state.errors=[];files.clear();closeOverlay();render();toast('Local view reset. Shared history retained.');}
    if (action === 'remove-doc') { const doc = getDoc(); const id = doc.id; modal('Remove this statement?', `<p>Remove ${esc(doc.filename)} and its review notes from this workspace? Your original PDF will not be deleted.</p>`, 'confirm-remove', 'Remove'); state.selected = id; }
    if (action === 'confirm-remove') { const doc = getDoc();await shared.archiveStatement(doc.id,shared.state.details.get(doc.id).version);files.delete(doc.id);closeOverlay();render(); }
    if (action === 'template') download('bill-record-template.csv', toCSV([['vendor','invoiceNumber','amount','kind','currency','clearedPaymentAmount','scheduledAmount','creditAmount','paymentDate','id']]));
    if (action === 'export') {
      const header = ['vendor','statement','statementDate','invoiceNumber','activityType','originalAmount','statementOutstanding','result','reason','source','simulated','reviewDecision','reviewNote','assignedReviewer','importId','ruleVersion','reviewerInitials','completedAtUTC','statementNotes'];
      const reportRows=state.selected&&docDetail(state.selected)?.readOnly?comparisonsFor(getDoc()):results();
      const rows = reportRows.map(r => { const detail=docDetail(r.statementId);const doc = detail?.readOnly?detail.doc:(state.statements.find(d => d.id === r.statementId)||detail.doc); const resolution = reviewDecision(r.id); return [r.vendor,doc.filename,doc.statementDate,r.invoiceNumber,r.kind,r.originalAmount == null ? '' : (r.originalAmount/100).toFixed(2),r.outstanding == null ? '' : (r.outstanding/100).toFixed(2),statuses[r.status].label,r.reason,detail?.readOnly?(detail.importLabel||'Frozen saved comparison'):state.provider.label || 'No BILL data',r.simulated ? 'YES — SIMULATED' : 'NO',resolution?.decision || '',(historicalDetail?historicalDetail.resolutions[r.id]:state.resolutions[r.id])?.note || '',doc.assignee || '',detail?.importId||'',detail?.readOnly?detail.ruleVersion:'ap-match-v3',detail?.readOnly?historySelection?.initials||'':'',detail?.readOnly?historySelection?.completedAt||'':'',doc.notes||'']; });
      download('statement-reconciliation.csv', toCSV([header,...rows])); toast('Report exported with source and review notes.');
    }
  } catch(error) {if(error.retry||error.code){sharedError=error;retryOperation=error.retry||null;decorateSharedUi();}toast(error.message || 'This action could not be completed.', true); }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && overlay.innerHTML) closeOverlay();
  if (e.key === 'Tab' && overlay.innerHTML) {
    const elements = [...overlay.querySelectorAll('button:not(:disabled),input,select,textarea,summary,[tabindex="0"]')].filter(n => n.getClientRects().length);
    const first = elements[0], last = elements.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }
});
render();
startShared();
