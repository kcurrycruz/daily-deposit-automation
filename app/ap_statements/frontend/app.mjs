import { money, cents, uid, totals, groupInvoices, reconcile, statuses, importRecords, toCSV, vendorKey } from './core.mjs';
import { createDemo, simulateRecords } from './demo.mjs';
import { loadSession, saveSession, clearSession, loadVendorMappings, saveVendorMappings } from './session.mjs';

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
const initial = createDemo();
const state = { ...initial, view: 'statements', filter: 'all', query: '', mappings: {}, resolutions: {}, selected: null, selectedRow: null, drawerTab: 'review', page: 1, busy: false, progress: '', fraction: 0, errors: [] };
const files = new Map();
let extractor;
let toastTimer;
let priorFocus;
let renderToken = 0;
const app = document.querySelector('#app');
const overlay = document.querySelector('#overlay-root');
const browserStorage = () => { try { return window.localStorage; } catch { return null; } };
const saved = loadSession(browserStorage());
if (saved.session) Object.assign(state, saved.session, { view: 'statements', selected: null });
const savedMappings = loadVendorMappings(browserStorage());
state.mappings = savedMappings.mappings;
for (const error of [saved.error, savedMappings.error]) if (error) state.errors.push(error);
const results = () => state.statements.flatMap(statement => reconcile(statement, state.provider, state.mappings));
const isAttention = row => row.status !== 'matched' && !state.resolutions[row.id];
function stats() {
  const rows = results();
  return { rows, total: rows.length, matched: rows.filter(r => r.status === 'matched').length, attention: rows.filter(isAttention).length, reviewed: rows.filter(r => state.resolutions[r.id]).length, balance: state.statements.reduce((s, d) => s + (d.declaredTotal ?? totals(d).sum), 0) };
}
const badge = (status, label) => `<span class="badge ${statuses[status]?.tone || 'gray'}"><span class="dot"></span>${esc(label || statuses[status]?.label || status)}</span>`;
const initials = name => name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
function vendorCell(doc) { return `<div class="vendor-cell"><div class="vendor-avatar">${esc(initials(doc.vendor))}</div><div><strong>${esc(doc.vendor)}</strong><small>${esc(doc.filename)}</small></div></div>`; }
function sourcePill() { return state.provider.simulated ? 'Demo · simulated BILL' : state.provider.loaded ? 'CSV records · API offline' : 'BILL not connected'; }
function docSummary(doc) {
  const rows = reconcile(doc, state.provider, state.mappings);
  const check = totals(doc);
  if (!doc.confirmed) return { status: 'extraction', label: 'Review extraction' };
  if (check.difference !== 0 && check.difference !== null) return { status: 'extraction', label: 'Check statement total' };
  if (rows.every(r => r.status === 'matched') && rows.length) return { status: 'matched' };
  if (!state.provider.loaded) return { status: 'unverified' };
  return { status: 'balance', label: `${rows.filter(isAttention).length} to review` };
}
function render() {
  const data = stats();
  const title = { statements: 'Your statement workspace', exceptions: 'Focus on what needs attention', vendors: 'Keep your vendors connected', connection: 'Connect your accounting source' }[state.view];
  const subtitle = { statements: 'Upload statements. Match invoices. Spend your time on the exceptions.', exceptions: 'Every difference has a reason. Review the evidence, then record your decision.', vendors: 'Map statement names to the vendor names used in BILL.', connection: 'Try the workflow today. Connect your live BILL account after approval.' }[state.view];
  app.innerHTML = `<div class="shell"><aside class="sidebar"><div class="brand"><span class="brand-icon">${icon('ledger')}</span>Statement Desk</div><div class="nav-label">Workspace</div><nav class="nav" aria-label="Workspace navigation">${[['statements','folder','Statements',state.statements.length],['exceptions','flag','Exceptions',data.attention],['vendors','users','Vendors',''],['connection','plug','BILL connection','']].map(([view, glyph, label, count]) => `<button data-action="view" data-view="${view}" class="${state.view === view ? 'active' : ''}" ${state.view === view ? 'aria-current="page"' : ''} title="${label}">${icon(glyph)}${label}${count !== '' ? `<span class="count">${count}</span>` : ''}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="local-note">${icon('shield')}<strong>Your files stay with you</strong>PDFs are read in this browser. Save session keeps extracted rows and notes, not originals. Select PDFs again after leaving. Saved financial metadata is visible to anyone using this browser profile.</div><div class="profile"><div class="avatar">AP</div><div>Accounts payable<small>Prototype workspace</small></div></div></div></aside><main class="main"><header class="topbar"><div class="breadcrumb">AP workspace <span>/</span><strong>${state.view === 'connection' ? 'BILL connection' : state.view[0].toUpperCase() + state.view.slice(1)}</strong></div><div class="top-actions"><button class="button small subtle" data-action="save-session">${icon('save')}Save session</button><span class="connection-pill"><span class="dot"></span>${sourcePill()}</span></div></header><div class="content"><div class="heading"><div><div class="eyebrow">A clearer month-end</div><h1>${title}</h1><p>${subtitle}</p></div><div class="action-row">${state.view === 'statements' || state.view === 'exceptions' ? `<button class="button" data-action="export">${icon('down')}Export report</button><button class="button primary" data-action="upload" ${state.busy ? 'disabled' : ''}>${icon('plus')}Upload statements</button>` : ''}</div></div>${state.provider.simulated ? `<div class="notice">${icon('info')}<div><strong>You’re exploring a demonstration.</strong> BILL records and match results are simulated. Uploaded invoices have not been checked against your actual account.</div><div class="notice-actions"><button class="mini-link" data-action="view" data-view="connection">About the connection ${icon('arrow')}</button></div></div>` : !state.provider.loaded ? `<div class="notice blue">${icon('plug')}<div><strong>BILL is not connected yet.</strong> You can extract and review PDFs now. Invoice matching needs imported records or a live connection.</div></div>` : `<div class="notice blue">${icon('info')}<div><strong>Comparing against imported CSV records.</strong> ${esc(state.provider.label)} · ${state.provider.records.length} records. Coverage and historical balances require review.</div></div>`}${state.view === 'statements' || state.view === 'exceptions' ? `${metrics(data)}<div class="workspace-grid"><section class="panel">${state.view === 'statements' ? statementPanel(data) : exceptionPanel(data)}</section><aside class="right-rail">${rail(data)}</aside></div>` : state.view === 'vendors' ? vendorsPanel() : connectionPanel()}</div></main></div>`;
  bindDropzone();
}
function metrics(data) {
  return `<div class="metrics">${[
    ['Statements uploaded', state.statements.length, `${new Set(state.statements.map(d => d.vendor)).size} vendors in this workspace`, 'folder', ''],
    ['Matched invoices', data.matched, state.provider.simulated ? 'Against simulated BILL records' : 'Invoice and balance agree', 'check', 'good'],
    ['Needs attention', data.attention, `${data.reviewed} items reviewed by your team`, 'flag', 'warn'],
    ['Statement balances', money(data.balance), 'Reported totals across uploaded statements', 'ledger', ''],
  ].map(([label, value, detail, glyph, tone]) => `<div class="metric"><div class="metric-top">${label}<span class="metric-icon">${icon(glyph)}</span></div><div class="metric-value">${value}</div><div class="metric-detail ${tone}">${detail}</div></div>`).join('')}</div>`;
}
function toolbar() {
  return `<div class="toolbar"><div class="tabs" role="group" aria-label="Filter results">${[['all','All items'],['attention','Needs review'],['matched','Matched'],['reviewed','Reviewed']].map(([key,label]) => `<button class="${state.filter === key ? 'active' : ''}" data-action="filter" data-filter="${key}" aria-pressed="${state.filter === key}">${label}</button>`).join('')}</div><label class="search">${icon('search')}<input id="search" placeholder="Search vendor or invoice…" value="${esc(state.query)}" aria-label="Search vendor or invoice"></label></div>`;
}
function matchesQuery(text) { return text.toLowerCase().includes(state.query.toLowerCase().trim()); }
function statementPanel(data) {
  const docs = state.statements.filter(doc => {
    const rows = reconcile(doc, state.provider, state.mappings);
    return matchesQuery(`${doc.vendor} ${doc.filename} ${doc.rows.map(r => r.invoiceNumber).join(' ')}`) && (state.filter === 'all' || state.filter === 'attention' && (rows.some(isAttention) || !doc.confirmed) || state.filter === 'matched' && rows.some(r => r.status === 'matched') || state.filter === 'reviewed' && rows.some(r => state.resolutions[r.id]));
  });
  return `<div class="panel-title"><h2>Vendor statements</h2><small>${state.statements.length} documents</small></div><div class="dropzone" id="dropzone" role="region" aria-label="PDF upload area"><span class="upload-icon">${icon('upload')}</span><div><strong>Drop your vendor statements here</strong><p>Multiple PDFs · Scans supported · Processed on your device</p></div><button class="button small" data-action="upload" ${state.busy ? 'disabled' : ''}>Browse files</button></div>${state.busy ? `<div class="progress"><span class="spinner"></span>${esc(state.progress)}<div class="progress-bar"><span style="width:${Math.round(state.fraction * 100)}%"></span></div></div>` : ''}${state.errors.map(e => `<div class="file-error">${esc(e)}</div>`).join('')}${toolbar()}${docs.length ? `<div class="table-wrap"><table class="main-table"><thead><tr><th>Vendor / statement</th><th>As of</th><th>Invoices</th><th>Balance</th><th>Status</th><th></th></tr></thead><tbody>${docs.map(doc => { const summary = docSummary(doc); return `<tr data-action="open-doc" data-id="${doc.id}"><td><button data-action="open-doc" data-id="${doc.id}" style="text-align:left;padding:0">${vendorCell(doc)}</button></td><td class="numeric">${esc(doc.statementDate || 'Set date')}</td><td>${groupInvoices(doc).filter(r => r.kind === 'invoice').length}<small style="display:block;color:#9aa18f;font-size:9px;margin-top:4px">${doc.pageCount} ${doc.pageCount === 1 ? 'page' : 'pages'}${doc.ocr ? ' · OCR' : ''}</small></td><td class="numeric">${money(doc.declaredTotal ?? totals(doc).sum)}</td><td>${badge(summary.status, summary.label)}</td><td>${icon('arrow')}</td></tr>`; }).join('')}</tbody></table></div>` : `<div class="empty">${icon('folder')}<h3>${state.statements.length ? 'No statements match this filter' : 'Ready for your first statement'}</h3>${state.statements.length ? 'Try another filter or search.' : 'Upload a PDF to review its invoices, credits, and balances.'}</div>`}<div class="table-foot"><span>${docs.length} statements shown</span><button class="mini-link" data-action="clear">Clear workspace</button></div>`;
}
function exceptionPanel() {
  const rows = results().filter(row => matchesQuery(`${row.vendor} ${row.invoiceNumber} ${row.reason}`) && (state.filter === 'all' || state.filter === 'attention' && isAttention(row) || state.filter === 'matched' && row.status === 'matched' || state.filter === 'reviewed' && state.resolutions[row.id]));
  return `<div class="panel-title"><h2>Invoice review queue</h2><small>${rows.length} items</small></div><div style="height:20px"></div>${toolbar()}${rows.length ? `<div class="table-wrap"><table class="main-table result-table"><thead><tr><th>Vendor</th><th>Invoice</th><th>Statement balance</th><th>Result</th><th></th></tr></thead><tbody>${rows.map(row => `<tr data-action="open-result" data-doc="${row.statementId}" data-id="${row.id}"><td><button style="padding:0;text-align:left" data-action="open-result" data-doc="${row.statementId}" data-id="${row.id}"><strong>${esc(row.vendor)}</strong><small style="display:block;color:#929d87;font-size:9px;margin-top:4px">${row.kind === 'invoice' ? 'Invoice' : esc(row.kind)} · Page ${row.page}</small></button></td><td class="invoice-link">${esc(row.invoiceNumber || 'Account activity')}</td><td class="numeric">${money(row.outstanding)}</td><td>${badge(row.status)}${state.resolutions[row.id] ? '<span class="resolved-label">✓ Reviewed · decision recorded</span>' : ''}</td><td>${icon('arrow')}</td></tr>`).join('')}</tbody></table></div>` : `<div class="empty">${icon('check')}<h3>No items in this view</h3>Change the filter or upload another statement.</div>`}<div class="table-foot"><span>${rows.length} items shown · ${state.provider.simulated ? 'Simulated results' : 'BILL API offline'}</span><button class="mini-link" data-action="export">Download CSV</button></div>`;
}
function rail(data) {
  const percent = data.total ? Math.round(data.matched / data.total * 100) : 0;
  return `<div class="side-card"><div class="eyebrow" style="margin-bottom:15px">At a glance</div><h3>Reconciliation progress</h3><div class="review-number">${percent}%<small>matched</small></div><div class="review-bar"><span class="good" style="width:${percent}%"></span><span class="warn" style="width:${100-percent}%"></span></div><div class="legend-row"><span><i class="legend-dot"></i>Matched</span><strong>${data.matched}</strong></div><div class="legend-row"><span><i class="legend-dot" style="background:#e1b873"></i>Needs attention</span><strong>${data.attention}</strong></div><div class="legend-row"><span><i class="legend-dot" style="background:#9baf8a"></i>Reviewed</span><strong>${data.reviewed}</strong></div><p>${state.provider.simulated ? 'This is a preview of the workflow. Match percentages use fictional BILL data.' : 'A match confirms the compared records, not QuickBooks sync or historical completeness.'}</p><button class="button small" style="width:100%" data-action="view" data-view="exceptions">Open review queue ${icon('arrow')}</button></div><div class="side-card"><h3>A simpler statement check</h3><ol class="steps"><li><span class="step-number">1</span><div><strong>Upload your PDFs</strong>Digital and scanned statements.</div></li><li><span class="step-number">2</span><div><strong>Check the extraction</strong>Verify rows, credits, and totals.</div></li><li><span class="step-number">3</span><div><strong>Review the exceptions</strong>See the source and record a decision.</div></li></ol><button class="mini-link" data-action="demo">Load sample workspace ${icon('arrow')}</button></div>`;
}
function vendorsPanel() {
  const vendors = [...new Set(state.statements.map(d => d.vendor))];
  return `<section class="panel"><div class="panel-title"><h2>Vendor name mappings</h2><small>${vendors.length} vendors</small></div><div class="wide-panel"><p>Statement names and BILL vendor names can differ. Enter the exact name from your imported records. Mappings are saved in this browser.</p></div><div class="table-wrap"><table class="vendor-table"><thead><tr><th>Statement vendor</th><th>BILL vendor name</th><th>Statements</th><th></th></tr></thead><tbody>${vendors.map((vendor,i) => `<tr><td><strong>${esc(vendor)}</strong></td><td><input id="mapping-${i}" value="${esc(state.mappings[vendor] || vendor)}" aria-label="BILL vendor name for ${esc(vendor)}"></td><td>${state.statements.filter(d => d.vendor === vendor).length}</td><td><button class="button small" data-action="mapping" data-vendor="${esc(vendor)}" data-input="mapping-${i}">Save mapping</button></td></tr>`).join('')}</tbody></table></div>${vendors.length ? '' : '<div class="empty">Upload a statement to add its vendor.</div>'}</section>`;
}
function connectionPanel() {
  return `<div class="connection-layout"><section class="panel wide-panel"><div class="eyebrow">Your accounting source</div><h2 style="margin-top:10px">BILL, when you’re ready</h2><p>The prototype is ready to demonstrate statement extraction and exception review. Your live BILL account will be connected after your administrator approves production API access.</p><div class="connection-illustration"><span class="connection-node">Statement Desk</span>${icon('plug')}<span class="connection-node" style="color:#ed683e">BILL</span></div><div class="notice amber">${icon('info')}<div><strong>Live API connection is not implemented in this prototype.</strong> No credentials are collected. Production access needs a server-side connector and administrator setup.</div></div><h3 style="font-size:13px">Current data source</h3><p><strong>${esc(state.provider.label || 'None connected')}</strong><br>${state.provider.loaded ? `${state.provider.records.length} records · ${state.provider.simulated ? 'simulated' : 'imported CSV'}` : 'Upload PDFs to review extraction. Matching will remain unverified.'}</p><div class="action-row"><button class="button" data-action="disconnect">Use extraction only</button><button class="button primary" data-action="simulate" ${state.statements.length ? '' : 'disabled'}>Try simulated matching</button></div></section><section class="panel wide-panel"><h2>Test with your own records</h2><p>If your team can already export BILL data, a CSV lets you test actual invoice matching before API access is approved. This is optional.</p><ol class="steps"><li><span class="step-number">1</span><div><strong>Download the record template</strong>Keep invoice numbers as text, including leading zeros.</div></li><li><span class="step-number">2</span><div><strong>Prepare your BILL records</strong>Include paid and unpaid invoices, credits, and payment amounts. Confirm the export covers your statement dates.</div></li><li><span class="step-number">3</span><div><strong>Import and compare</strong>The import replaces the current sample record source.</div></li></ol><div class="action-row"><button class="button small" data-action="template">${icon('down')}CSV template</button><button class="button primary small" data-action="import">Import records</button></div><label class="field">Record snapshot date (optional)<input type="date" id="provider-date" value="${esc(state.provider.asOf || '')}"></label><p style="font-size:10px">Scheduled payments are displayed separately from cleared payments. Current data alone cannot prove balances at an earlier statement date.</p></section></div>`;
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
function closeOverlay() { overlay.innerHTML = ''; state.selected = null; state.selectedRow = null; priorFocus?.focus?.(); renderToken++; }
function getDoc() { return state.statements.find(d => d.id === state.selected); }
function openDoc(id, row = null) { priorFocus = document.activeElement; state.selected = id; state.selectedRow = row; state.drawerTab = row ? 'review' : 'extraction'; state.page = row ? reconcile(getDoc(), state.provider, state.mappings).find(r => r.id === row)?.page || 1 : 1; renderDrawer(); overlay.querySelector('.close')?.focus(); }
function renderDrawer() {
  const doc = getDoc(); if (!doc) return;
  const check = totals(doc);
  const reviewRows = reconcile(doc, state.provider, state.mappings);
  const row = reviewRows.find(r => r.id === state.selectedRow) || reviewRows.find(isAttention) || reviewRows[0];
  if (row && !state.selectedRow) state.selectedRow = row.id;
  const warnings = [...doc.warnings];
  if (check.difference !== 0 && check.difference !== null) warnings.push(`Extracted activity differs from the statement total by ${money(check.difference)}. Check missing rows, credits, or duplicate totals.`);
  if (check.difference === null) warnings.push('No statement total was identified. Enter it or verify completeness manually.');
  overlay.innerHTML = `<div class="overlay"><section class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><header class="drawer-head"><div><div class="eyebrow">${doc.demo ? 'Fictional demonstration' : 'Statement review'}</div><h2 id="drawer-title">${esc(doc.vendor)}</h2><small>${esc(doc.filename)} · ${doc.pageCount} ${doc.pageCount === 1 ? 'page' : 'pages'}${doc.ocr ? ' · scanned PDF' : ''}</small></div><button class="close" data-action="close" aria-label="Close statement">${icon('close')}</button></header><div class="drawer-body"><div class="drawer-tabs"><button class="button ${state.drawerTab === 'extraction' ? 'primary' : ''}" data-action="drawer-tab" data-tab="extraction">1. Check extraction</button><button class="button ${state.drawerTab === 'review' ? 'primary' : ''}" data-action="drawer-tab" data-tab="review">2. Compare & review</button><button class="button ${state.drawerTab === 'notes' ? 'primary' : ''}" data-action="drawer-tab" data-tab="notes">Notes & assignment</button><button class="button subtle danger" data-action="remove-doc">Remove statement</button></div>${doc.demo ? `<div class="notice">${icon('info')}<div>This document and its BILL records are fictional demonstration data.</div></div>` : ''}${state.drawerTab === 'extraction' ? extractionView(doc, check, warnings) : state.drawerTab === 'notes' ? notesView(doc) : row ? reviewView(doc, row, reviewRows) : '<div class="empty">No rows extracted. Add transaction rows in Check extraction.</div>'}</div></section></div>`;
  if (state.drawerTab !== 'notes') previewPDF(doc);
}
function extractionView(doc, check, warnings) {
  return `${warnings.length ? `<div class="notice amber">${icon('info')}<div>${warnings.map(w => `<div>${esc(w)}</div>`).join('')}</div></div>` : `<div class="notice">${icon('check')}<div>Extracted activity agrees with the statement total. Verify invoice numbers before confirming.</div></div>`}<div class="form-grid"><label class="field">Statement vendor<input id="doc-vendor" value="${esc(doc.vendor)}"></label><label class="field">Statement date<input type="date" id="doc-date" value="${esc(doc.statementDate)}"></label><label class="field">Printed statement total (USD)<input id="doc-total" value="${doc.declaredTotal == null ? '' : (doc.declaredTotal / 100).toFixed(2)}" inputmode="decimal"></label><label class="field">Extracted activity total<input readonly value="${money(check.sum)}"></label></div><div class="source-layout"><div><div class="page-control"><strong>Extracted transactions · ${doc.rows.length}</strong><button class="button small" data-action="add-row">${icon('plus')}Add row</button></div><div class="table-wrap"><table class="edit-table"><thead><tr><th>Reference</th><th>Type</th><th>Amount</th><th>Invoice balance</th><th>Page</th><th></th></tr></thead><tbody>${doc.rows.map(row => `<tr data-row="${row.id}"><td><input class="ref" name="reference" value="${esc(row.invoiceNumber)}" aria-label="Invoice reference"></td><td><select name="type" aria-label="Transaction type">${['invoice','credit','payment','opening'].map(type => `<option ${row.type === type ? 'selected' : ''}>${type}</option>`).join('')}</select></td><td><input name="amount" value="${(row.amount / 100).toFixed(2)}" inputmode="decimal" aria-label="Original amount"></td><td><input name="balance" value="${row.balance == null ? '' : (row.balance / 100).toFixed(2)}" inputmode="decimal" aria-label="Invoice outstanding balance"></td><td><input class="small-col" name="page" type="number" min="1" max="${doc.pageCount}" value="${row.page}" aria-label="Source page"></td><td><button data-action="delete-row" data-id="${row.id}" aria-label="Remove row">${icon('trash')}</button></td></tr>`).join('')}</tbody></table></div><p style="font-size:10px;line-height:1.7;color:#849277">Amounts are signed: invoices positive, credits and payments negative. Leave invoice balance blank when only a running account balance is supplied. Reference numbers remain text.</p><div class="action-row"><button class="button" data-action="save-extraction">Save corrections</button><button class="button primary" data-action="confirm-extraction">${icon('check')}Confirm extracted rows</button></div><details style="margin-top:20px;font-size:11px;color:#748967"><summary>Extracted source text</summary><pre class="raw-text">${esc(doc.rawText || doc.rows.map(r => r.source).join('\n'))}</pre></details></div>${pdfPanel(doc)}</div>`;
}
function pdfPanel(doc) { return `<div><div class="page-control"><strong>Original statement</strong><label>Page <select id="page-select" aria-label="Preview page">${Array.from({length:doc.pageCount},(_,i) => `<option value="${i+1}" ${state.page === i+1 ? 'selected' : ''}>${i+1}</option>`).join('')}</select></label></div>${files.has(doc.id) ? '<div class="pdf-view"><canvas id="pdf-canvas" aria-label="Original PDF page"></canvas><div id="pdf-loading">Loading page…</div></div>' : `<div class="no-source">${icon('ledger')}<br>${doc.demo ? 'This is a fictional sample. Upload a PDF to see its original page here.' : 'PDF previews are kept only for this browser session. Re-upload the original PDF to preview it again.'}</div>`}</div>`; }
function reviewView(doc, row, rows) {
  const bill = row.candidates[0];
  const resolution = state.resolutions[row.id];
  return `<label class="field">Select invoice or account activity<select id="row-select">${rows.map(r => `<option value="${r.id}" ${r.id === row.id ? 'selected' : ''}>${esc(r.invoiceNumber || r.kind)} · ${statuses[r.status].label}</option>`).join('')}</select></label><div class="notice ${row.status === 'matched' ? '' : 'amber'}">${icon(row.status === 'matched' ? 'check' : 'info')}<div>${badge(row.status)}<div style="margin-top:7px">${esc(row.reason)}</div>${row.simulated ? '<div><strong>Simulated result — not verified against your BILL account.</strong></div>' : ''}</div></div><div class="evidence-grid"><div class="evidence-card"><h3>Vendor statement</h3>${[['Reference',row.invoiceNumber || 'Account activity'],['Original amount',money(row.originalAmount)],['Outstanding balance',money(row.outstanding)],['Statement date',doc.statementDate || 'Not identified'],['Source page',row.page]].map(([k,v]) => `<div class="evidence-line"><span>${k}</span><strong>${esc(v)}</strong></div>`).join('')}</div><div class="evidence-card"><h3>${state.provider.simulated ? 'Simulated BILL record' : 'Imported BILL record'}</h3>${bill ? [['Reference',bill.invoiceNumber],['Original amount',money(bill.amount)],['Applied credits',money(bill.creditAmount || 0)],['Cleared payments',money(bill.clearedPaymentAmount || 0)],['Scheduled payments',money(bill.scheduledAmount || 0)]].map(([k,v]) => `<div class="evidence-line"><span>${k}</span><strong>${esc(v)}</strong></div>`).join('') : `<p style="font-size:11px;line-height:1.8;color:#829175">${state.provider.loaded ? 'No matching record available in this dataset.' : 'No BILL records connected. This invoice has not been checked.'}</p>`}${row.candidates.length > 1 ? `<p style="font-size:11px;color:#a47a3f">${row.candidates.length} candidates: ${row.candidates.map(b => esc(`${b.id}: ${money(b.amount)}`)).join(' · ')}</p>` : ''}</div></div><div class="source-layout"><div><h3 style="font-size:12px">Statement activity for this reference</h3>${row.activity.map(a => `<div class="activity-list"><div>${esc(a.type)} · ${esc(a.invoiceNumber || 'account')}<small>${esc(a.date || 'Date not supplied')} · page ${a.page}</small></div><strong>${money(a.amount)}</strong></div>`).join('')}<label class="field">Review decision<select id="review-decision">${['Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed'].map(v => `<option ${resolution?.decision === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label><label class="field">Review note<textarea id="review-note" placeholder="Explain your decision or next step…">${esc(resolution?.note || '')}</textarea></label><div class="action-row"><button class="button primary" data-action="resolve">${icon('check')}Save review decision</button>${resolution ? '<button class="button" data-action="reopen">Reopen item</button>' : ''}</div>${resolution ? `<p style="font-size:10px;color:#7e916c">Reviewed ${esc(new Date(resolution.at).toLocaleString())}. The original matching result is preserved.</p>` : ''}</div>${pdfPanel(doc)}</div>`;
}
function notesView(doc) { return `<label class="field">Assigned reviewer<input id="assignee" value="${esc(doc.assignee)}" placeholder="Name or initials"></label><label class="field">Statement notes<textarea id="doc-notes" style="min-height:170px" placeholder="Vendor follow-up, unresolved opening balances, or review context…">${esc(doc.notes)}</textarea></label><button class="button primary" data-action="save-notes">Save notes</button><p style="font-size:11px;line-height:1.8;color:#879578">Use Save session to retain this workspace and notes in this browser. This prototype does not share assignments between devices.</p>`; }
async function previewPDF(doc) {
  const canvas = document.querySelector('#pdf-canvas'); if (!canvas || !files.has(doc.id)) return;
  const token = ++renderToken;
  try { extractor ??= await import('./extraction.mjs'); if (token !== renderToken) return; await extractor.renderPage(files.get(doc.id), state.page, canvas); if (token === renderToken) document.querySelector('#pdf-loading')?.remove(); }
  catch(error) { if (token === renderToken) { const loading = document.querySelector('#pdf-loading'); if (loading) loading.textContent = `Preview unavailable: ${error.message}`; } }
}
function collectRows(doc) {
  const rows = [...overlay.querySelectorAll('[data-row]')].map(tr => {
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
function collectDoc(doc) {
  doc.rows = collectRows(doc);
  doc.vendor = document.querySelector('#doc-vendor').value.trim() || 'Unidentified vendor';
  doc.statementDate = document.querySelector('#doc-date').value;
  const total = document.querySelector('#doc-total').value.trim();
  if (total && cents(total) == null) throw new Error('Enter a valid printed statement total.');
  doc.declaredTotal = total ? cents(total) : null;
}
async function uploadPDFs(fileList) {
  if (state.busy) return;
  const pdfs = [...fileList].filter(file => file.name.toLowerCase().endsWith('.pdf'));
  if (!pdfs.length) { toast('Choose PDF statement files.', true); return; }
  if (pdfs.length > 150) { toast('Upload at most 150 PDFs in one batch.', true); return; }
  if (state.statements.length && state.statements.every(d => d.demo)) { state.statements = []; state.resolutions = {}; }
  if (state.provider.simulated) state.provider = { loaded: false, simulated: false, records: [], label: 'Not connected' };
  state.busy = true; state.errors = []; state.query = ''; state.filter = 'all'; state.view = 'statements'; render();
  try {
    extractor ??= await import('./extraction.mjs');
    for (let i = 0; i < pdfs.length; i++) {
      const file = pdfs[i];
      const existing = state.statements.find(d => d.filename === file.name && d.fileSize === file.size && d.fileModified === file.lastModified);
      if (existing) { files.set(existing.id, file); toast(`Original PDF attached again: ${file.name}`); continue; }
      try {
        const doc = await extractor.extractPDF(file, progress => { state.progress = `${i+1}/${pdfs.length} · ${file.name} · page ${progress.page}/${progress.total} · ${progress.stage}`; state.fraction = (i + progress.fraction) / pdfs.length; const node = document.querySelector('.progress'); if (node) node.innerHTML = `<span class="spinner"></span>${esc(state.progress)}<div class="progress-bar"><span style="width:${Math.round(state.fraction*100)}%"></span></div>`; });
        doc.fileSize = file.size; doc.fileModified = file.lastModified; state.statements.push(doc); files.set(doc.id, file);
      } catch (error) { state.errors.push(`${file.name}: ${error.message}`); }
      render();
    }
  } catch(error) { state.errors.push(`PDF processing unavailable: ${error.message}`); }
  finally { await extractor?.stopOCR?.(); state.busy = false; state.progress = ''; render(); document.querySelector('#pdf-input').value = ''; }
  toast(`${state.statements.length} statements ready. Review extraction before matching.`, !!state.errors.length);
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
  try { const records = importRecords(await file.text()); state.provider = { loaded: true, simulated: false, records, label: file.name, refreshedAt: new Date().toISOString(), asOf: document.querySelector('#provider-date')?.value || '' }; state.resolutions = {}; render(); toast(`${records.length} BILL records imported. Check date and export coverage.`); }
  catch(error) { toast(error.message, true); }
  e.target.value = '';
});
document.addEventListener('input', e => {
  if (e.target.id === 'search') { const pos = e.target.selectionStart; state.query = e.target.value; render(); const input = document.querySelector('#search'); input?.focus(); input?.setSelectionRange(pos,pos); }
});
document.addEventListener('change', e => {
  if (e.target.id === 'page-select') { state.page = Number(e.target.value); previewPDF(getDoc()); }
  if (e.target.id === 'row-select') { state.selectedRow = e.target.value; const row = reconcile(getDoc(), state.provider, state.mappings).find(r => r.id === state.selectedRow); state.page = row?.page || 1; renderDrawer(); }
  if (e.target.id === 'provider-date') state.provider.asOf = e.target.value;
});
document.addEventListener('click', async e => {
  if (e.target.classList.contains('overlay')) { closeOverlay(); return; }
  const target = e.target.closest('[data-action]'); if (!target || target.disabled) return;
  const action = target.dataset.action;
  try {
    if (action === 'view') { state.view = target.dataset.view; state.filter = state.view === 'exceptions' ? 'attention' : 'all'; state.query = ''; render(); }
    if (action === 'filter') { state.filter = target.dataset.filter; render(); }
    if (action === 'upload') document.querySelector('#pdf-input').click();
    if (action === 'import') document.querySelector('#csv-input').click();
    if (action === 'open-doc') openDoc(target.dataset.id);
    if (action === 'open-result') openDoc(target.dataset.doc, target.dataset.id);
    if (action === 'close') closeOverlay();
    if (action === 'drawer-tab') { state.drawerTab = target.dataset.tab; renderDrawer(); }
    if (action === 'save-extraction' || action === 'confirm-extraction') {
      const doc = getDoc(); for (const row of groupInvoices(doc)) delete state.resolutions[row.id]; collectDoc(doc); doc.confirmed = false;
      if (action === 'confirm-extraction') {
        if (!doc.rows.length || doc.vendor === 'Unidentified vendor') throw new Error('Set the vendor and add transaction rows before confirming.');
        doc.confirmed = true; doc.rows.forEach(r => { r.confidence = 99; }); state.drawerTab = 'review';
      }
      render(); renderDrawer(); toast(action === 'confirm-extraction' ? 'Extraction confirmed. Matching results are ready for review.' : 'Corrections saved. Confirm the rows when ready.');
    }
    if (action === 'add-row') { const doc = getDoc(); collectDoc(doc); doc.rows.push({ id: uid(), type: 'invoice', invoiceNumber: '', amount: 0, balance: null, page: state.page, confidence: 99, source: 'Manually added row' }); doc.confirmed = false; renderDrawer(); }
    if (action === 'delete-row') { const doc = getDoc(); collectDoc(doc); doc.rows = doc.rows.filter(r => r.id !== target.dataset.id); doc.confirmed = false; renderDrawer(); }
    if (action === 'save-notes') { const doc = getDoc(); doc.notes = document.querySelector('#doc-notes').value; doc.assignee = document.querySelector('#assignee').value; toast('Notes saved in this workspace. Use Save session to keep them.'); }
    if (action === 'resolve') { const note = document.querySelector('#review-note').value.trim(); if (!note) throw new Error('Add a note explaining your review decision.'); state.resolutions[state.selectedRow] = { note, decision: document.querySelector('#review-decision').value, at: new Date().toISOString() }; render(); renderDrawer(); toast('Review recorded. The matching evidence is preserved.'); }
    if (action === 'reopen') { delete state.resolutions[state.selectedRow]; render(); renderDrawer(); }
    if (action === 'mapping') { const value = document.getElementById(target.dataset.input).value.trim(); if (!value) throw new Error('Enter the BILL vendor name.'); state.mappings[target.dataset.vendor] = value; const result = saveVendorMappings(browserStorage(), state.mappings); render(); if (!result.ok) throw new Error(result.error); toast('Vendor mapping saved in this browser.'); }
    if (action === 'save-session') { const result = saveSession(browserStorage(), { version: 1, statements: state.statements, provider: state.provider, resolutions: state.resolutions }); if (!result.ok) throw new Error(result.error); toast('Session saved in this browser. Select original PDFs again after leaving.'); }
    if (action === 'disconnect') { state.provider = { loaded: false, simulated: false, records: [], label: 'Not connected' }; state.resolutions = {}; render(); toast('Extraction-only mode. No live connection was changed.'); }
    if (action === 'simulate') modal('Try simulated BILL matching?', '<p>This generates fictional BILL records from the extracted invoices, with intentional missing invoices, amount differences, and payment scenarios.</p><p><strong>It demonstrates the review workflow. It does not establish whether any real invoice is in BILL.</strong></p>', 'confirm-simulate', 'Generate demo records');
    if (action === 'confirm-simulate') { state.provider = simulateRecords(state.statements); state.resolutions = {}; closeOverlay(); render(); toast('Simulated records generated. Confirm PDF extraction to see comparisons.'); }
    if (action === 'demo') modal('Load the sample workspace?', '<p>This replaces the current in-memory workspace with three fictional vendors and simulated BILL records. Your original PDF files are unaffected.</p>', 'confirm-demo', 'Load sample');
    if (action === 'confirm-demo') { Object.assign(state, createDemo(), { resolutions: {}, query: '', filter: 'all', view: 'statements', errors: [] }); files.clear(); closeOverlay(); render(); }
    if (action === 'clear') modal('Clear this workspace?', '<p>This removes extracted statements, imported records, review notes, vendor mappings, and saved AP data from this browser. It does not delete your original PDFs or change BILL.</p>', 'confirm-clear', 'Clear workspace');
    if (action === 'confirm-clear') { const result = clearSession(browserStorage()); if (!result.ok) throw new Error(result.error); state.statements = []; state.provider = { loaded: false, records: [], simulated: false }; state.resolutions = {}; state.mappings = {}; state.errors = []; files.clear(); closeOverlay(); render(); toast('Browser-local AP data cleared.'); }
    if (action === 'remove-doc') { const doc = getDoc(); const id = doc.id; modal('Remove this statement?', `<p>Remove ${esc(doc.filename)} and its review notes from this workspace? Your original PDF will not be deleted.</p>`, 'confirm-remove', 'Remove'); state.selected = id; }
    if (action === 'confirm-remove') { const doc = getDoc(); for (const row of groupInvoices(doc)) delete state.resolutions[row.id]; state.statements = state.statements.filter(d => d.id !== doc.id); files.delete(doc.id); closeOverlay(); render(); }
    if (action === 'template') download('bill-record-template.csv', toCSV([['vendor','invoiceNumber','amount','kind','currency','clearedPaymentAmount','scheduledAmount','creditAmount','paymentDate','id'],['Example Vendor','000123','125.00','invoice','USD','0.00','0.00','0.00','','sample-only']]));
    if (action === 'export') {
      const header = ['vendor','statement','statementDate','invoiceNumber','activityType','originalAmount','statementOutstanding','result','reason','source','simulated','reviewDecision','reviewNote','assignedReviewer'];
      const rows = results().map(r => { const doc = state.statements.find(d => d.id === r.statementId); const resolution = state.resolutions[r.id]; return [r.vendor,doc.filename,doc.statementDate,r.invoiceNumber,r.kind,r.originalAmount == null ? '' : (r.originalAmount/100).toFixed(2),r.outstanding == null ? '' : (r.outstanding/100).toFixed(2),statuses[r.status].label,r.reason,state.provider.label || 'No BILL data',r.simulated ? 'YES — SIMULATED' : 'NO',resolution?.decision || '',resolution?.note || '',doc.assignee || '']; });
      download('statement-reconciliation.csv', toCSV([header,...rows])); toast('Report exported with source and simulation labels.');
    }
  } catch(error) { toast(error.message || 'This action could not be completed.', true); }
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
