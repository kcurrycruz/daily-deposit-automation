import test from 'node:test';
import assert from 'node:assert/strict';
const module=await import('../app/ap_statements/frontend/history-browser.mjs').catch(()=>null);
function api(){assert.ok(module,'The vendor history browser must be implemented');return module;}
const item=(id,vendor='Alpha',completedAt='2026-10-21T14:00:00Z')=>({id,statementId:'s-'+id,revisionId:'r-'+id,vendor,filename:id+'.pdf',statementDate:'2026-10-01',initials:'KC',status:'reviewed',completedAt,notes:''});

test('vendor directory includes older pages, deduplicates events and does not fetch PDFs',async()=>{
  const cursors=[];const items=await api().loadHistoryIndex(async cursor=>{cursors.push(cursor);return cursor===null?{items:[item('1')],nextCursor:'older'}:{items:[item('1'),item('2','Beta')],nextCursor:null};});
  assert.deepEqual(cursors,[null,'older']);assert.equal(items.length,2);
  assert.deepEqual(api().historyVendors(items),[{vendor:'Alpha',count:1},{vendor:'Beta',count:1}]);
});

test('incomplete history fails rather than showing a partial vendor directory',async()=>{
  await assert.rejects(api().loadHistoryIndex(async()=>({items:[item('1')],nextCursor:'repeat'})),/incomplete/i);
});

test('vendor selection preserves filters, newest completion first and exact vendor boundaries',()=>{
  const items=[item('old','Alpha','2026-10-20T14:00:00Z'),item('other','Alpha Foods'),item('new'),{...item('follow'),status:'follow_up'}];
  const before=structuredClone(items);
  assert.deepEqual(api().filterHistory(items,{vendor:'Alpha',status:'reviewed'}).map(i=>i.id),['new','old']);
  assert.equal(api().filterHistory(items,{initials:'MM'}).length,0);
  assert.deepEqual(items,before);
});

test('history browser escapes vendors and provides keyboard preview and full revision actions',()=>{
  const html=api().historyBrowserHTML([item('1','<Alpha>'),item('2','Beta')],{vendor:'<Alpha>'});
  assert.match(html,/aria-label="Statement vendors"/);assert.match(html,/All vendors/);
  assert.match(html,/aria-current="true"/);assert.match(html,/&lt;Alpha&gt;/);assert.doesNotMatch(html,/<Alpha>/);
  assert.match(html,/data-action="history-preview"/);assert.match(html,/data-action="history-open"/);
  assert.doesNotMatch(html,/2\.pdf/);
});

test('preview loads only on demand, caches a thumbnail in memory and discards stale results',async()=>{
  let requested=0,painted=0,release;const states=[];
  const preview=api().createHistoryPreview({loadPdf:async id=>{requested++;if(id==='s-1')await new Promise(r=>release=r);return new Blob([id]);},paint:async file=>{painted++;return 'data:image/png;base64,'+btoa(await file.text());},onChange:s=>states.push({...s})});
  assert.equal(requested,0);
  const first=preview.show(item('1'));await preview.show(item('2'),{pinned:true});release();await first;
  assert.equal(preview.state.item.id,'2');assert.equal(preview.state.phase,'ready');assert.equal(painted,1);
  preview.hide();assert.equal(preview.state.item.id,'2','A pinned preview survives pointer leave');
  preview.hide(true);assert.equal(preview.state.item,null);
  await preview.show(item('2'));assert.equal(requested,2,'The cached thumbnail needs no second private PDF fetch');
  assert.ok(states.some(s=>s.phase==='loading'));preview.dispose();assert.equal(preview.state.item,null);
});

test('preview failures show retry without changing review data or keeping stale thumbnails',async()=>{
  let fail=true;const original=item('1'),before=structuredClone(original);
  const preview=api().createHistoryPreview({loadPdf:async()=>{if(fail)throw Error('Private PDF unavailable');return new Blob(['pdf']);},paint:async()=> 'data:image/png;base64,cGRm',onChange(){}});
  await preview.show(original,{pinned:true});assert.equal(preview.state.phase,'error');
  const html=api().historyPreviewHTML(preview.state);assert.match(html,/history-preview-retry/);assert.doesNotMatch(html,/<img/);
  fail=false;await preview.show(original,{pinned:true});assert.equal(preview.state.phase,'ready');
  assert.deepEqual(original,before);preview.dispose();
});
