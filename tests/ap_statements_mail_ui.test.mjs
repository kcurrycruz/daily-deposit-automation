import test from 'node:test';
import assert from 'node:assert/strict';
import {mailImportsHTML} from '../app/ap_statements/frontend/mail-imports-ui.mjs';
import {completionPayload} from '../app/ap_statements/frontend/history.mjs';
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
