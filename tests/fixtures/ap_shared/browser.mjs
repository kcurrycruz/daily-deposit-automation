// Synthetic UI harness only. This is not a Supabase persistence test.
import {comparisonSnapshot} from '../../../app/ap_statements/frontend/shared-workspace.mjs';
const id='00000000-0000-4000-8000-000000000071',importId='00000000-0000-4000-8000-000000000072';
const doc={id,vendor:'Synthetic Produce',filename:'Synthetic statement.pdf',statementDate:'2026-10-01',declaredTotal:18400,pageCount:1,layout:'generic',confirmed:true,warnings:[],notes:'QA only — no company records',assignee:'',rows:[{id:'00000000-0000-4000-8000-000000000073',invoiceNumber:'00042',type:'invoice',date:'2026-09-01',amount:18400,balance:18400,page:1,confidence:99}]};
const simple=new URLSearchParams(location.search).has('simple');
if(simple)doc.confirmed=false;
const provider={loaded:true,simulated:false,label:'synthetic-bills.csv',records:[{id:`${importId}:0`,vendor:doc.vendor,invoiceNumber:'00042',amount:18400,kind:'invoice',currency:'USD',clearedPaymentAmount:0,scheduledAmount:0,creditAmount:0}]};
if(simple)Object.assign(provider.records[0],{vendor:'Synthetic Produce Albany',comparisonScope:'invoice-only',status:'PaidInFull'});
const mappings={},mappingVersions={};
// A local, explicitly synthetic original makes PDF reading usable in the preview.
const content='BT /F1 18 Tf 50 740 Td (SYNTHETIC QA - NOT COMPANY DATA) Tj 0 -50 Td (Synthetic Produce) Tj 0 -35 Td (Statement date: 10/01/2026) Tj 0 -45 Td (Invoice 00042     $184.00) Tj 0 -40 Td (Statement total: $184.00) Tj ET';
const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',`<< /Length ${content.length} >>\nstream\n${content}\nendstream`];
let pdf='%PDF-1.4\n',offsets=[0];
for(let i=0;i<objects.length;i++){offsets.push(pdf.length);pdf+=`${i+1} 0 obj\n${objects[i]}\nendobj\n`;}
const xref=pdf.length;pdf+=`xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n ').join('\n')}\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
const originalUrl=URL.createObjectURL(new Blob([pdf],{type:'application/pdf'}));
let detail={doc,version:1,resolutions:{},results:comparisonSnapshot(doc,provider,{}),importId,mappingSnapshot:{},ruleVersion:'ap-match-v2',completed:false,originalAvailable:true};
const history=[],snapshots=new Map(),replays=new Map();
window.hwfcSharedClient={dispose(){},async request(action,payload,options={}){
  await new Promise(resolve=>setTimeout(resolve,100));
  if(replays.has(options.requestId))return structuredClone(replays.get(options.requestId));
  let reply;
  if(action==='bootstrap')reply={activeImport:{id:importId,record_count:1,metadata:{label:provider.label,refreshedAt:'2026-10-01T12:00:00Z',asOf:'2026-10-01',sourceFormat:simple?'bill-native':'normalized'}},statements:detail.completed?[]:[{id}],mappings,mappingVersions,nextCursor:null};
  else if(action==='records_page')reply={records:provider.records,nextCursor:null,recordCount:1,importId};
  else if(action==='statement')reply=payload.revision_id?snapshots.get(payload.revision_id):detail;
  else if(action==='pdf_preview')reply={url:originalUrl};
  else if(action==='save_mapping'){if(payload.expected_version!==(mappingVersions[payload.vendor]||0))throw Error('Mapping conflict');mappings[payload.vendor]=payload.bill_vendor;mappingVersions[payload.vendor]=(mappingVersions[payload.vendor]||0)+1;reply={version:mappingVersions[payload.vendor]};}
  else if(action==='save_revision'){if(payload.expected_version!==detail.version)throw Object.assign(Error('Conflict. Reload latest.'),{code:'conflict'});const revisionId=crypto.randomUUID();detail={...detail,doc:structuredClone(payload.doc),resolutions:Object.fromEntries(Object.entries(payload.resolutions).map(([key,value])=>[key,{...value,...(value.decision?{at:new Date().toISOString()}:{})}])),results:payload.results,importId:payload.import_id,mappingSnapshot:payload.mapping_snapshot,ruleVersion:payload.rule_version,version:detail.version+1,revisionId,revisionVersion:detail.version+1};snapshots.set(revisionId,structuredClone(detail));reply={version:detail.version,statement_id:id,revision_id:revisionId};}
  else if(action==='complete_revision'){if(payload.expected_version!==detail.version)throw Error('Conflict');detail={...detail,version:detail.version+1,completed:true};const revisionId=crypto.randomUUID(),event={id:crypto.randomUUID(),statementId:id,revisionId,vendor:doc.vendor,filename:doc.filename,statementDate:doc.statementDate,initials:payload.initials,notes:payload.notes,status:detail.results.every(row=>row.status==='matched')?'reconciled':Object.values(detail.resolutions).some(value=>value.decision&&value.decision!=='Reviewed — no action needed')?'follow_up':'reviewed',completedAt:new Date().toISOString()};snapshots.set(revisionId,structuredClone(detail));history.unshift(event);reply={version:detail.version};}
  else if(action==='history_page')reply={items:history,nextCursor:null};
  else if(action==='reopen_statement'){detail={...detail,completed:false,version:detail.version+1,resolutions:{}};reply={version:detail.version};}
  else throw Error('Unsupported synthetic operation '+action);
  if(options.requestId)replays.set(options.requestId,structuredClone(reply));return structuredClone(reply);
}};
await import('../../../app/ap_statements/frontend/app.mjs');
