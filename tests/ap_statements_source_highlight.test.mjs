import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {findSourceLine} from '../app/ap_statements/frontend/source-location.mjs';
const text=(str,x,y=400,width=70)=>({str,transform:[10,0,0,10,x,y],width,height:10});
const selection={reference:'269394',amount:361873};

test('a statement due-date column does not prevent highlighting the exact invoice and amount',()=>{
  for(const date of ['9/3/26','09/03/2026','2026-09-03']){
    const items=[text('269394',40),text(date,240),text('$3,618.73',440,400,80)];
    const original=structuredClone(items),hit=findSourceLine(items,selection);
    assert.ok(hit,`Locate the invoice row with date ${date}`);
    assert.equal(hit.text,`269394 ${date} $3,618.73`);
    assert.equal(hit.x,40);assert.equal(hit.width,480);assert.equal(hit.y,400);assert.equal(hit.height,10);
    assert.deepEqual(items,original);
  }
});

test('invoice and due dates in a single PDF text item are recognized without losing the full line bounds',()=>{
  const hit=findSourceLine([text('269394 8/15/26 9/3/26 $3,618.73',40,400,480)],selection);
  assert.ok(hit);assert.equal(hit.width,480);
});

test('invalid dates and additional invoice identifiers still prevent a guessed source highlight',()=>{
  for(const extra of ['999999','99/99/26','9/31/26','2026-02-30','INV/09/26']){
    assert.equal(findSourceLine([text('269394',40),text(extra,240),text('$3,618.73',440)],selection),null);
  }
  assert.equal(findSourceLine([text('269394',40),text('9/3/26',140),text('$100.00',240),text('999999',340),text('$3,618.73',440)],selection),null);
});

test('dates never relax exact invoice reference, exact cents, or duplicate-line checks',()=>{
  const line=[text('269394',40),text('9/3/26',240),text('$3,618.73',440)];
  assert.equal(findSourceLine(line,{...selection,reference:'269394X'}),null);
  assert.equal(findSourceLine(line,{...selection,amount:361874}),null);
  assert.equal(findSourceLine([...line,text('269394',40,300),text('9/3/26',240,300),text('$3,618.73',440,300)],selection),null);
});

test('a date-shaped selected reference is retained as the exact invoice identifier',()=>{
  const hit=findSourceLine([text('9/3/26',40),text('10/3/26',240),text('$3,618.73',440)],{...selection,reference:'9/3/26'});
  assert.ok(hit);
});

test('Invoice found selection highlights and scrolls the source preview just like other result statuses',async()=>{
  const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
  for(const status of ['presence','matched','possible','missing']){
    const row={id:'r',invoiceNumber:'269394',originalAmount:361873,page:1,status};
    const note={textContent:''},view={scrollTop:0},canvas={clientWidth:100,width:0,height:0,getContext:()=>({drawImage(){}}),closest:()=>view};
    const context={renderToken:0,files:new Map([['s',new Blob(['synthetic PDF boundary'])]]),state:{page:1,drawerTab:'review',selectedRow:'r'},comparisonsFor:()=>[row],
      document:{querySelector:selector=>selector==='#pdf-canvas'?canvas:selector==='#source-location-status'?note:null,createElement:()=>({width:0,height:0})},
      extractor:{async renderPage(file,page,buffer,selected){
        assert.equal(page,1);assert.equal(selected.reference,'269394');assert.equal(selected.amount,361873);
        buffer.width=200;buffer.height=800;
        return findSourceLine([text('269394',40),text('9/3/26',240),text('$3,618.73',440)],selected);
      }}};
    vm.runInNewContext(source.slice(source.indexOf('async function previewPDF('),source.indexOf('function collectRows(')),context);
    await context.previewPDF({id:'s'});
    assert.match(note.textContent,/matching invoice line highlighted/);assert.equal(view.scrollTop,160);
  }
});
