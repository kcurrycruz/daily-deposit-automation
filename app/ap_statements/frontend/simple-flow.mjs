import {reconcile,totals} from './core.mjs';
import {providerVendors} from './vendor-identity.mjs';
export const invoiceFound=row=>['matched','presence'].includes(row.status);
export function defaultReviewDecision(row,resolution){
  if(resolution?.decision)return resolution.decision;
  if(invoiceFound(row)&&!row.preview&&!row.simulated&&row.matchMethod==='reference'&&row.candidates?.length===1)
    return 'Reviewed — no action needed';
  return '';
}
export async function confirmVendor(doc,name,shared,persistDoc){
  if(!providerVendors(shared.state.provider,doc.id).some(record=>record.vendor===name))throw Error('Choose a vendor from the saved BILL data.');
  if(!doc.vendor?.trim()||['unidentified vendor','unknown','unidentified'].includes(doc.vendor.trim().toLowerCase())){
    doc.vendor=name;doc.confirmed=false;return persistDoc(doc);
  }
  return shared.saveMapping({vendor:doc.vendor,bill_vendor:name},shared.state.mappingVersions[doc.vendor]||0);
}
export function statementComparisons(doc,provider,mappings={}){
  if(doc.confirmed)return reconcile(doc,provider,mappings);
  return reconcile({...doc,confirmed:true},provider,mappings).map(row=>({...row,
    status:row.status==='matched'?'presence':row.status,preview:true,
    reason:`Preliminary — ${row.reason} Check the PDF reading before finishing this statement.`}));
}
export function billDataSummary(provider,now=new Date()){
  const ready=!!provider.loaded&&!provider.simulated;
  const time=Date.parse(provider.refreshedAt||'');
  const dateKnown=Number.isFinite(time)&&time<=now.getTime();
  return {ready,count:ready?(Number.isInteger(provider.recordCount)?provider.recordCount:(provider.records||[]).length):0,dateKnown,
    updatedAt:dateKnown?new Date(time).toISOString():null,
    updateDue:ready&&(!dateKnown||now.getTime()-time>=7*86400000)};
}
export function completionReviews(rows,resolutions={}){
  const next=structuredClone(resolutions);
  for(const row of rows)if(row.status==='presence'&&!row.preview&&!next[row.id]?.decision)
    next[row.id]={...next[row.id],note:next[row.id]?.note||'',decision:'Reviewed — no action needed'};
  return next;
}
export function readingIssues(doc){
  const check=totals(doc),issues=[];
  if(!doc.rows.length)issues.push('No invoice rows were read.');
  if(!doc.statementDate)issues.push('Check the statement date.');
  if(check.difference===null)issues.push('Check the printed statement total.');
  else if(check.difference!==0)issues.push('The extracted rows and printed total differ.');
  if(doc.rows.some(r=>r.confidence<80))issues.push('Some scanned values are unclear.');
  return issues;
}
