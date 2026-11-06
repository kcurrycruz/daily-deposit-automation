import test from 'node:test';
import assert from 'node:assert/strict';
import {mailImportsHTML,mailEvidenceHTML} from '../app/ap_statements/frontend/mail-imports-ui.mjs';
import {completionPayload} from '../app/ap_statements/frontend/history.mjs';

test('email status describes scheduled work without promising a five-minute checker',()=>{
 const html=mailImportsHTML({enabled:true,loaded:true,connection:{id:'conn',label:'AP Statements',paused:false,lastSuccessAt:'2026-11-06T13:17:00Z'},counts:{},items:[],messages:[]});
 assert.doesNotMatch(html,/every five minutes|Automatic imports on/);
 assert.match(html,/Ready for scheduled imports/);assert.match(html,/Last successful check/);
 assert.match(html,/New mail, retries, and earlier-email requests run on the configured import schedule/);
 assert.match(html,/next scheduled check/);assert.match(html,/Pause imports/);
 assert.match(html,/preliminary/i);assert.match(html,/Credits absent/);
});
test('mail controls escape subjects, label preliminary work and show separate New York dates',()=>{
 const html=mailImportsHTML({enabled:true,loaded:true,connection:{id:'conn',label:'AP Statements',paused:false},counts:{queued:2},
 items:[{id:'receipt',status:'awaiting_review',filename:'<img src=x onerror=alert(1)>',subject:'<script>bad</script>',received_at:'2026-11-04T15:00:00Z',
 imported_at:'2026-11-04T16:00:00Z',preliminary:{rangeRefreshPending:true,freshness:{stale:true}}}],messages:[]});
 assert.doesNotMatch(html,/<script>|<img src/);assert.match(html,/Awaiting review/);assert.match(html,/Preliminary/);
 assert.match(html,/Received/);assert.match(html,/Imported/);assert.match(html,/10:00 AM EST/);assert.match(html,/11:00 AM EST/);
 assert.match(html,/BILL export/);assert.match(html,/archive/i);assert.match(html,/<label[^>]*for="mail-history/);
 assert.throws(()=>completionPayload({doc:{id:'s',confirmed:false,rows:[{}]},results:[{status:'presence'}],resolutions:{},initials:'KC',expectedVersion:1}),/Confirm/);
});
test('capability absence renders nothing and disconnected state does not imply empty BILL data',()=>{
 assert.equal(mailImportsHTML({enabled:false}),'');
 assert.match(mailImportsHTML({enabled:true,loaded:true,connection:null,items:[],messages:[],counts:{}}),/not connected/i);
});
test('an explicitly completed server statement shows Reviewed without the preliminary action banner',()=>{
 const html=mailImportsHTML({enabled:true,loaded:true,connection:null,items:[{id:'r',status:'awaiting_review',display_status:'reviewed',filename:'done.pdf',completed:true,statement_id:'s'}],messages:[],counts:{}});
 assert.match(html,/Reviewed/);assert.doesNotMatch(html,/Awaiting review|Preliminary comparison/);assert.match(html,/badge green/);
});
test('saved preliminary found and amount differences show their source without review controls',()=>{
 const html=mailEvidenceHTML({receipt_id:'r',preliminary:true,compared_at:'2026-11-04T12:00:00Z',source:{label:'Saved Bills.csv',uploadedAt:'2026-11-03T12:00:00Z'},
 metadata:{},total:2,nextCursor:null,rows:[{invoiceNumber:'<script>123</script>',originalAmount:100,status:'presence',reason:'Found',candidates:[{invoiceNumber:'123',amount:100,vendor:'Synthetic'}]},
 {invoiceNumber:'124',originalAmount:150,status:'amount',reason:'Different amount',candidates:[{invoiceNumber:'124',amount:100,vendor:'Synthetic'}]}]});
 assert.match(html,/Preliminary/);assert.match(html,/Invoice found/);assert.match(html,/Amount difference/);assert.match(html,/Saved Bills.csv/);
 assert.doesNotMatch(html,/<script>|data-action="complete|data-action="candidate-confirm/);
});
