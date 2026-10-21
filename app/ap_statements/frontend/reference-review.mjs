import {money,invoiceKey} from './core.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function candidate(row){
  const bill=row.candidates?.length===1?row.candidates[0]:null;
  return bill&&['possible','amount'].includes(row.status)&&row.matchMethod==='amount'&&!row.preview&&!bill.sourceIssues&&(!bill.currency||bill.currency==='USD')&&
    invoiceKey(row.invoiceNumber)&&invoiceKey(bill.invoiceNumber)&&invoiceKey(row.invoiceNumber)!==invoiceKey(bill.invoiceNumber)&&Number.isSafeInteger(row.originalAmount)&&Number.isSafeInteger(bill.amount)?bill:null;
}
export function confirmReferenceReview(doc,row,prior={}){
  const bill=candidate(row);if(!doc.confirmed||!bill)throw Error('Check the PDF and review a single same-vendor candidate before confirming the reference.');
  const different=row.originalAmount!==bill.amount;
  const decision=different?'Investigate amount difference':prior.decision||'Reviewed — no action needed';
  const evidence=`Manually confirmed same invoice: statement ${row.invoiceNumber} (${money(row.originalAmount)}) / BILL ${bill.invoiceNumber} (${money(bill.amount)}). Original references and matching result retained.${different?' Amount discrepancy requires follow-up.':''}`;
  return {decision,note:[prior.note?.trim(),evidence].filter(Boolean).join('\n')};
}
export function referenceReviewHTML(doc,row,readOnly=false){
  const bill=candidate(row);if(!bill||readOnly||!doc.confirmed)return '';
  const different=row.originalAmount!==bill.amount;
  return `<section class="notice amber reference-review"><div><strong>Reference differs — review both documents</strong><p>Statement: <b>${esc(row.invoiceNumber)}</b> · ${money(row.originalAmount)}<br>BILL: <b>${esc(bill.invoiceNumber)}</b> · ${money(bill.amount)}</p>${different?`<p>Amount difference: ${money(bill.amount-row.originalAmount)}. This stays flagged for investigation.</p>`:''}<button class="button" data-action="confirm-reference">${different?'Confirm reference; keep amount discrepancy':'Confirm same invoice & save review'}</button><p>Records your explicit review. Original references, source warnings, and comparison evidence remain unchanged. This does not verify payment settlement.</p></div></section>`;
}
