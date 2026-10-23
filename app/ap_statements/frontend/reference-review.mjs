import {money,invoiceKey,statuses} from './core.mjs';
import {adventureAmountDiscrepancy} from './adventure-reference.mjs';
import {manualCheckFor} from './manual-review.mjs';
export {adventureAmountDiscrepancy} from './adventure-reference.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const canonical=value=>JSON.stringify(Object.fromEntries(Object.entries(value||{}).sort(([a],[b])=>a.localeCompare(b))));
export function confirmableCandidate(row,index){
  const bill=Number.isInteger(index)?row.candidates?.[index]:null;
  return bill&&['possible','ambiguous','amount'].includes(row.status)&&['amount','reference'].includes(row.matchMethod)&&!row.preview&&!row.simulated&&!row.duplicate&&(row.kind??'invoice')==='invoice'&&(bill.kind??'invoice')==='invoice'&&!bill.sourceIssues&&(!bill.currency||bill.currency==='USD')&&
    invoiceKey(row.invoiceNumber)&&invoiceKey(bill.invoiceNumber)&&Number.isSafeInteger(row.originalAmount)&&Number.isSafeInteger(bill.amount)&&
    row.candidates.filter(item=>canonical(item)===canonical(bill)).length===1?bill:null;
}
export function confirmInvoiceCandidate(doc,row,index,prior={}){
  const bill=confirmableCandidate(row,index);if(!doc.confirmed||!bill)throw Error('Check the PDF and choose a unique same-vendor candidate before confirming your review.');
  const different=row.originalAmount!==bill.amount;
  const decision=different?'Investigate amount difference':prior.decision||'Reviewed — no action needed';
  const evidence=`Manually confirmed same invoice: statement ${row.invoiceNumber} (${money(row.originalAmount)}) / BILL ${bill.invoiceNumber} (${money(bill.amount)}). Original references and matching result retained.${different?' Amount discrepancy requires follow-up.':''}`;
  return {decision,note:[prior.note?.trim(),evidence].filter(Boolean).join('\n'),confirmedMatch:{statementReference:row.invoiceNumber,statementAmount:row.originalAmount,candidate:structuredClone(bill)}};
}
export function confirmReferenceReview(doc,row,prior={}){
  if(row.candidates?.length!==1)throw Error('Choose a single candidate before confirming your review.');
  return confirmInvoiceCandidate(doc,row,0,prior);
}
export function confirmedInvoiceCandidate(row,resolution){
  const proof=resolution?.confirmedMatch;
  if(resolution?.decision!=='Reviewed — no action needed'||!Number.isFinite(Date.parse(resolution?.at))||!proof||proof.statementReference!==row.invoiceNumber||proof.statementAmount!==row.originalAmount)return null;
  const index=row.candidates?.findIndex(item=>canonical(item)===canonical(proof.candidate));
  const bill=confirmableCandidate(row,index);
  return bill&&bill.amount===row.originalAmount?bill:null;
}
export function invoiceResult(row,resolution){
  const manual=!!confirmedInvoiceCandidate(row,resolution),automatic=['matched','presence'].includes(row.status);
  const checkedManually=!!manualCheckFor(row,resolution);
  return {found:manual||automatic,manual,checkedManually,label:checkedManually?'Checked manually in BILL':manual?'Invoice found':adventureAmountDiscrepancy(row)?'Amount discrepancy':statuses[row.status]?.label||row.status,tone:checkedManually?(resolution.decision==='Reviewed — no action needed'?'green':'amber'):manual||automatic?'green':statuses[row.status]?.tone||'amber'};
}
export function reviewDecisionOptions(row){
  const options=['Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed'];
  return options.map(value=>[value,value]);
}
export function adventureFollowUp(row,action,note=''){
  if(!adventureAmountDiscrepancy(row))throw Error('Open an Adventure in Food amount discrepancy before recording a follow-up.');
  const choices={credit:['Follow up with vendor','Request vendor credit'],bill:['Request missing invoice','Additional bill needed'],investigate:['Investigate amount difference','Investigate']};
  if(!Object.hasOwn(choices,action))throw Error('Choose a valid follow-up action.');
  const [decision,label]=choices[action],bill=row.candidates[0];
  const entry=`Follow-up action: ${label}. Adventure in Food statement ${row.invoiceNumber} (${money(row.originalAmount)}) / BILL ${bill.invoiceNumber} (${money(bill.amount)}). Difference: ${money(Math.abs(row.originalAmount-bill.amount))}. Verify the original invoice and payment; no bill or credit was created.`;
  const priorNote=String(note).trim();
  return {decision,note:priorNote.includes(entry)?priorNote:[priorNote,entry].filter(Boolean).join('\n')};
}
export function adventureDiscrepancyHTML(row,readOnly=false){
  if(!adventureAmountDiscrepancy(row))return '';
  const bill=row.candidates[0],difference=row.originalAmount-bill.amount;
  return `<section class="notice amber adventure-discrepancy"><div><strong>Amount discrepancy</strong><p>Statement: ${money(row.originalAmount)} · BILL: ${money(bill.amount)}<br>Difference: ${money(Math.abs(difference))} (statement ${difference>0?'higher':'lower'}).</p>${!bill.currency?'<p>Currency is not supplied; currency is not verified.</p>':''}<p>Check the original invoice and actual payment. If an overpayment is confirmed, request a vendor credit; if an additional amount is owed, review whether an additional bill is needed. No bill or credit is created by this app.</p>${readOnly?'':`<div class="action-row">${[['credit','Request vendor credit'],['bill','Additional bill needed'],['investigate','Investigate']].map(([action,label])=>`<button class="button small" data-action="adventure-follow-up" data-followup="${action}">${label}</button>`).join('')}</div><small>These buttons save a follow-up decision and note only.</small>`}</div></section>`;
}
export function candidateConfirmationHTML(doc,row,index,readOnly=false){
  if(readOnly||!doc.confirmed||row.candidates?.length<2||!confirmableCandidate(row,index))return '';
  return `<button class="button small" data-action="confirm-candidate" data-candidate="${index}">Confirm this invoice & save review</button>`;
}
export function referenceReviewHTML(doc,row,readOnly=false){
  if(adventureAmountDiscrepancy(row))return '';
  const bill=row.candidates?.length===1?confirmableCandidate(row,0):null;if(!bill||readOnly||!doc.confirmed||invoiceKey(row.invoiceNumber)===invoiceKey(bill.invoiceNumber))return '';
  const different=row.originalAmount!==bill.amount;
  return `<section class="notice amber reference-review"><div><strong>Reference differs — review both documents</strong><p>Statement: <b>${esc(row.invoiceNumber)}</b> · ${money(row.originalAmount)}<br>BILL: <b>${esc(bill.invoiceNumber)}</b> · ${money(bill.amount)}</p>${different?`<p>Amount difference: ${money(bill.amount-row.originalAmount)}. This stays flagged for investigation.</p>`:''}<button class="button" data-action="confirm-reference">${different?'Confirm reference; keep amount discrepancy':'Confirm same invoice & save review'}</button><p>Records your explicit review. Original references, source warnings, and comparison evidence remain unchanged. This does not verify payment settlement.</p></div></section>`;
}
