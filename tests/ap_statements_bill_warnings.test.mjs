import test from 'node:test';
import assert from 'node:assert/strict';
import {createBillWarnings,billWarningsHTML} from '../app/ap_statements/frontend/bill-warnings.mjs';
test('warning view pages the displayed source and keeps exclusions visible with retry on read failure',async()=>{
 const calls=[];let fail=true;
 const reader=createBillWarnings({async request(action,payload){calls.push({action,payload});if(payload.cursor&&fail)throw Error('offline');return {importId:'source',total:2,warnings:[{rows:payload.cursor?'99':'2','reason':payload.cursor?'Inactive bill':'Missing vendor'}],nextCursor:payload.cursor?null:'next'};}});
 await reader.load({id:'source',label:'Weekly.csv'});assert.match(billWarningsHTML(reader.state),/Missing vendor/);
 await reader.load({id:'source',label:'Weekly.csv'},{more:true});assert.equal(reader.state.items.length,1);assert.match(billWarningsHTML(reader.state),/Retry/);
 fail=false;await reader.load({id:'source',label:'Weekly.csv'},{more:true});assert.equal(reader.state.items.length,2);assert.equal(reader.state.nextCursor,null);
 assert.equal(calls[0].action,'bill_warnings_page');assert.ok(calls.every(c=>c.payload.import_id==='source'));
});
test('a late warnings response cannot replace a newer displayed source',async()=>{
 let release;const reader=createBillWarnings({async request(a,p){if(p.import_id==='old')await new Promise(r=>release=r);return {importId:p.import_id,total:1,warnings:[{rows:'2',reason:p.import_id}],nextCursor:null};}});
 const old=reader.load({id:'old',label:'Old'});await reader.load({id:'new',label:'New'});release();await old;
 assert.equal(reader.state.importId,'new');assert.equal(reader.state.items[0].reason,'new');
});
