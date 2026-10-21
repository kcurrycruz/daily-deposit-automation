import {groupInvoices,invoiceKey,vendorKey,totals} from './core.mjs';
import {LIMITS} from './shared-client.mjs';
const unknown=name=>!vendorKey(name)||['unidentified vendor','unknown','unidentified'].includes(vendorKey(name));
export function sameStatementVendor(a,b,mappings={}){
  if(unknown(a)||unknown(b))return false;
  const left=Object.hasOwn(mappings,a)?mappings[a]:a,right=Object.hasOwn(mappings,b)?mappings[b]:b;
  // Similar names are not proof of the same supplier; only saved mappings may alias them.
  return vendorKey(left)===vendorKey(right);
}
function facts(doc){
  return groupInvoices(doc).filter(row=>['invoice','credit'].includes(row.kind)&&invoiceKey(row.invoiceNumber)&&Number.isSafeInteger(row.originalAmount))
    .map(row=>({reference:row.kind+':'+invoiceKey(row.invoiceNumber),amount:row.originalAmount,balance:row.outstanding,uncertain:row.confidence<80||row.duplicate}));
}
const signature=rows=>JSON.stringify(rows.map(r=>[r.reference,r.amount,r.balance]).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))));
export function assessStatement(doc,candidates,mappings={}){
  const incoming=facts(doc),eligible=candidates.filter(item=>sameStatementVendor(doc.vendor,item.doc.vendor,mappings));
  const known=new Set(eligible.flatMap(item=>facts(item.doc).map(row=>JSON.stringify([row.reference,row.amount]))));
  const repeated=incoming.filter(row=>known.has(JSON.stringify([row.reference,row.amount]))).length,added=incoming.length-repeated;
  const base={kind:'new',match:null,repeated,added};let best=null;
  for(const item of eligible){
    const prior=facts(item.doc),byRef=new Map(prior.map(row=>[row.reference,row]));
    const overlaps=incoming.filter(row=>byRef.has(row.reference));if(!overlaps.length)continue;
    const changed=overlaps.some(row=>byRef.get(row.reference).amount!==row.amount);
    const incomplete=value=>!!value.warnings?.length||!value.statementDate||!Number.isSafeInteger(value.declaredTotal)||totals(value).difference!==0||
      value.rows.some(row=>(row.confidence??0)<80||(['invoice','credit'].includes(row.type)&&(!invoiceKey(row.invoiceNumber)||!Number.isSafeInteger(row.amount))));
    const uncertain=incomplete(doc)||incomplete(item.doc)||incoming.some(row=>row.uncertain)||prior.some(row=>row.uncertain);
    const sameRows=incoming.length===prior.length&&signature(incoming)===signature(prior);
    // Non-invoice activity or a changed printed total must never be discarded.
    const activity=rows=>JSON.stringify((rows||[]).filter(r=>!['invoice','credit'].includes(r.type)).map(r=>[r.type,invoiceKey(r.invoiceNumber),r.amount,r.balance??null]).sort());
    const sameActivity=activity(doc.rows)===activity(item.doc.rows),sameTotal=(doc.declaredTotal??null)===(item.doc.declaredTotal??null);
    if(sameRows&&sameActivity&&sameTotal&&!uncertain&&doc.statementDate===item.doc.statementDate)return {...base,kind:'duplicate',match:item};
    const kind=!changed&&!uncertain&&added>0&&overlaps.length<incoming.length?'overlap':'similar';
    if(!best||overlaps.length>best.count||kind==='similar'&&best.kind==='overlap')best={kind,match:item,count:overlaps.length};
  }
  return best?{...base,kind:best.kind,match:best.match}:base;
}
export async function prepareStatementUpload({file,extract,findCandidates,upload,choose,mappings={}}){
  if(!Number.isInteger(file?.size)||file.size<1||file.size>LIMITS.file)throw Error('Each statement PDF must be at most 20 MiB.');
  let parsed;
  try{parsed=await extract(file);}
  catch(error){return {kind:'saved',saved:await upload(file,async()=>{throw error;})};}
  const candidates=await findCandidates(parsed),assessment=assessStatement(parsed,candidates,mappings);
  if(assessment.kind==='duplicate')return assessment;
  if(assessment.kind==='similar'){
    const choice=await choose(assessment,parsed);
    if(choice==='existing')return {...assessment,kind:'duplicate'};
    if(choice!=='continue')return {...assessment,kind:'cancelled'};
  }
  return {...assessment,kind:'saved',assessment:assessment.kind,saved:await upload(file,async()=>parsed)};
}
