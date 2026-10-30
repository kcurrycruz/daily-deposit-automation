import {rangeCoverageText} from './bill-range.mjs';
import {billDataSummary,invoiceFound,readingIssues} from './simple-flow.mjs';
import {resolveStatementVendor,providerVendors} from './vendor-identity.mjs';
import {money} from './core.mjs';
import {nyTimestamp} from './history.mjs';
import {vendorPickerHTML} from './vendor-picker.mjs';
import {invoiceResult} from './reference-review.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function billDataHTML(provider,now=new Date()){
  if(provider.error)return `<section class="bill-data-strip update-due" aria-label="Saved BILL data"><div><strong>Saved BILL data temporarily unavailable</strong><p>${esc(provider.label||'Saved export')}</p><small>Pinned manual reviews remain available. Latest-data comparisons, saves and completion require reconnecting.</small></div><button class="button" data-action="retry-bill-source">Retry loading BILL data</button></section>`;
  const info=billDataSummary(provider,now);
  return `<section class="bill-data-strip ${info.updateDue?'update-due':''}" aria-label="Saved BILL data"><div><strong>${info.ready?'BILL data saved':'Add your BILL data once'}</strong><p>${info.ready?`${info.count.toLocaleString()} records · ${esc(provider.label)} · Last updated: ${info.dateKnown?esc(nyTimestamp(info.updatedAt)):'date unavailable'}`:'Upload the original Bills CSV export. We’ll keep it for every new statement.'}</p><small>${provider.workingSet?esc(rangeCoverageText(provider.workingSet))+" · ":""}${info.ready?(info.updateDue?'Weekly refresh due. You can still check statements against the saved records.':'Ready for arriving statements. Update the export about once a week.'):'After that, just upload statements as they arrive.'}</small></div><div class="action-row"><button class="button ${info.ready?'':'primary'}" data-action="import">${info.ready?'Update BILL data':'Upload BILL data'}</button><button class="button small subtle" data-action="view" data-view="connection">Details</button></div></section>`;
}
export function uploadReviewHTML(state){
  return `<section class="upload-review-start"><button type="button" class="dropzone" id="dropzone" data-action="upload" aria-label="Add statements: drag PDFs here or click to browse files" ${state.busy?'disabled':''}><span class="dropzone-symbol" aria-hidden="true">↑</span><span class="dropzone-copy"><strong>Add statements</strong><small>Drag statement PDFs here or browse files. <span class="dropzone-limits">Up to 20 files · 20 MiB each</span></small></span><span class="button primary dropzone-action">Browse files</span></button>${state.busy?`<p class="guide-progress" role="status">Reading your PDFs… ${esc(state.progress||'')}</p>`:''}${(state.errors||[]).map(e=>`<div class="file-error">${esc(e)}</div>`).join('')}</section>`;
}
export function vendorQuestionHTML(doc,provider,mappings={},readOnly=false,pickerState){
  if(readOnly||doc.reviewMode==='manual'||!provider.loaded)return '';
  if(provider.scopes&&!provider.directoryComplete)return '<p role="status">Loading saved BILL vendors…</p>';
  const choice=resolveStatementVendor(doc.vendor,providerVendors(provider,doc.id),mappings);
  if(choice.vendor)return `<div class="vendor-recognized">BILL vendor: <strong>${esc(choice.vendor)}</strong> · ${choice.status==='remembered'?'your saved choice':'recognized automatically'}</div>`;
  const first=choice.candidates.length===1?choice.candidates[0]:null;
  return `<section class="vendor-question" aria-label="Confirm statement vendor"><strong>${first?`Is “${esc(doc.vendor)}” the same vendor as “${esc(first)}”?`:'Which BILL vendor sent this statement?'}</strong><p>${first?'Confirm once. We’ll remember your answer for future statements.':'Choose the company from your saved BILL data. Invoice numbers alone don’t identify a vendor.'}</p>${first?`<button class="button primary" data-action="vendor-confirm" data-vendor="${esc(first)}">Yes, same vendor</button>`:''}<details ${first?'':'open'}><summary>Choose another vendor</summary>${vendorPickerHTML(choice.choices,pickerState)}</details></section>`;
}
export function statementOverviewHTML(doc,rows,readOnly=false,resolutions={}){
  const found=rows.filter(row=>invoiceFound(row,resolutions[row.id])).length,issues=readingIssues(doc);
  let linkedCreditCount=0;
  const tableRows=rows.map(row=>{
    const result=invoiceResult(row,resolutions[row.id]);
    const credits=doc.layout==='ace'&&row.kind==='invoice'?(row.activity||[]).filter(activity=>activity.type==='credit'):[];
    linkedCreditCount+=credits.length;
    const invoice=`<tr data-action="select-invoice" data-id="${esc(row.id)}" tabindex="0" aria-label="Review invoice ${esc(row.invoiceNumber||row.kind)}"><td><button class="invoice-link" data-action="select-invoice" data-id="${esc(row.id)}">${esc(row.invoiceNumber||row.kind)}</button></td><td>${money(row.originalAmount)}</td><td><span class="badge ${result.tone}">${esc(result.label)}</span>${row.preview?' <small>Check PDF</small>':''}</td></tr>`;
    const linked=credits.map(credit=>`<tr class="linked-credit-row" aria-label="Statement credit ${esc(credit.invoiceNumber)} linked to invoice ${esc(row.invoiceNumber)}"><td><strong>${esc(credit.invoiceNumber)}</strong><small>Statement credit · linked to ${esc(row.invoiceNumber)}</small></td><td>${money(credit.amount)}</td><td><span class="badge amber">Credit not verified</span><button class="mini-link" data-action="select-invoice" data-id="${esc(row.id)}" aria-label="View invoice activity for credit ${esc(credit.invoiceNumber)}">View invoice activity</button></td></tr>`).join('');
    return invoice+linked;
  }).join('');
  const creditNote=linkedCreditCount?`<div class="notice blue linked-credit-note" role="note"><div>${linkedCreditCount} linked statement ${linkedCreditCount===1?'credit is':'credits are'} shown below. Credits are not verified by an invoice match. Open invoice activity to review the credit.</div></div>`:'';
  return `<section class="statement-overview" id="invoice-overview"><div class="statement-overview-heading"><div><h3>Invoice check</h3><p>${found} found in BILL · ${rows.length-found} need attention${!doc.confirmed?' · preliminary until you check the PDF':''}</p></div>${!readOnly&&!doc.confirmed?'<button class="button" data-action="confirm-reading">I checked the PDF reading</button>':''}</div>${!readOnly&&!doc.confirmed?`<div class="notice ${issues.length?'amber':'blue'}"><div>${issues.length?esc(issues.join(' ')):'We’ve compared the extracted rows automatically.'} Verify the reading against the original before finishing. <button class="mini-link" data-action="drawer-tab" data-tab="extraction">Check PDF or correct rows</button></div></div>`:''}${creditNote}<div class="table-wrap"><table class="main-table"><thead><tr><th>Invoice</th><th>Original amount</th><th>Result</th></tr></thead><tbody>${tableRows}</tbody></table></div></section>`;
}
