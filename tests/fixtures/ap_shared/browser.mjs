// Synthetic UI harness only. This is not a Supabase persistence test.
import {comparisonSnapshot} from '../../../app/ap_statements/frontend/shared-workspace.mjs';
const id='00000000-0000-4000-8000-000000000071',importId='00000000-0000-4000-8000-000000000072';
const doc={id,vendor:'Synthetic Produce',filename:'Synthetic statement.pdf',statementDate:'2026-10-01',declaredTotal:18400,pageCount:1,layout:'generic',confirmed:true,warnings:[],notes:'QA only — no company records',assignee:'',rows:[{id:'00000000-0000-4000-8000-000000000073',invoiceNumber:'00042',type:'invoice',date:'2026-09-01',amount:18400,balance:18400,page:1,confidence:99}]};
const provider={loaded:true,simulated:false,label:'synthetic-bills.csv',records:[{id:`${importId}:0`,vendor:doc.vendor,invoiceNumber:'00042',amount:18400,kind:'invoice',currency:'USD',clearedPaymentAmount:0,scheduledAmount:0,creditAmount:0}]};
let detail={doc,version:1,resolutions:{},results:comparisonSnapshot(doc,provider,{}),importId,mappingSnapshot:{},ruleVersion:'ap-match-v2',completed:false,originalAvailable:true};
const history=[],snapshots=new Map(),replays=new Map();
window.hwfcSharedClient={dispose(){},async request(action,payload,options={}){
  await new Promise(resolve=>setTimeout(resolve,100));
  if(replays.has(options.requestId))return structuredClone(replays.get(options.requestId));
  let reply;
  if(action==='bootstrap')reply={activeImport:{id:importId,record_count:1,metadata:{label:provider.label,refreshedAt:'2026-10-01T12:00:00Z',asOf:'2026-10-01'}},statements:detail.completed?[]:[{id}],mappings:{},mappingVersions:{},nextCursor:null};
  else if(action==='records_page')reply={records:provider.records,nextCursor:null,recordCount:1,importId};
  else if(action==='statement')reply=payload.revision_id?snapshots.get(payload.revision_id):detail;
  else if(action==='pdf_preview')throw Error('Synthetic harness has no PDF original.');
  else if(action==='save_revision'){if(payload.expected_version!==detail.version)throw Object.assign(Error('Conflict. Reload latest.'),{code:'conflict'});detail={...detail,doc:structuredClone(payload.doc),resolutions:payload.resolutions,results:payload.results,importId:payload.import_id,mappingSnapshot:payload.mapping_snapshot,version:detail.version+1};reply={version:detail.version,statement_id:id};}
  else if(action==='complete_revision'){if(payload.expected_version!==detail.version)throw Error('Conflict');detail={...detail,version:detail.version+1,completed:true};const revisionId=crypto.randomUUID(),event={id:crypto.randomUUID(),statementId:id,revisionId,vendor:doc.vendor,filename:doc.filename,statementDate:doc.statementDate,initials:payload.initials,notes:payload.notes,status:'reconciled',completedAt:new Date().toISOString()};snapshots.set(revisionId,structuredClone(detail));history.unshift(event);reply={version:detail.version};}
  else if(action==='history_page')reply={items:history,nextCursor:null};
  else if(action==='reopen_statement'){detail={...detail,completed:false,version:detail.version+1,resolutions:{}};reply={version:detail.version};}
  else throw Error('Unsupported synthetic operation '+action);
  if(options.requestId)replays.set(options.requestId,structuredClone(reply));return structuredClone(reply);
}};
await import('../../../app/ap_statements/frontend/app.mjs');
