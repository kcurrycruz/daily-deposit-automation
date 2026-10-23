import test from 'node:test';
import assert from 'node:assert/strict';
let presentation;
try{({duplicateProgressPresentation:presentation}=await import('../app/ap_statements/frontend/duplicate-progress.mjs'));}catch(error){if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;}
function show(state,now=100000){assert.equal(typeof presentation,'function','scan presentation must be implemented');return presentation(state,now);}
const state=(phase,extra={})=>({phase:'running',lastAdvanceAt:100000,observedAt:100000,progress:{state:'running',phase,checkpoint:4,recordsRead:223425,totalRecords:223425,canStep:true,...extra}});

test('scan stages distinguish reading, candidates, packaging and review preparation without claiming completion',()=>{
 for(const [phase,title] of [['reading',/Reading/i],['candidates',/Checking.*patterns/i],['packaging',/Packaging/i]]){
  const p=show(state(phase));assert.equal(p.kind,'active');assert.match(p.title,title);assert.equal(p.busy,true);assert.doesNotMatch(p.title,/complete|finished/i);
 }
 assert.match(show(state('complete',{state:'ready',projectionReady:false})).title,/Preparing.*review/i);
 assert.equal(show(state('complete',{state:'ready',projectionReady:true})).kind,'ready');
 assert.match(show(state('future-phase')).title,/Checking/i);
});

test('a foreign live lease shows waiting, never active work or a restart permission',()=>{
 const p=show(state('packaging',{canStep:false,leaseExpiresAt:'2099-01-01T00:00:00Z'}));
 assert.equal(p.kind,'waiting');assert.equal(p.busy,false);assert.match(p.message,/another session/i);assert.doesNotMatch(p.message,/restart now/i);
});

test('one minute without advancement warns but never reports a finished check',()=>{
 const s=state('packaging');assert.equal(show(s,159999).kind,'active');
 const p=show(s,160000);assert.equal(p.kind,'interrupted');assert.equal(p.busy,false);assert.match(p.message,/no progress/i);
 s.lastAdvanceAt=160000;assert.equal(show(s,160001).kind,'active');
});

test('missing timing metadata and backward client time are safe and do not invent interruption',()=>{
 const s=state('reading');delete s.lastAdvanceAt;delete s.observedAt;
 assert.equal(show(s).kind,'active');s.lastAdvanceAt=200000;assert.equal(show(s,100000).kind,'active');
 assert.equal(show(s,100000).diagnostics.elapsedSeconds,0);
});

test('server errors and expired scan states stay paused and diagnostics are allowlisted',()=>{
 const s=state('packaging');s.error={code:'duplicate_conflict',message:'source changed secret'};
 const p=show(s);assert.equal(p.kind,'paused');assert.match(p.message,/refresh/i);assert.doesNotMatch(p.message,/source changed|secret/i);
 for(const phase of ['restart_required','failed','superseded'])assert.equal(show({...state('reading'),phase}).kind,'paused');
 assert.deepEqual(Object.keys(p.diagnostics).sort(),['checkpoint','elapsedSeconds','phase']);
 assert.equal(p.diagnostics.checkpoint,4);
});
