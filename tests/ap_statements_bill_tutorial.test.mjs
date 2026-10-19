import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const tutorial = await import('../app/ap_statements/frontend/bill-export-guide.mjs').catch(()=>({}));

test('export instructions use the supplied BILL workflow and screenshot snippets',()=>{
  assert.equal(typeof tutorial.billExportGuideHTML,'function');
  const pages=[0,1,2,3].map(step=>tutorial.billExportGuideHTML(step));
  assert.match(pages[0],/Settings/);
  assert.match(pages[1],/Legacy Import\/Export/);assert.match(pages[1],/Bills/);
  assert.match(pages[2],/Default Mapping/);assert.match(pages[2],/Export all/);
  assert.match(pages[3],/Upload.*CSV/);
  const images=pages.join('').matchAll(/src="(\.\/assets\/bill-export\/[^"]+)"/g);
  const paths=[...images].map(match=>match[1]);
  assert.equal(paths.length,4);
  for(const path of paths)assert.ok(fs.existsSync(new URL('../app/ap_statements/frontend/'+path,import.meta.url)));
});

test('guide bounds navigation and offers CSV upload without importing anything',()=>{
  assert.equal(typeof tutorial.billExportGuideHTML,'function');
  const first=tutorial.billExportGuideHTML(-100),last=tutorial.billExportGuideHTML(100);
  assert.match(first,/Step 1 of 4/);assert.doesNotMatch(first,/data-step="-1"/);
  assert.match(first,/I already have the CSV/);assert.match(first,/data-action="bill-guide-upload"/);
  assert.match(last,/Step 4 of 4/);assert.doesNotMatch(last,/data-step="4"/);
  assert.match(last,/data-step="2"/);assert.match(last,/data-action="bill-guide-upload"/);
  assert.match(first,/role="dialog"/);assert.match(first,/aria-modal="true"/);
});
