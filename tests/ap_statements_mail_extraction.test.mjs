import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {parseStatement,layouts} from '../app/ap_statements/frontend/core.mjs';

function harness(width,height,numPages=1){
 const sizes=[];
 const ctx={parseStatement,layouts,URL,Uint8Array,Uint8ClampedArray,Float32Array,Math,
  pdfjs:{GlobalWorkerOptions:{},getDocument:()=>({promise:Promise.resolve({numPages,destroy:async()=>{},getPage:async()=>({
   getViewport:({scale})=>({width:width*scale,height:height*scale}),getTextContent:async()=>({items:[]}),
   render:()=>({promise:Promise.resolve()}),cleanup:()=>{},
  })})})},document:{createElement:()=>{
   let w=0,h=0;return {get width(){return w;},set width(value){w=value;if(w&&h)sizes.push(w*h);},
    get height(){return h;},set height(value){h=value;if(w&&h)sizes.push(w*h);},
    getContext:()=>({getImageData:()=>({data:new Uint8ClampedArray(4)}),putImageData:()=>{}})};
  }},Tesseract:{PSM:{AUTO:'3'},createWorker:async()=>({setParameters:async()=>{},terminate:async()=>{},
   recognize:async()=>({data:{text:'Synthetic\n10/01/26 INV100 100.00',confidence:99,tsv:''}})})}};
 ctx.globalThis=ctx;vm.createContext(ctx);
 const source=readFileSync(new URL('../app/ap_statements/frontend/extraction.mjs',import.meta.url),'utf8')
  .replace(/^import .*;\r?$/gm,'').replace(/\bexport /g,'').replace(/import\.meta\.url/g,"'http://localhost/extraction.mjs'");
 vm.runInContext(source,ctx);return {ctx,sizes,file:{name:'synthetic.pdf',size:8,arrayBuffer:async()=>new ArrayBuffer(8)}};
}

test('background OCR and retry canvases respect the raster cap before allocation',async()=>{
 const h=harness(100000,120000);
 try{await h.ctx.extractPDF(h.file,()=>{},{maxRasterPixels:20_000_000});
  assert.ok(h.sizes.length>0);assert.ok(h.sizes.every(n=>n<=20_000_000),JSON.stringify(h.sizes));
 }finally{await h.ctx.stopOCR();}
});

test('nonfinite PDF viewports and excessive page counts fail before raster allocation',async()=>{
 for(const [w,h,pages] of [[Infinity,792,1],[612,NaN,1],[612,792,101]]){
  const harn=harness(w,h,pages);
  try{await assert.rejects(harn.ctx.extractPDF(harn.file,()=>{},{maxRasterPixels:20_000_000}));}
  finally{await harn.ctx.stopOCR();}
  assert.deepEqual(harn.sizes,[]);
 }
});

test('normal-size page scaling keeps existing interactive dimensions',async()=>{
 const h=harness(612,792);
 try{await h.ctx.extractPDF(h.file);assert.equal(h.sizes[0],Math.ceil(612*200/72)*Math.ceil(792*200/72));}
 finally{await h.ctx.stopOCR();}
});
