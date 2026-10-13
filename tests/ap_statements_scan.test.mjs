import test from 'node:test';
import assert from 'node:assert/strict';
import {parseStatement,layouts,groupInvoices,reconcile} from '../app/ap_statements/frontend/core.mjs';
import {readFileSync,existsSync} from 'node:fs';
import vm from 'node:vm';
const page = lines => [{page:1,ocr:true,lines}];
const line = (text,y,words=[]) => ({text,y,words,confidence:92});

test('unreadable Rinella logo is identified by both company email and phone, not either alone', () => {
  const identifiers=[line('e-mail ajproduce@aol.com',.1),line('518-465-4581 24 hr.',.12)];
  assert.equal(parseStatement(page(identifiers)).vendor,'A.J. Rinella');
  for(const single of identifiers) assert.equal(parseStatement(page([single])).layout,'generic');
});

test('statement date directly below its label is read without using an invoice date', () => {
  const doc=parseStatement(page([line('A.J. Rinella',.1),line('DATE:',.22),line('10/01/26',.245),line('09/28/26 INV100 100.00 100.00',.43)]));
  assert.equal(doc.statementDate,'2026-10-01');
  assert.equal(doc.rows[0].date,'2026-09-28');
});

test('split date uses label-column alignment when customer text shares the next line', () => {
  const doc=parseStatement(page([line('Rinella',.1),line('MAIL TO: DATE:',.22,[{text:'DATE:',x:.62}]),
    line('Customer 09/01/26 10/01/26',.245,[{text:'Customer',x:.14},{text:'09/01/26',x:.28},{text:'10/01/26',x:.60}])]));
  assert.equal(doc.statementDate,'2026-10-01');
});

test('table header and remote dates cannot silently become the statement date', () => {
  for(const lines of [[line('DATE INVOICE AMOUNT BALANCE',.32),line('09/28/26 INV100 100.00',.34)],
    [line('DATE:',.22),line('10/01/26',.5)], [line('DATE:',.22),line('02/30/26',.245)],
    [line('DATE:',.22),line('10/01/26 09/01/26',.245)]]) {
    assert.equal(parseStatement(page(lines)).statementDate,'');
  }
});

test('OCR whitespace in dates and decimal cents does not change reference digits', () => {
  const doc=parseStatement(page([line('Rinella',.1),line('DATE: 10/ 01 /26',.22),
    line('09/ 28 /26 001234 100. 00 100. 00',.43)]));
  assert.equal(doc.statementDate,'2026-10-01');
  assert.equal(doc.rows.length,1);
  assert.equal(doc.rows[0].invoiceNumber,'001234');
  assert.equal(doc.rows[0].amount,10000);
  assert.equal(doc.rows[0].balance,10000);
  assert.equal(doc.confirmed,false);
});

test('unreadable cents and references are not repaired by replacing letters with digits', () => {
  const doc=parseStatement(page([line('Rinella',.1),line('09/28/26 £01234 100.00',.43),line('09/28/26 001235 100. @@',.45)]));
  assert.equal(doc.rows.length,0);
});

test('broken spacing inside day digits is joined only within a slash date', () => {
  const doc=parseStatement(page([line('Rinella',.1),line('DATE: 10/ 0 1 /26',.22),line('09/ 2 8 /26 001234 100.00',.43)]));
  assert.equal(doc.statementDate,'2026-10-01');
  assert.equal(doc.rows[0].date,'2026-09-28');
  assert.equal(doc.rows[0].invoiceNumber,'001234');
});

test('OCR extra fractional digits are not silently truncated into valid money', () => {
  const doc=parseStatement(page([line('Rinella',.1),line('09/28/26 001234 100.000',.43)]));
  assert.equal(doc.rows.length,0);
});

function extractionHarness({failRetry=false, complete=false, generic=false,failInitialization=false}={}) {
  const workers=[], canvases=[];
  const ctx={parseStatement,layouts,URL,Uint8Array,Uint8ClampedArray,Float32Array,Math,
    pdfjs:{GlobalWorkerOptions:{},getDocument:()=>({promise:Promise.resolve({numPages:1,destroy:async()=>{},getPage:async()=>({
      getViewport:({scale})=>({width:60*scale,height:80*scale}),getTextContent:async()=>({items:[]}),
      render:()=>({promise:Promise.resolve()}),cleanup:()=>{},
    })})})},
    document:{createElement:()=>{
      const canvas={width:1,height:1,getContext:()=>({
        getImageData:(x,y,w,h)=>({data:new Uint8ClampedArray(w*h*4).fill(255)}),putImageData:()=>{},
      })};canvases.push(canvas);return canvas;
    }},
    Tesseract:{PSM:{AUTO:'3',SINGLE_BLOCK:'6'},createWorker:async(lang,engine,options)=>{
      if(failInitialization && engine===0) {
        queueMicrotask(()=>options.errorHandler?.('Language model could not be loaded'));
        return new Promise(()=>{});
      }
      const worker={engine,options,terminated:false,setParameters:async()=>{},terminate:async()=>{worker.terminated=true;},
        recognize:async(canvas,parameters)=>{
          if(failRetry && engine===0)throw Error('Fallback unavailable');
          const meta=generic?[['Vendor Example',.1,.1]]:[['ajproduce@aol.com',.05,.1],['518-465-4581',.05,.12]];
          const header=[['DATE:',.62,.22],['DATE',.18,.38],['INVOICE',.28,.38],['AMOUNT',.41,.38],['BALANCE',.78,.38]];
          const rows=[['09/28/26',.15,.43],['001234',.28,.43],['100.00',.41,.43],['100.00',.78,.43],
            ['09/29/26',.15,.45],['001235',.28,.45],['200.00',.41,.45],['200.00',.78,.45]];
          let words=[...meta,...header];
          if(complete || engine===0) {
            const top=(parameters.rectangle?.top ?? 0)/canvas.height;
            words=complete?[...words,...rows,['10/01/26',.60,.25],['INVOICE TOTAL',.77,.80],['300.00',.89,.815]]
              :top>.7?[['INVOICE TOTAL',.77,.80],['300.00',.89,.815]]:top<.3?[['10/01/26',.60,.25]]:rows;
          }
          const tsv='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'+words.map(([text,x,y])=>
            `5\t1\t1\t1\t1\t1\t${x*canvas.width}\t${y*canvas.height-1}\t${canvas.width*.05}\t2\t92\t${text}`).join('\n');
          return {data:{text:words.map(w=>w[0]).join('\n'),tsv,confidence:92}};
        },
      };workers.push(worker);return worker;
    }},
  };
  ctx.globalThis=ctx;
  const source=readFileSync(new URL('../app/ap_statements/frontend/extraction.mjs',import.meta.url),'utf8')
    .replace(/^import .*;\r?$/gm,'').replace(/\bexport /g,'').replace(/import\.meta\.url/g,"'http://localhost/ap/extraction.mjs'");
  vm.createContext(ctx);vm.runInContext(source,ctx);
  return {ctx,workers,canvases,file:{name:'statement.pdf',size:10,arrayBuffer:async()=>new ArrayBuffer(10)}};
}

test('weak Rinella scans recover rows, date and printed total through local fallback without auto-confirming',async()=>{
  const h=extractionHarness();
  try {
    const doc=await h.ctx.extractPDF(h.file);
    assert.equal(doc.vendor,'A.J. Rinella');
    assert.equal(doc.rows.length,2);
    assert.equal(doc.rows[0].invoiceNumber,'001234');
    assert.equal(doc.rows[1].amount,20000);
    assert.equal(doc.statementDate,'2026-10-01');
    assert.equal(doc.declaredTotal,30000);
    assert.equal(doc.confirmed,false);
    assert.match(doc.warnings.join(' '),/review|verify/i);
    assert.ok(h.workers.every(w=>new URL(w.options.langPath).origin==='http://localhost'));
  }finally{await h.ctx.stopOCR();}
  assert.ok(h.workers.every(w=>w.terminated));
  assert.ok(h.canvases.every(c=>c.width===0 && c.height===0));
});

test('fallback errors retain the initial extraction and provide a review warning',async()=>{
  const h=extractionHarness({failRetry:true});
  try {
    const doc=await h.ctx.extractPDF(h.file);
    assert.equal(doc.vendor,'A.J. Rinella');
    assert.equal(doc.rows.length,0);
    assert.match(doc.warnings.join(' '),/retry|fallback|enhanced/i);
    assert.equal(doc.confirmed,false);
  }finally{await h.ctx.stopOCR();}
});

test('a complete strong scan keeps its rows without loading the dot-matrix fallback',async()=>{
  const h=extractionHarness({complete:true});
  try{
    const doc=await h.ctx.extractPDF(h.file);
    assert.equal(doc.rows.length,2);
    assert.equal(doc.declaredTotal,30000);
    assert.ok(!h.workers.some(w=>w.engine===0));
  }finally{await h.ctx.stopOCR();}
});

test('dot-matrix cleanup connects pale broken strokes but leaves blank paper white',()=>{
  const h=extractionHarness();
  assert.equal(typeof h.ctx.joinDots,'function');
  const pixels=new Uint8ClampedArray(3*3*4).fill(255);
  for(let n=0;n<9;n++)if(n!==4)pixels.fill(200,n*4,n*4+3);
  let written;
  const canvas={width:3,height:3,getContext:()=>({getImageData:()=>({data:pixels}),putImageData:image=>{written=image.data;}})};
  h.ctx.joinDots(canvas,{left:0,top:0,width:3,height:3},1);
  assert.equal(written[16],0);
  const white=new Uint8ClampedArray(36).fill(255);
  canvas.getContext=()=>({getImageData:()=>({data:white}),putImageData:image=>{written=image.data;}});
  h.ctx.joinDots(canvas,{left:0,top:0,width:3,height:3},1);
  assert.ok(written.every(value=>value===255));
});

test('Rinella cropped header fields fill missing metadata only when their OCR is readable',()=>{
  const doc=parseStatement([{page:1,ocr:true,lines:[line('Rinella',.1)],ocrFields:{
    statementDate:{text:'DATE:\n10/01/26',confidence:92},printedTotal:{text:'300. 00',confidence:92},
  }}]);
  assert.equal(doc.statementDate,'2026-10-01');
  assert.equal(doc.declaredTotal,30000);
  for(const [text,confidence] of [['300.@@',92],['300.00',40],['30000',92]]) {
    const bad=parseStatement([{page:1,ocr:true,lines:[line('Rinella',.1)],ocrFields:{printedTotal:{text,confidence}}}]);
    assert.equal(bad.declaredTotal,null);
  }
});

test('ordinary Date headers retain existing same-line extraction behavior',()=>{
  assert.equal(parseStatement(page([line('Date 10/01/26',.22)])).statementDate,'2026-10-01');
});

test('dot-matrix and standard OCR models use independent browser cache keys',async()=>{
  const h=extractionHarness();
  try {
    await h.ctx.extractPDF(h.file);
    const standard=h.workers.find(w=>w.engine===1),dots=h.workers.find(w=>w.engine===0);
    assert.notEqual(dots.options.cachePath??'.',standard.options.cachePath??'.');
  }finally{await h.ctx.stopOCR();}
});

test('a vendor filename alone cannot enable fixed Rinella OCR regions',async()=>{
  const h=extractionHarness({generic:true});h.file.name='Rinella statement.pdf';
  try{
    await h.ctx.extractPDF(h.file);
    assert.ok(!h.workers.some(w=>w.engine===0));
  }finally{await h.ctx.stopOCR();}
});

test('unreadable positioned original amount is not replaced with the invoice balance',()=>{
  const doc=parseStatement(page([line('Rinella',.1),line('09/28/26 001234 100.000 80.00',.43,[
    {text:'100.000',x:.40,width:.05},{text:'80.00',x:.78,width:.05},
  ])]));
  assert.equal(doc.rows.length,0);
  assert.match(doc.warnings.join(' '),/amount.*unreadable|unreadable.*amount/i);
});

test('split cents retain positioned amount while an unreadable balance stays blank, not the running total',()=>{
  const doc=parseStatement(page([line('Rinella',.1),line('09/28/26 001234 100. 00 80. @@ 200.00',.43,[
    {text:'100.',x:.40,width:.035},{text:'00',x:.44,width:.02},
    {text:'80.',x:.78,width:.03},{text:'@@',x:.815,width:.02},{text:'200.00',x:.90,width:.06},
  ])]));
  assert.equal(doc.rows.length,1);
  assert.equal(doc.rows[0].amount,10000);
  assert.equal(doc.rows[0].balance,null);
});

test('reported OCR initialization failures settle instead of hanging the upload',async()=>{
  const h=extractionHarness({failInitialization:true});let timer;
  try {
    const doc=await Promise.race([h.ctx.extractPDF(h.file),new Promise(resolve=>{timer=setTimeout(()=>resolve(null),1000);})]);
    assert.ok(doc,'initial extraction must be returned when model initialization reports failure');
    assert.equal(doc.vendor,'A.J. Rinella');
    assert.match(doc.warnings.join(' '),/retry.*unavailable/i);
  }finally{clearTimeout(timer);await h.ctx.stopOCR();}
});

test('local dot-matrix worker closes on startup failure but retains successful and recognition responses',()=>{
  const url=new URL('../app/ap_statements/frontend/dot-matrix.worker.js',import.meta.url);
  assert.ok(existsSync(url),'startup-failure cleanup wrapper must be packaged');
  const events=[];
  const self={location:{href:'http://localhost/ap/dot-matrix.worker.js'},postMessage:message=>events.push(message),close:()=>events.push('closed')};
  vm.runInNewContext(readFileSync(url,'utf8'),{self,URL,importScripts:()=>{}});
  self.postMessage({status:'resolve',action:'initialize'});
  self.postMessage({status:'reject',action:'recognize'});
  assert.equal(events.filter(event=>event==='closed').length,0);
  self.postMessage({status:'reject',action:'loadLanguage',data:'Not found'});
  assert.equal(events.at(-1),'closed');
  assert.equal(events.at(-2).data,'Not found');
});

test('unknown Rinella balances stay unknown through grouping and comparison after confirmation',()=>{
  const doc={vendor:'A.J. Rinella',layout:'rinella',confirmed:true,rows:[{
    id:'r',type:'invoice',invoiceNumber:'001234',amount:10000,balance:null,page:1,confidence:99,
  }]};
  assert.equal(groupInvoices(doc)[0].outstanding,null);
  const result=reconcile(doc,{loaded:true,records:[{vendor:'A.J. Rinella',invoiceNumber:'001234',amount:10000}]});
  assert.equal(result[0].status,'presence');
});
