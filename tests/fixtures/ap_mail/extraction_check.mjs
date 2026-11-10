import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {tmpdir} from 'node:os';
import {join,resolve,dirname,basename} from 'node:path';
import {textPdf,imagePdf,encryptedPdf,statementLines} from './pdfs.mjs';
import {openExtractionPage,extractPDFFile} from '../../../workers/ap_mail/browser.mjs';
const folder=await mkdtemp(join(tmpdir(),'ap-mail-synthetic-'));
const view=await openExtractionPage();
const comparable=doc=>({vendor:doc.vendor,rows:doc.rows.map(({invoiceNumber,amount,type,page})=>({invoiceNumber,amount,type,page})),rawText:doc.rawText});
try{
 // System monospace fonts differ across Windows and Ubuntu. Generate the same
 // synthetic ink with a font from the existing locked PDF.js dependency.
 const require=createRequire(new URL('../../../app/ap_statements/package.json',import.meta.url));
 const fixtureFont=await readFile(require.resolve('pdfjs-dist/standard_fonts/LiberationSans-Bold.ttf'));
 await view.page.evaluate(async encoded=>{
  const face=new FontFace('APFixtureFont',Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)).buffer);
  await face.load();document.fonts.add(face);
 },fixtureFont.toString('base64'));
 const session=await view.browser.newBrowserCDPSession();
 const {arguments:args}=await session.send('Browser.getBrowserCommandLine');
 assert.ok(!args.includes('--no-sandbox'));await session.detach();
 assert.equal(await view.page.evaluate(async()=>{try{await fetch('https://example.com');return true;}catch{return false;}}),false);
 const expected=[['00042',10000,'invoice'],['00043',20000,'invoice']];
 const variants=[['digital',textPdf(),expected],['credit',textPdf(['Adventure in Food Trading Company',
  'Account statement','as of 11/01/26','00042 11/12/26 100.00','00043 - -5.00','TOTAL 95.00']),
  [['00042',10000,'invoice'],['00043',-500,'credit']]]];
 for(const name of ['scanned','dot-matrix','damaged-scan']){
  const jpeg=await view.page.evaluate(({lines,dots,clearDates})=>{
   const canvas=document.createElement('canvas');canvas.width=1836;canvas.height=2376;
   const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);
   ctx.fillStyle='black';ctx.font='54px APFixtureFont';
   lines.forEach((text,i)=>{
    const y=[.1,.22,.38,.43,.48,.8][i]*canvas.height;
    if(i>=2&&i<=4)text.split(/\s+/).forEach((word,n)=>ctx.fillText(word,[270,510,780,1440][n],y));
    else ctx.fillText(text,i===1?1140:120,y);
   });
   if(dots){
    const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#16365b';
    for(let y=0;y<canvas.height;y+=3)for(let x=0;x<canvas.width;x+=3)if(pixels.data[(y*canvas.width+x)*4]<150)ctx.fillRect(x,y,2.8,2.8);
    // The exact-value control isolates broken invoice/amount ink from date
    // recognition. A separate damaged-scan case also degrades the dates.
    if(clearDates)ctx.putImageData(pixels,0,0,240,Math.round(.40*canvas.height),250,Math.round(.15*canvas.height));
   }
   return canvas.toDataURL('image/jpeg',.97).split(',')[1];
  },{lines:statementLines,dots:name!=='scanned',clearDates:name==='dot-matrix'});
  variants.push([name,imagePdf(Buffer.from(jpeg,'base64'),1836,2376),name==='damaged-scan'?null:expected]);
 }
 for(const [name,pdf,expectedRows] of variants){
  const path=join(folder,name+'.pdf');await writeFile(path,pdf);
  const interactive=await view.page.evaluate(async({data,name})=>window.extractStatement(data,name,{}),{data:pdf.toString('base64'),name:name+'.pdf'});
  if(name==='damaged-scan'&&!interactive.rows.length){
   // The existing reader cannot always recover broken ink. The worker must
   // preserve that quality outcome, not register a successful empty statement.
   await assert.rejects(extractPDFFile(path,name+'.pdf'));
   continue;
  }
  assert.ok(interactive.rows.length,name+' '+JSON.stringify({text:interactive.rawText,warnings:interactive.warnings}));
  const automatic=await extractPDFFile(path,name+'.pdf');
  assert.deepEqual(comparable(automatic),comparable(interactive),name);
  assert.deepEqual(automatic.warnings,interactive.warnings,name+' quality warnings');
  assert.equal(automatic.confirmed,false);
  if(expectedRows)assert.deepEqual(automatic.rows.map(r=>[r.invoiceNumber,r.amount,r.type]),expectedRows,name+' '+JSON.stringify({text:automatic.rawText,warnings:automatic.warnings}));
  else {
   assert.ok(automatic.warnings.some(w=>w.includes('Scanned PDF: verify invoice numbers and amounts')),name+' must retain the manual-reading limitation');
   const recovered=automatic.rows.map(r=>[r.invoiceNumber,r.amount,r.type]);
   if(JSON.stringify(recovered)!==JSON.stringify(expected))assert.ok(automatic.warnings.some(w=>/Enhanced scan (?:reading|retry)/.test(w)),name+' incomplete recovery must retain the enhanced-scan review note');
  }
 }
 const excessive=join(folder,'too-many.pdf');await writeFile(excessive,textPdf(statementLines,{pages:101}));
 await assert.rejects(extractPDFFile(excessive,'too-many.pdf'));
 const malformed=join(folder,'bad.pdf');await writeFile(malformed,Buffer.from('%PDF-1.4\nbroken'));
 await assert.rejects(extractPDFFile(malformed,'bad.pdf'));
 const encrypted=join(folder,'encrypted.pdf');await writeFile(encrypted,encryptedPdf());
 await assert.rejects(extractPDFFile(encrypted,'encrypted.pdf'));
 console.log('Synthetic browser extraction checks passed: digital/scanned/dot-matrix/credit parity, sandbox, egress, limits.');
}finally{
 await view.close();
 assert.equal(dirname(resolve(folder)),resolve(tmpdir()));
 assert.ok(basename(folder).startsWith('ap-mail-synthetic-'));
 await rm(folder,{recursive:true,force:true});
}
