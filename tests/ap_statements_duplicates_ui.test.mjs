import test from 'node:test';
import assert from 'node:assert/strict';
import {duplicateSidebarHTML,duplicateViewHTML,createDuplicateReviewDrafts} from '../app/ap_statements/frontend/duplicate-bills-ui.mjs';
const key='a'.repeat(64);
const finding={key,classification:'possible_duplicate',strength:'possible',reasons:['trailing_letter','currency_unknown'],
 latestDate:'2026-10-01',memberCount:2,previews:[{vendor:'Synthetic <Foods>',invoiceNumber:'271712',amount:129981,currency:''},{vendor:'Synthetic <Foods>',invoiceNumber:'271712X',amount:129981,currency:''}],review:null};
const base=()=>({phase:'ready',source:{importId:'source',capability:1},filters:{review:'unreviewed',classification:null,search:''},
 progress:{state:'ready',projectionReady:true,counts:{all:1,reviewed:0,unreviewed:1},completedAt:'2026-10-22T12:00:00Z'},
 page:{total:1,findings:[finding],nextCursor:null},selection:null,detail:null,error:null,loading:false,saveState:'idle'});

test('completed scan preparation never presents the saved scan age as a stalled live scan',()=>{
 const s={...base(),page:null,lastAdvanceAt:Date.now()-189911000,
  progress:{state:'ready',phase:'complete',projectionReady:false,checkpoint:279,recordsRead:223425,totalRecords:223425}};
 const html=duplicateViewHTML(s);
 assert.match(html,/Preparing shared review history/);assert.match(html,/scan is complete/i);
 assert.doesNotMatch(html,/No recent scan progress|since reported progress|Check not complete/);
 assert.match(html,/279/);
});
test('sidebar badge requires complete review projection; pending and failed never claim no duplicates',()=>{
 const state=base();assert.match(duplicateSidebarHTML(state,{active:true}),/Duplicate bills/);assert.match(duplicateSidebarHTML(state,{active:true}),/aria-current="page"/);
 for(const phase of ['pending','failed','restart_required']){
  const value={...state,phase,progress:{state:phase,counts:null,projectionReady:false},page:null};
  assert.doesNotMatch(duplicateSidebarHTML(value,{}),/class="count"/);
  assert.doesNotMatch(duplicateViewHTML(value),/No possible duplicates/);
 }
 const clean=base();clean.page={findings:[],total:0};clean.progress.counts={all:0,reviewed:0,unreviewed:0};
 assert.match(duplicateViewHTML(clean),/No possible duplicates found by these rules/);
});

test('a failed request shows paused checks without an active main or sidebar spinner',()=>{
 const state={...base(),phase:'running',page:null,error:{code:'unavailable',message:'Storage unavailable'},
  progress:{state:'running',phase:'packaging',recordsRead:223425,totalRecords:223425,projectionReady:false}};
 const html=duplicateViewHTML(state),sidebar=duplicateSidebarHTML(state);
 assert.match(html,/paused/i);assert.match(html,/223,425/);
 assert.match(html,/data-action="duplicate-retry"/);
 assert.doesNotMatch(html,/startup-spinner|aria-busy="true"|Checking your saved bills/);
 assert.doesNotMatch(sidebar,/duplicate-mini-spinner/);
 assert.match(sidebar,/aria-label="Duplicate checks need attention"/);
});

test('an active packaging request still shows activity when no error has occurred',()=>{
 const state={...base(),phase:'running',page:null,
  progress:{state:'running',phase:'packaging',recordsRead:223425,totalRecords:223425,projectionReady:false}};
 assert.match(duplicateViewHTML(state),/aria-busy="true"/);
 assert.match(duplicateSidebarHTML(state),/duplicate-mini-spinner/);
 assert.match(duplicateViewHTML(state),/Packaging duplicate results/);
});

test('waiting or stale scan progress has an honest stage and no active spinner',()=>{
 const state={...base(),phase:'running',page:null,lastAdvanceAt:Date.now()-120000,
  progress:{state:'running',phase:'packaging',recordsRead:223425,totalRecords:223425,checkpoint:275,projectionReady:false,canStep:false}};
 let html=duplicateViewHTML(state);assert.match(html,/Waiting for the active scan/);assert.doesNotMatch(html,/startup-spinner/);
 assert.doesNotMatch(duplicateSidebarHTML(state),/duplicate-mini-spinner/);assert.doesNotMatch(html,/Restart from saved/);
 state.progress.canStep=true;html=duplicateViewHTML(state);assert.match(html,/No recent scan progress/);assert.doesNotMatch(html,/startup-spinner/);
 assert.match(html,/Scan diagnostics/);assert.match(html,/275/);
 state.error={code:'duplicate_conflict',message:'The source or shared review changed'};
 html=duplicateViewHTML(state);assert.doesNotMatch(html,/The source or shared review changed/);assert.match(html,/could not continue/i);
});

test('paused shared conflicts point to the offered refresh action rather than a same-operation retry',()=>{
 const state={...base(),phase:'running',page:null,error:{code:'duplicate_conflict',message:'Shared review changed'},
  progress:{state:'running',projectionReady:false}};
 const html=duplicateViewHTML(state);
 assert.match(html,/Use “Refresh shared review”/);
 assert.doesNotMatch(html,/Retry same operation/);
});

test('loading disables every refresh and recovery action without removing draft controls',()=>{
 for(const state of [
  {...base(),phase:'restart_required',progress:{state:'restart_required',projectionReady:false}},
  {...base(),error:{code:'duplicate_conflict',message:'Refresh needed'}}
 ]){
  state.loading=true;const html=duplicateViewHTML(state);
  const buttons=html.match(/<button[^>]*data-action="duplicate-(?:retry|refresh)"[^>]*>/g)||[];
  assert.ok(buttons.length>=1);for(const button of buttons)assert.match(button,/disabled/);
 }
});
test('list uses accessible whole-row actions, literal escaped values, and explains cautious evidence',()=>{
 const html=duplicateViewHTML(base());
 assert.match(html,/data-action="duplicate-open"/);assert.match(html,/tabindex="0"/);assert.match(html,/role="button"/);
 assert.match(html,/Synthetic &lt;Foods&gt;/);assert.doesNotMatch(html,/<Foods>/);
 assert.match(html,/Currency not supplied/);assert.match(html,/Possible duplicate/);assert.match(html,/Trailing letter/);
 assert.doesNotMatch(html,/>Delete|>Pay|>Create credit|PDF/);
});
test('detail shows actual source records side by side, review attribution and explicit acknowledgement',()=>{
 const state=base();state.selection=key;state.detail={finding,members:finding.previews.map((b,n)=>({ordinal:n,bill:{...b,invoiceDate:'2026-10-01',sourceRows:String(n+2),sourceIssues:n?'Ambiguous source':'',status:'Open',currency:'USD',reportedPaidAmount:100}})),total:2};
 state.draft={decision:'not_duplicate',initials:'KC',note:'Keep <this>',expectedVersion:0,dirty:true};
 const html=duplicateViewHTML(state);
 assert.match(html,/Back to invoice list/);assert.match(html,/duplicate-evidence-grid/);assert.match(html,/Original amount/);assert.match(html,/Source rows/);
 assert.match(html,/Ambiguous source/);assert.match(html,/Required initials/);assert.match(html,/Note \(optional\)/);assert.match(html,/Keep &lt;this&gt;/);
 assert.match(html,/USD 1\.00/);
 assert.match(html,/self-reported/);assert.match(html,/not verify payment/);
 const saved={...finding,review:{decision:'not_duplicate',initials:'KC',note:'',version:1,at:'2026-10-22T12:00:00Z'}};
 state.detail.finding=saved;state.saveState='saved';state.draft.dirty=false;
 assert.match(duplicateViewHTML(state),/Review saved/);assert.match(duplicateViewHTML(state),/Reviewed — not a duplicate/);assert.match(duplicateViewHTML(state),/EDT/);
 state.detail.finding={...saved,priorReview:true};assert.match(duplicateViewHTML(state),/Prior review retained/);
 state.error={code:'duplicate_conflict',message:'Shared review changed'};state.saveState='not_saved';
 assert.match(duplicateViewHTML(state),/Keep &lt;this&gt;/);assert.match(duplicateViewHTML(state),/could not continue/);
});
test('drafts survive progress and navigation; only acknowledged server reviews reset dirtiness',()=>{
 const drafts=createDuplicateReviewDrafts();drafts.update(key,{note:'My draft',initials:'KC',decision:'not_duplicate'});
 assert.equal(drafts.hasUnsaved(key),true);drafts.get('b'.repeat(64));assert.equal(drafts.get(key).note,'My draft');
 const review={decision:'confirmed_duplicate',initials:'AB',note:'Colleague',version:2};
 assert.equal(drafts.get(key,review).note,'My draft');assert.equal(drafts.get(key).expectedVersion,0);
 drafts.acknowledge(key,{...review,decision:'not_duplicate',initials:'KC',note:'My draft',version:3});
 assert.equal(drafts.hasUnsaved(key),false);assert.equal(drafts.get(key).expectedVersion,3);
 drafts.clear();assert.equal(drafts.get(key).note,'');
});
test('ambiguous source and amount differences are explicit while reviewed work is green with text',()=>{
 for(const [classification,label] of [['export_review','Export needs review'],['amount_difference','Amount difference'],['exact_pattern','Exact reference pattern']]){
  const state=base();state.page.findings=[{...finding,classification}];assert.match(duplicateViewHTML(state),new RegExp(label));
 }
 const state=base();state.page.findings=[{...finding,strength:'strong'}];assert.match(duplicateViewHTML(state),/duplicate-tone-red/);
 state.page.findings=[{...finding,review:{decision:'confirmed_duplicate',initials:'KC',version:1,at:'2026-10-22T12:00:00Z'}}];
 assert.match(duplicateViewHTML(state),/duplicate-tone-green/);assert.match(duplicateViewHTML(state),/Reviewed — duplicate flagged/);
});

function profiledFinding(classification='possible_wrong_vendor'){
 const profiles=[{vendor:'Synthetic Paper',invoiceNumber:'PAP451234',periodStart:'2025-10-01',periodEnd:'2026-09-30',distinctReferences:24,
  shapes:[{shape:'PAP######',references:24}],established:true,matches:true},
 {vendor:'Synthetic <Produce>',invoiceNumber:'PAP451234',periodStart:'2025-10-01',periodEnd:'2026-09-30',distinctReferences:30,
  shapes:[{shape:'FOOD#######',references:30}],established:true,matches:false}];
 return {...finding,classification,reasons:['cross_vendor_reference','vendor_format_mismatch'],
  previews:[{...finding.previews[0],vendor:'Synthetic Paper',invoiceNumber:'PAP451234'},
            {...finding.previews[1],vendor:'Synthetic <Produce>',invoiceNumber:'PAP451234'}],
  evidence:{version:1,dateGapDays:0,referenceReuse:false,profiles}};
}
test('wrong-vendor list identifies both vendors and provides the new pattern filters',()=>{
 const state=base();state.page.findings=[profiledFinding()];const html=duplicateViewHTML(state);
 assert.match(html,/Possible wrong vendor/);assert.match(html,/Possible reference entry issue/);
 assert.match(html,/aria-label="Review Synthetic Paper and Synthetic &lt;Produce&gt;/);
 assert.match(html,/Vendor format mismatch/);assert.doesNotMatch(html,/Synthetic <Produce>/);
});
test('detail shows the immutable profile history and avoids selecting a correct vendor',()=>{
 const state=base(),f=profiledFinding();state.selection=f.key;state.detail={finding:f,members:f.previews.map((bill,n)=>({ordinal:n,bill})),total:2};
 const html=duplicateViewHTML(state);
 assert.match(html,/Why this was flagged/);assert.match(html,/2025-10-01/);assert.match(html,/2026-09-30/);
 assert.match(html,/24 distinct references/);assert.match(html,/PAP######/);assert.match(html,/FOOD#######/);
 assert.match(html,/Fits observed format/);assert.match(html,/Outside observed formats/);
 assert.match(html,/original invoice/i);assert.doesNotMatch(html,/Correct vendor:|automatically reassigned/);
 state.detail.finding={...f,classification:'reference_entry_issue',evidence:{...f.evidence,edit:'one_character_added_or_missing'}};
 assert.match(duplicateViewHTML(state),/One character added or missing/);
});
test('reference reuse remains visible alongside amount difference and review controls',()=>{
 const state=base();state.page.findings=[{...finding,classification:'amount_difference',evidence:{version:1,dateGapDays:400,referenceReuse:true,profiles:[]}}];
 const html=duplicateViewHTML(state);assert.match(html,/Amount difference/);assert.match(html,/Reused reference — check context/);assert.match(html,/400 days apart/);
});
test('missing or unsupported profile evidence is not presented as a learned fact',()=>{
 const state=base(),f=profiledFinding();state.selection=f.key;state.detail={finding:{...f,evidence:{version:99,profiles:[{vendor:'SECRET'}]}},members:[],total:0};
 const html=duplicateViewHTML(state);assert.doesNotMatch(html,/SECRET|Why this was flagged/);assert.match(html,/Compare the source bills/);
});
